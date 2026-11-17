"""DeepSeek scaled recursion ablation, reusing upstream evolutionary orchestration."""
import argparse
import asyncio
from dataclasses import asdict
import hashlib
import inspect
import json
import os
from pathlib import Path
import random
import campaign as core
from alphadiana.harness.meta_n.client import SolverClient
from alphadiana.harness.meta_n.co_bench import evaluate_program
from alphadiana.harness.meta_n.resource_contract import ResourceContract
from alphadiana.harness.meta_n.layers import IsolatedMetaLayer
from meta_n.core.meta_layer import MetaLayer
from meta_n.core.solver import Layer1Solver
from meta_n.core.omega import OmegaEngine
from meta_n.utils.context_manager import ContextBudget
from meta_n.integrations.co_bench import COBenchAdapter
from meta_n.integrations.benchmark import AdapterExecutor, EvalResult
import meta_n.core.evolutionary_orchestrator as evolution

ROOT=core.REPO.parent/'experiments/deepseek_recursive_ablation_16k'
DATA=core.REPO.parent/'experiments/cobench_corrected_data/data'
RESOURCE=ResourceContract()
TASK_NAMES=['Assignment problem','Common due date scheduling','Equitable partitioning problem']

class SafeAdapter(COBenchAdapter):
    async def evaluate(self,task,solution):
        config={'data_dir':str(DATA),'eval_split':'dev',**RESOURCE.scorer_config()}
        if not solution.strip():return EvalResult(success=False,score=0.,raw_score=0.,feedback='Truncated/empty model program; not executed')
        result=await asyncio.to_thread(evaluate_program,solution,task.metadata['task_name'],config)
        return EvalResult(success=result['score']>0,score=result['score'],raw_score=result['score'],feedback=result['feedback'])
    # Paper depth-1 ablation reports validation only; avoid auto held-out scoring
    # on files whose every instance belongs to the official dev split.
    evaluate_test=None

class DevExecutor(AdapterExecutor):
    is_sandboxed=True
    def __init__(self,adapter):
        # Hide evaluate_test capability from upstream's hasattr check.
        class AdapterView:
            def __getattr__(self,name):
                if name=='evaluate_test':raise AttributeError(name)
                return getattr(adapter,name)
        super().__init__(AdapterView())

class LoggedIsolatedLayer(MetaLayer):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.events=[]
    def _run_pre_process(self,task,outer_context=''):
        result=IsolatedMetaLayer._run_pre_process(self,task,outer_context)
        path=ROOT/'full'/'layer_events.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a') as f:f.write(json.dumps({'task_id':task.task_id,**self.events[-1]},ensure_ascii=False)+'\n')
        return result

class ContractClient(SolverClient):
    async def complete(self,messages,temperature=0,seed=None):
        prefix=RESOURCE.prompt()+'\nActual fixed base solver source:\n'+inspect.getsource(Layer1Solver)+'\n'
        messages=[{**m,'content':prefix+m['content']} for m in messages]
        result=await super().complete(messages,temperature=temperature,seed=seed)
        if self.response['choices'][0]['finish_reason']!='stop':
            return '', result[1]  # Invalid output scores zero; retain journal and do not regenerate
        return result

def client_config(mode):
    return {'model':'deepseek-flash','api_base':'https://api.deepseek.com','max_tokens':16384,'request_timeout_seconds':180,
            'input_token_bound':180000,'budget_ledger':str(core.REPO.parent/'experiments/budget_reservations.jsonl'),
            'budget_scope':'deepseek_ablation_16k_'+mode,'pilot_cap_cny':30,'global_cap_cny':150,
            'budget_branches':[],'request_log_dir':str(ROOT/mode/'requests'),
            'halt_file':str(ROOT/mode/'request_halted.json')}

def protocol():
    adapter=SafeAdapter(str(DATA),task_names=TASK_NAMES,timeout=10,instance_workers=1)
    tasks=adapter.load_tasks();assert len(tasks)==3
    body={'output_token_cap':16384,'purpose':'scaled_method_ablation_16k_new_protocol_after_truncation_audit',
          'seed':42,'resource_contract':asdict(RESOURCE),'dataset_revision':'6e561a36254d4315b8c2d155e81a465b634e87e1',
          'task_names':TASK_NAMES,'metric':'archive-best validation and best fixed chain validation; no held-out test',
          'full':{'beam_width':2,'beam_candidates':2,'max_iterations':3,'patience':4,'max_depth':10,
                  'epsilon':0.02,'novelty_alpha':0.3,'temperatures':[0.5,0.7,0.9],'max_retries':2,'retry_threshold':0.1,
                  'gate_tasks':0,'force_code_library_live':True},
          'depth1':{'runs':4,'temperature':1.0,'omega':False,'code_library':False,'outer_context':False},
          'departures':['DeepSeek instead of Gemma/GPT','3 task families, one official file each instead of 36 full tasks',
                        '3 evolutionary iterations instead of 6/8; single seed instead of 3',
                        'no candidate gate in scaled run; preserve library injection explicitly on newer upstream',
                        'standard-library-only solver and macOS sandbox; costs not compute-matched'],
          'source':{'paper':'https://arxiv.org/html/2608.24735v1#A3','upstream_commit':__import__('subprocess').check_output(['git','-C',str(core.REPO.parent/'meta-n'),'rev-parse','HEAD'],text=True).strip()},
          'files':{str(p.relative_to(DATA)):hashlib.sha256(p.read_bytes()).hexdigest() for n in TASK_NAMES for p in sorted((DATA/n).iterdir()) if p.is_file()}}
    body['hash']=core.digest(body);core.save(ROOT/'protocol.json',body)
    return body,adapter,tasks

async def run_full(p,adapter,tasks):
    if (ROOT/'full/result.json').exists():return json.loads((ROOT/'full/result.json').read_text())
    attempt=ROOT/'full/attempt.json'
    if attempt.exists():raise RuntimeError('Prior full attempt retained; audit required before resume')
    core.save(attempt,{'protocol_hash':p['hash']})
    client=ContractClient(client_config('full'))
    evolution.MetaLayer=LoggedIsolatedLayer
    cfg=evolution.EvolutionaryConfig(**p['full'],seed=42,parallel=1,output_dir=str(ROOT/'full'),no_early_stop=True)
    omega=OmegaEngine(client,context_budget=ContextBudget(max_tokens=24000));omega.context_manager.rng=random.Random(42)
    orchestrator=evolution.EvolutionaryOrchestrator(client,DevExecutor(adapter),omega,cfg,solver_language='python')
    try:
        result=await orchestrator.run(tasks,run_config={'protocol_hash':p['hash'],'model':'deepseek-flash','scaled':True})
        orchestrator.save_results(result,run_config={'protocol_hash':p['hash'],'model':'deepseek-flash','scaled':True})
        # Persist concise metrics independently of upstream summary schema.
        value={'best_chain_validation':result.best_mean_score,'archive_best_validation':result.oracle_mean_score,
               'archive_size':result.archive_size,'iterations':result.total_iterations,
               'per_task_best_scores':result.per_task_best_scores,
               'max_observed_depth':max(c.depth for c in orchestrator.archive.candidates)}
        core.save(ROOT/'full/result.json',value);return value
    finally:await client.close()

def retained_truncations(task,folder):
    records=[json.loads(f.read_text()) for f in folder.glob('*.json')]
    return [r for r in records if any(task.description in m.get('content','') for m in r.get('messages',[]))
            and r.get('response',{}).get('choices',[{}])[0].get('finish_reason')=='length']

async def run_flat(p,adapter,tasks):
    output=[]
    for draw in range(4):
        path=ROOT/'depth1'/f'draw_{draw}.json'
        if path.exists():output.append(json.loads(path.read_text()));continue
        attempt=path.with_suffix('.attempt.json')
        # Recovery uses only already saved per-task results or the retained truncated response.
        core.save(attempt,{'protocol_hash':p['hash'],'draw':draw})
        client=ContractClient(client_config('depth1'));solver=Layer1Solver(client,language='python');rows=[]
        try:
            for task in tasks:
                saved=ROOT/'depth1'/f'draw_{draw}_{task.task_id}.json'
                if saved.exists():
                    rows.append(json.loads(saved.read_text()));continue
                truncated=retained_truncations(task,ROOT/'depth1/requests')
                already_used={json.loads(f.read_text()).get('source_request_id') for f in (ROOT/'depth1').glob('draw_*_*.json')}
                truncated=[r for r in truncated if r['request_id'] not in already_used]
                if truncated:
                    assert len(truncated)==1
                    r=truncated[0];record={'task_id':task.task_id,'script':'','raw_output':r['response']['choices'][0]['message']['content'],'tokens':r['usage']['total_tokens'],'score':0.,'feedback':'Retained truncated output; not executed or regenerated','source_request_id':r['request_id']}
                    core.save(saved,record);rows.append(record);continue
                script,raw,tokens=await solver.solve(task,temperature=1.)
                result=await adapter.evaluate(task,script)
                rows.append({'task_id':task.task_id,'script':script,'raw_output':raw,'tokens':tokens,
                             'score':result.score,'feedback':result.feedback})
                core.save(ROOT/'depth1'/f'draw_{draw}_{task.task_id}.json',rows[-1])
            record={'draw':draw,'rows':rows};core.save(path,record);output.append(record)
        finally:await client.close()
    best={t.task_id:max(next(r['score'] for r in draw['rows'] if r['task_id']==t.task_id) for draw in output) for t in tasks}
    means=[sum(r['score'] for r in draw['rows'])/len(tasks) for draw in output]
    return {'archive_best_validation':sum(best.values())/len(tasks),'best_chain_validation':max(means),'draw_means':means,'per_task_best_scores':best}

async def main_async(stage):
    p,adapter,tasks=protocol()
    sources=[Path(__file__),*sorted((core.REPO/'alphadiana/harness/meta_n').glob('*.py'))]
    implementation={'files':{str(f.relative_to(core.REPO)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources}}
    if not (ROOT/'implementation.json').exists():core.save(ROOT/'implementation.json',implementation)
    old=json.loads((ROOT/'implementation.json').read_text())
    if old!=implementation:
        core.save(ROOT/'implementation_amendments'/(core.digest(implementation)+'.json'),{'previous':old,'current':implementation,'reason':'Logged infrastructure cleanup/deadline fix; saved-output rescore and partial-draw recovery; no strategy edits or model regeneration'})
    if stage=='validate':
        cfg=evolution.EvolutionaryConfig(**p['full'],seed=42,parallel=1,output_dir=str(ROOT/'full'),no_early_stop=True)
        print('Protocol frozen; upstream config constructed; no model requests.');return
    if (ROOT/'comparison.json').exists():
        print((ROOT/'comparison.json').read_text());return
    if not os.environ.get('DEEPSEEK_API_KEY'):os.environ['DEEPSEEK_API_KEY']=(core.REPO.parent/'apikey').read_text().strip().strip("\"'")
    flat=await run_flat(p,adapter,tasks)
    full=await run_full(p,adapter,tasks)
    summary={'full':full,'depth1':flat,'delta_archive_best':full['archive_best_validation']-flat['archive_best_validation'],
             'warning':'Scaled validation ablation on DeepSeek, unequal realized compute, not held-out or original numerical reproduction'}
    core.save(ROOT/'comparison.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['validate','all'],default='validate');args=parser.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True);asyncio.run(main_async(args.stage))
