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

ROOT=core.REPO.parent/'experiments/cobench_paper_smoke'
PREP=core.REPO.parent/'experiments/cobench_preparation'
BOTH=['cobench_independent','cobench_recursive']
CONTRACT='Implement the supplied solve(**kwargs) interface returning its required dictionary. Python standard library only; do not import numpy/scipy/pulp or call llm. Input objects may be numpy arrays, so use indexing/len or tolist(). Do not access files or network. Evaluator invokes solve on optimization instances; do not implement a no-argument numeric answer.'

def freeze():
    tree=json.loads((PREP/'source_tree.json').read_text())
    splits={'G':['Bin packing - one-dimensional','Flow shop scheduling'],
            'D':['Graph colouring','Job shop scheduling'],
            'T':['Open shop scheduling','Aircraft landing']}
    adapter=COBenchAdapter(str(PREP/'data'),task_names=sum(splits.values(),[]))
    tasks={t.metadata['task_name']:t for t in adapter.load_tasks()}
    assert len(tasks)==6
    p={'purpose':'paper_data_engineering_smoke_not_full_paper_replication',
       'dataset':'CO-Bench/CO-Bench','revision':tree['revision'],'seed':20261116,
       'splits':{k:[{'id':tasks[n].task_id,'name':n,'problem':tasks[n].description,'answer':''} for n in ns] for k,ns in splits.items()},
       'files':{str(f.relative_to(PREP)):hashlib.sha256(f.read_bytes()).hexdigest() for n in tasks for f in sorted((PREP/'data'/n).iterdir()) if f.is_file()},
       'data_policy':'one lexicographically first official case file per task; G/D official dev indices; T official test complement; task families disjoint; no generated instances',
       'model':'deepseek-flash','solver_max_tokens':8192,'omega_max_tokens':8192,
       'scope_reservation_cap_cny':6,'branch_reservation_cap_cny':5,
       'branch_token_cap':700000,'answer_contract':CONTRACT,
       'selection':'mean official normalized score; ties shallower then A',
       'test_policy':'same selected chain reuses identical outputs; AC supplemental diagnostic on D only',
       'meta_n_commit':subprocess.check_output(['git','-C',str(core.REPO.parent/'meta-n'),'rev-parse','HEAD'],text=True).strip()}
    p['hash']=core.digest(p); core.save(ROOT/'protocol.json',p)
    return p

def client_config(branches,omega=False,protocol=None):
    return {'model':'deepseek-flash','api_base':'https://api.deepseek.com','max_tokens':8192,
            'input_token_bound':90000 if omega else 24000,
            'budget_ledger':str(core.REPO.parent/'experiments/budget_reservations.jsonl'),
            'budget_scope':'cobench_paper_smoke','pilot_cap_cny':6,
            'budget_branches':branches,'branch_token_cap':700000,'branch_cny_cap':5,
            'answer_contract':CONTRACT,'halt_file':str(ROOT/'request_halted.json')}

def score_config(p,split):
    return {'data_dir':str(PREP/'data'),'eval_split':'test' if split=='T' else 'dev',
            'task_names':{t['id']:t['name'] for ts in p['splits'].values() for t in ts},'evaluation_timeout':180}

def run(p,split,label,chain,branches):
    from alphadiana.engine.config.experiment_config import ExperimentConfig
    from alphadiana.engine.config.validator import ConfigValidator
    from alphadiana.engine.runner import Runner
    result=ROOT/'results'/f'cobench_{split}_{label}.jsonl'
    if result.exists():
        rows=core.read_rows(result)
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
    rows=core.read_rows(result)
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
        core.save(ROOT/'implementation.json',{'files':{str(f.relative_to(core.REPO)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__),Path(core.__file__),*sorted((core.REPO/'alphadiana/harness/meta_n').glob('*.py'))]}})
        if args.stage=='validate':
            for ts in p['splits'].values():
                for t in ts:
                    result=evaluate_program('def solve(**kwargs):\n    return {}',t['name'],score_config(p,'T' if ts is p['splits']['T'] else 'G'))
                    print(t['name'],result['score'],result['feedback'][:160],flush=True)
            print('Infrastructure validation complete; no model requests.');return
        if not os.environ.get('DEEPSEEK_API_KEY'):os.environ['DEEPSEEK_API_KEY']=(core.REPO.parent/'apikey').read_text().strip().strip("\"'")
        os.chdir(core.REPO)
        genp={**p,'G':p['splits']['G']}
        base=run(p,'G','base',[],BOTH)
        a=asyncio.run(core.generate(genp,'A',[],omega_rows(base),BOTH))
        if not a['valid']:raise RuntimeError('A invalid; no repair')
        ta=run(p,'G','A',['A'],[BOTH[1]])
        c=asyncio.run(core.generate(genp,'C',['A'],omega_rows(ta),[BOTH[1]],baseline_rows=omega_rows(base)))
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
        usage=sum(r.get('token_usage',{}).get('total_tokens',0) for r in [*base,*ta,*sum(dev.values(),[]),*tested['base'],*sum(cache.values(),[])])
        usage+=sum(x['token_usage']['total_tokens'] for x in [a,b,c])
        summary={'selection':selection,'test_mean_scores':{n:mean(rs) for n,rs in tested.items()},'physical_tokens':usage,
                 'limitations':['6 task families, one official case file each; engineering smoke only','single search seed','new backbone, not paper numerical replication','continuous normalized scores, not math accuracy'],
                 'paired_test_scores':[{k:v for k,v in zip(tested,vals)} for vals in zip(*[[r['score'] for r in rs] for rs in tested.values()])]}
        core.save(ROOT/'summary.json',summary)
        lines=['# CO-Bench 论文数据小规模流程测试','',f"数据：官方 CO-Bench，revision `{p['revision']}`。非合成题。",'',
               '6 类任务，G/D/T 各 2 类；每类使用字典序第一个官方数据文件。G/D 用官方 dev 索引，T 用官方 test 索引。',
               '官方连续优化质量得分，不是数学题正确率。仅用于流程验证，不代表完整 CO-Bench 复现。','',
               '|开发候选|平均分|','|---|---:|',*[f'|{n}|{mean(rs):.4f}|' for n,rs in dev.items()],
               '', '|测试组|策略|平均分|','|---|---|---:|',f"|base|base|{mean(tested['base']):.4f}|",
               *[f'|{n}|{selection[n]}|{mean(tested[n]):.4f}|' for n in ['independent','recursive']],
               '',f'物理 token 总数：{usage}。若选中同一链，复用同一批测试输出。',
               '单 seed、极小任务数；不能据此作统计显著性或一般性收益结论。']
        (ROOT/'report.md').write_text('\n'.join(lines)+'\n')
        print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
