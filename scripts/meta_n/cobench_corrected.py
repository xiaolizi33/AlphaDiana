"""Small, separately frozen CO-Bench reproduction using upstream data and scoring."""
import argparse
import asyncio
import fcntl
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import yaml
import campaign as core
from alphadiana.harness.meta_n.co_bench import evaluate_program
from meta_n.integrations.co_bench import COBenchAdapter
from dataclasses import asdict
from alphadiana.harness.meta_n.resource_contract import ResourceContract
RESOURCE=ResourceContract()

ROOT=core.REPO.parent/'experiments/cobench_corrected'
PREP=core.REPO.parent/'experiments/cobench_corrected_data'
BOTH=['cobench_independent','cobench_recursive']
CONTRACT=RESOURCE.prompt()
SEARCH_SEED=20261116

def freeze():
    tree=json.loads((PREP/'source_tree.json').read_text())
    splits={'G':['Assignment problem','Common due date scheduling','Equitable partitioning problem'],
            'D':['Generalised assignment problem','Container loading','Corporate structuring'],
            'T':['Uncapacitated warehouse location','Resource constrained shortest path','Assortment problem']}
    adapter=COBenchAdapter(str(PREP/'data'),task_names=sum(splits.values(),[]))
    tasks={t.metadata['task_name']:t for t in adapter.load_tasks()}
    assert len(tasks)==9
    p={'purpose':'corrected_attachment_comparison_with_fresh_task_families',
       'dataset':'CO-Bench/CO-Bench','revision':tree['revision'],'seed':SEARCH_SEED,
       'splits':{k:[{'id':tasks[n].task_id,'name':n,'problem':tasks[n].description,'answer':''} for n in ns] for k,ns in splits.items()},
       'files':{str(f.relative_to(PREP)):hashlib.sha256(f.read_bytes()).hexdigest() for n in tasks for f in sorted((PREP/'data'/n).iterdir()) if f.is_file()},
       'data_policy':'G/D first official file with dev indices; T first official non-dev file; task families disjoint and no synthetic instances; excluded empty-test preflight files retained separately',
       'resource_contract':asdict(RESOURCE),'model':'deepseek-flash','solver_max_tokens':8192,'omega_max_tokens':8192,
       'scope_reservation_cap_cny':12,'branch_reservation_cap_cny':10,
       'branch_token_cap':2000000,'answer_contract':CONTRACT,
       'selection':'mean official normalized score; ties shallower then A',
       'test_policy':'same selected chain reuses identical outputs; AC supplemental diagnostic on D only',
       'meta_n_commit':subprocess.check_output(['git','-C',str(core.REPO.parent/'meta-n'),'rev-parse','HEAD'],text=True).strip()}
    p['hash']=core.digest(p); core.save(ROOT/'protocol.json',p)
    return p

def client_config(branches,omega=False,protocol=None):
    return {'resource_contract':asdict(RESOURCE),'model':'deepseek-flash','api_base':'https://api.deepseek.com','max_tokens':8192,
            'input_token_bound':90000 if omega else 24000,
            'budget_ledger':str(core.REPO.parent/'experiments/budget_reservations.jsonl'),
            'request_log_dir':str(ROOT/'requests'),'budget_scope':'cobench_corrected','pilot_cap_cny':12,'global_cap_cny':150,
            'budget_branches':branches,'branch_token_cap':2000000,'branch_cny_cap':10,
            'answer_contract':CONTRACT,'halt_file':str(ROOT/'request_halted.json')}

def score_config(p,split):
    return {'data_dir':str(PREP/'data'),'eval_split':'test' if split=='T' else 'dev',
            'task_names':{t['id']:t['name'] for ts in p['splits'].values() for t in ts},**RESOURCE.scorer_config()}

def read_rows(path):
    rows=core.read_rows(path)
    for row in rows:
        repair=ROOT/'score_repairs'/path.stem/(row['task_id']+'.json')
        if repair.exists():
            saved=json.loads(repair.read_text())
            if saved['original_row_hash']!=core.digest(row):raise ValueError('Repair source mismatch')
            row.update({k:saved[k] for k in ['score','correct','rationale','score_metadata']})
            row.update(score_status='valid_scored',error=None)
            row['metadata']['score_repair']=str(repair)
    return rows

def run(p,split,label,chain,branches):
    from alphadiana.engine.config.experiment_config import ExperimentConfig
    from alphadiana.engine.config.validator import ConfigValidator
    from alphadiana.engine.runner import Runner
    result=ROOT/'results'/f'cobench_{split}_{label}.jsonl'
    if result.exists():
        rows=read_rows(result)
        if any(r['score_status']!='valid_scored' for r in rows):raise RuntimeError('Saved failed run requires audit')
        if len(rows)==len(p['splits'][split]):return rows
    cfg={'run_id':f'cobench_{split}_{label}','agent':{'name':'meta_n_co_bench','version':'0.1.0','config':{
        **client_config(branches),'strategy_chain':[str(ROOT/'strategies'/f'{n}.json') for n in chain]}},
        'benchmark':{'name':'custom','config':{'problems':p['splits'][split]}},
        'scorer':{'name':'co_bench_official','config':score_config(p,split)},
        'num_samples':1,'max_concurrent':1,'output_dir':str(ROOT/'results'),
        'metadata':{'protocol_hash':p['hash'],'split':split,'candidate':label}}
    path=ROOT/'configs'/f'{split}_{label}.yaml';path.parent.mkdir(parents=True,exist_ok=True)
    text=yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False)
    if path.exists() and path.read_text()!=text:raise ValueError('Config changed')
    path.write_text(text)
    exp=ExperimentConfig.from_yaml(path)
    errors=ConfigValidator().validate(exp)
    if errors:raise ValueError(errors)
    print('RUN',split,label,flush=True)
    runner=Runner(exp)
    try:
        runner.setup();runner.run()
    finally:
        runner.teardown()
    rows=read_rows(result)
    if len(rows)!=len(p['splits'][split]) or any(r['score_status']!='valid_scored' for r in rows):raise RuntimeError('Incomplete or failed run')
    # Omega reads actual official evaluator feedback, not deferred-execution placeholder.
    return rows

def omega_rows(rows):
    rows=json.loads(json.dumps(rows))
    for r in rows:
        r['metadata']['execution']['stdout']=r['rationale']
    return rows

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['validate','all'],default='validate');args=parser.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True)
    with (ROOT/'campaign.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        p=freeze();core.ROOT=ROOT;core.client_config=client_config
        # Pin implementation before any paid call.
        implementation={'files':{str(f.relative_to(core.REPO)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__),Path(core.__file__),*sorted((core.REPO/'alphadiana/harness/meta_n').glob('*.py'))]}}
        if not (ROOT/'implementation.json').exists():core.save(ROOT/'implementation.json',implementation)
        old=json.loads((ROOT/'implementation.json').read_text())
        if old!=implementation:
            core.save(ROOT/'implementation_amendments'/(core.digest(implementation)+'.json'),{'previous':old,'current':implementation,'reason':'Logged infrastructure cleanup/deadline fix; saved-output rescore and partial-draw recovery; no strategy edits or model regeneration'})
        if args.stage=='validate':
            for ts in p['splits'].values():
                for t in ts:
                    result=evaluate_program('def solve(**kwargs):\n    return {}',t['name'],score_config(p,'T' if ts is p['splits']['T'] else 'G'))
                    print(t['name'],result['score'],result['feedback'][:160],flush=True)
            print('Infrastructure validation complete; no model requests.');return
        if not os.environ.get('DEEPSEEK_API_KEY'):os.environ['DEEPSEEK_API_KEY']=(core.REPO.parent/'apikey').read_text().strip().strip("\"'")
        os.chdir(core.REPO)
        assert p['answer_contract']==client_config([])['answer_contract']==RESOURCE.prompt()
        assert score_config(p,'G')['instance_timeout']==p['resource_contract']['instance_timeout_seconds']
        genp={**p,'G':p['splits']['G']}
        base=run(p,'G','base',[],BOTH)
        a=asyncio.run(core.generate(genp,'A',[],omega_rows(base),BOTH))
        if not a['valid']:raise RuntimeError('A invalid; no repair')
        ta=run(p,'G','A',['A'],[BOTH[1]])
        c=asyncio.run(core.generate(genp,'C',['A'],omega_rows(ta),[BOTH[1]],baseline_rows=omega_rows(base)))
        if c['valid']:run(p,'G','AC',['A','C'],[BOTH[1]])
        b=asyncio.run(core.generate(genp,'B',[],omega_rows(base),[BOTH[0]]))
        dev={'A':run(p,'D','A',['A'],BOTH)}
        if b['valid']:dev['B']=run(p,'D','B',['B'],[BOTH[0]])
        if c['valid']:dev['AC']=run(p,'D','AC',['A','C'],[BOTH[1]])
        def mean(rows):return sum(r['score'] for r in rows)/len(rows)
        def choose(ns):return sorted([n for n in ns if n in dev],key=lambda n:(-mean(dev[n]),2 if n=='AC' else 1,ns.index(n)))[0]
        selection={'independent':choose(['A','B']),'recursive':choose(['A','AC']),
                   'dev_scores':{n:mean(rs) for n,rs in dev.items()},'protocol_hash':p['hash'],
                   'chain_hashes':{n:json.loads((ROOT/'strategies'/f'{n}.json').read_text())['injection_hash'] for n in ['A','B','C']}}
        core.save(ROOT/'selection.json',selection)
        core.save(ROOT/'test_manifest.json',{'selection_hash':core.digest(selection),'protocol_hash':p['hash'],'reuse_same_chain':True})
        tested={'base':run(p,'T','base',[],[])}
        cache={}
        for branch in ['independent','recursive']:
            n=selection[branch]
            if n not in cache:cache[n]=run(p,'T',n,['A','C'] if n=='AC' else [n],[])
            tested[branch]=cache[n]
        usage=sum(json.loads(line).get('token_usage',{}).get('total_tokens',0) for file in (ROOT/'results').glob('*.jsonl') for line in file.read_text().splitlines())
        usage+=sum(x['token_usage']['total_tokens'] for x in [a,b,c])
        summary={'selection':selection,'test_mean_scores':{n:mean(rs) for n,rs in tested.items()},'physical_tokens':usage,
                 'limitations':['9 fresh task families, one official case file each; small-scale comparison','single search seed','new backbone, not paper numerical replication','continuous normalized scores, not math accuracy'],
                 'paired_test_scores':[{k:v for k,v in zip(tested,vals)} for vals in zip(*[[r['score'] for r in rs] for rs in tested.values()])]}
        core.save(ROOT/'summary.json',summary)
        lines=['# CO-Bench 资源契约修正后的对照实验','',f"数据：官方 CO-Bench，revision `{p['revision']}`。非合成题。",'',
               '9 类此前未使用的任务，G/D/T 各 3 类；G/D 使用首个官方 dev 文件，T 使用首个非 dev 文件；空测试预检文件已归档排除。',
               '官方连续优化质量得分，不是数学题正确率。仅用于流程验证，不代表完整 CO-Bench 复现。','',
               '|开发候选|平均分|','|---|---:|',*[f'|{n}|{mean(rs):.4f}|' for n,rs in dev.items()],
               '', '|测试组|策略|平均分|','|---|---|---:|',f"|base|base|{mean(tested['base']):.4f}|",
               *[f'|{n}|{selection[n]}|{mean(tested[n]):.4f}|' for n in ['independent','recursive']],
               '',f'物理 token 总数：{usage}。若选中同一链，复用同一批测试输出。',
               '单 seed、极小任务数；不能据此作统计显著性或一般性收益结论。']
        (ROOT/'report.md').write_text('\n'.join(lines)+'\n')
        print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
