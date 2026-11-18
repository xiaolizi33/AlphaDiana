"""Execute the frozen MATH-500 search and held-out evaluation, without cap amendments."""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import fcntl
import yaml
import campaign as core

ROOT = core.REPO.parent / 'experiments/math500_formal'
SNAPSHOT = core.REPO.parent / 'experiments/math500_preparation/test.jsonl'
BOTH = ['math500_independent', 'math500_recursive']


def protocol():
    p = json.loads((ROOT/'protocol.json').read_text())
    body = {k:v for k,v in p.items() if k != 'hash'}
    if core.digest(body) != p['hash']:
        raise ValueError('Protocol hash mismatch')
    if hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest() != p['snapshot_sha256']:
        raise ValueError('Snapshot checksum mismatch')
    if importlib.metadata.version('math-verify') != p['math_verify_version']:
        raise ValueError('Scorer version changed')
    source = {r['unique_id']:r for r in map(json.loads, SNAPSHOT.read_text().splitlines())}
    ids, hashes = [], []
    for split in ('G','D','T'):
        for t in p['splits'][split]:
            if core.digest(' '.join(source[t['id']]['problem'].split())) != t['problem_hash']:
                raise ValueError('Task problem changed')
            ids.append(t['id']); hashes.append(t['problem_hash'])
    if len(set(ids)) != len(ids) or len(set(hashes)) != len(hashes) or set(ids)&set(p['excluded_pilot_ids']):
        raise ValueError('Split overlap or duplicate problem')
    # Only generation problems, without gold or reference solutions, reach Omega.
    return p, [{'id':t['id'], 'problem':source[t['id']]['problem']} for t in p['splits']['G']]


def config(p, split, label, chain, branches):
    cfg = core.client_config(branches, protocol=p)
    cfg['halt_file'] = str(ROOT/'request_halted.json')
    cfg['strategy_chain'] = [str(ROOT/'strategies'/f'{n}.json') for n in chain]
    return {'run_id':f'math500_formal_{split}_{label}',
            'agent':{'name':'meta_n','version':'0.3.0','config':cfg},
            'benchmark':{'name':'math500','config':{'snapshot':str(SNAPSHOT),
                'sha256':p['snapshot_sha256'],'ids':[t['id'] for t in p['splits'][split]]}},
            'scorer':{'name':p['scorer'],'config':{}}, 'num_samples':1,
            'max_concurrent':p['max_concurrent'],'output_dir':str(ROOT/'results'),
            'metadata':{'protocol_hash':p['hash'],'split':split,'candidate':label}}


def check_rows(rows, expected, complete=False):
    ids = [r['task_id'] for r in rows]
    if len(ids) != len(set(ids)) or not set(ids) <= set(expected):
        raise ValueError('Unexpected or duplicate task results')
    if any(r.get('score_status') != 'valid_scored' for r in rows):
        raise RuntimeError('Failed attempt retained; stop for audit, without automatic retry')
    if complete and set(ids) != set(expected):
        raise RuntimeError('Incomplete run')


def run(p, split, label, chain, branches):
    from alphadiana.engine.config.experiment_config import ExperimentConfig
    from alphadiana.engine.config.validator import ConfigValidator
    from alphadiana.engine.runner import Runner
    cfg = config(p, split, label, chain, branches)
    path = ROOT/'configs'/f'{split}_{label}.yaml'
    text = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
    if path.exists() and path.read_text() != text:
        raise ValueError('Frozen run config changed')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text)
    result = ROOT/'results'/f'math500_formal_{split}_{label}.jsonl'
    expected = cfg['benchmark']['config']['ids']
    if result.exists():
        rows = core.read_rows(result)
        check_rows(rows, expected)
        if len(rows) == len(expected):
            return rows
    experiment = ExperimentConfig.from_yaml(str(path))
    errors = ConfigValidator().validate(experiment)
    if errors:
        raise ValueError(errors)
    runner = Runner(experiment)
    try:
        runner.setup(); runner.run()
    finally:
        runner.teardown()
    rows = core.read_rows(result)
    check_rows(rows, expected, complete=True)
    print(f'{split}/{label}: {sum(bool(r["correct"]) for r in rows)}/{len(rows)}', flush=True)
    return rows


async def generate(p, tasks, name, parent, rows, branches, baseline_rows=None):
    # Reuse official Omega adaptation with formal settings and no gold-bearing tasks.
    return await core.generate({**p,'G':tasks}, name, parent, rows, branches, baseline_rows=baseline_rows)


def audit_reservations(scope="math500_formal"):
    """A paid request without a durable result must never be silently repeated."""
    ledger = core.REPO.parent/'experiments/budget_reservations.jsonl'
    entries = [r for r in map(json.loads,ledger.read_text().splitlines()) if r.get('scope')==scope]
    recorded = []
    for path in (ROOT/'results').glob('*.jsonl'):
        recorded.extend(r['metadata']['reserved_cny'] for r in core.read_rows(path) if r.get('score_status')=='valid_scored')
    for path in (ROOT/'strategies').glob('?.json'):
        recorded.append(json.loads(path.read_text())['reserved_cny'])
    if abs(sum(r['reserved_cny'] for r in entries)-sum(recorded)) > 1e-8:
        raise RuntimeError('Unreconciled paid reservation; audit required before resume')


def summarize(p, selection, tests):
    groups = {}
    for label, rows in tests.items():
        groups[label] = {'n':len(rows),'correct':sum(bool(r['correct']) for r in rows),
                         'tokens':sum(r['token_usage']['total_tokens'] for r in rows)}
    indexed = {k:{r['task_id']:r for r in v} for k,v in tests.items()}
    def paired(a,b):
        return {'fixed':[k for k in indexed[a] if not indexed[a][k]['correct'] and indexed[b][k]['correct']],
                'regressed':[k for k in indexed[a] if indexed[a][k]['correct'] and not indexed[b][k]['correct']]}
    ledger = list(map(json.loads,(core.REPO.parent/'experiments/budget_reservations.jsonl').read_text().splitlines()))
    accounting = {}
    for branch in BOTH:
        entries = [r for r in ledger if branch in r.get('branches',[])]
        accounting[branch] = {'reserved_cny':sum(r['reserved_cny'] for r in entries),
                             'token_bound':sum(r['token_bound'] for r in entries)}
    runs = {path.stem:core.read_rows(path) for path in (ROOT/'results').glob('*.jsonl')}
    generation = {n:json.loads((ROOT/'strategies'/f'{n}.json').read_text()) for n in ('A','B','C')}
    result = {'protocol_hash':p['hash'],'selection':selection,'test_groups':groups,
              'paired_vs_base':{k:paired('base',k) for k in ('independent','recursive')},
              'recursive_vs_independent':paired('independent','recursive'),
              'branch_reservations':accounting,'project_reserved_cny':sum(r['reserved_cny'] for r in ledger)+0.000042,
              'runs':{k:{'n':len(v),'correct':sum(bool(r['correct']) for r in v),
                         'tokens':sum(r['token_usage']['total_tokens'] for r in v)} for k,v in runs.items()},
              'generation':{n:{k:r[k] for k in ('valid','token_usage','reserved_cny','source_rows_hash')} for n,r in generation.items()},
              'limitations':['Single search seed, 60 test tasks','Public dataset may occur in pretraining','Provider alias is not an immutable model version']}
    core.save(ROOT/'test_summary.json',result)
    lines = ['# MATH-500 正式对照结果','','|组别|链|正确数|准确率|测试 token|','|---|---|---:|---:|---:|']
    for label,g in groups.items():
        chain = [] if label=='base' else selection[label]['chain']
        lines.append(f"|{label}|{' + '.join(chain) or 'base'}|{g['correct']}/{g['n']}|{g['correct']/g['n']:.1%}|{g['tokens']}|")
    lines += ['','单 seed、60 道测试题；结果不能直接支持普遍提升。逐题配对变化、搜索用量和预算见 test_summary.json。']
    (ROOT/'test_report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(groups,ensure_ascii=False,indent=2))


def execute(stage):
    core.ROOT = ROOT
    p,tasks = protocol()
    audit_reservations()
    if (ROOT/'request_halted.json').exists():
        raise RuntimeError('Prior request error requires audit; see request_halted.json')
    # Freeze implementation and upstream identity before the first formal request.
    files = [Path(__file__),Path(core.__file__),*sorted((core.REPO/'alphadiana/harness/meta_n').glob('*.py'))]
    import subprocess
    core.save(ROOT/'implementation.json',{'protocol_hash':p['hash'],
        'files':{str(f.relative_to(core.REPO)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
        'meta_n_commit':subprocess.check_output(['git','-C',str(core.REPO.parent/'meta-n'),'rev-parse','HEAD'],text=True).strip()})
    if stage=='validate':
        print('Protocol, snapshot, splits, scorer, budget ledger and implementation validated.'); return
    if not os.environ.get('DEEPSEEK_API_KEY'):
        os.environ['DEEPSEEK_API_KEY']=(core.REPO.parent/'apikey').read_text().strip().strip("\"'")
    os.chdir(core.REPO)
    base=run(p,'G','base',[],BOTH)
    a=asyncio.run(generate(p,tasks,'A',[],base,BOTH))
    if not a['valid']:
        raise RuntimeError('A invalid; retain output and stop without repair')
    ta=run(p,'G','A',['A'],[BOTH[1]])
    c=asyncio.run(generate(p,tasks,'C',['A'],ta,[BOTH[1]],baseline_rows=base))
    if c['valid']:
        run(p,'G','AC',['A','C'],[BOTH[1]])
    b=asyncio.run(generate(p,tasks,'B',[],base,[BOTH[0]]))
    rows={'A':run(p,'D','A',['A'],BOTH)}
    rows['B']=run(p,'D','B',['B'],[BOTH[0]]) if b['valid'] else rows['A']
    rows['AC']=run(p,'D','AC',['A','C'],[BOTH[1]]) if c['valid'] else rows['A']
    selection=core.select({**p,'D':p['splits']['D']},rows)
    if stage=='search': return
    # Freeze all test configurations and chosen strategy hashes before reading T outputs.
    configs={label:config(p,'T',label,chain,[]) for label,chain in
             [('base',[]),('independent',selection['independent']['chain']),('recursive',selection['recursive']['chain'])]}
    for label in ('independent','recursive'):
        chain=core.load_chain(configs[label]['agent']['config']['strategy_chain'])
        if [core.digest(ic.model_dump()) for ic in chain] != selection[label]['chain_hashes']:
            raise ValueError('Selected strategy changed')
    core.save(ROOT/'test_manifest.json',{'protocol_hash':p['hash'],'selection_hash':core.digest(selection),'configs':configs})
    tests={label:run(p,'T',label,[] if label=='base' else selection[label]['chain'],[]) for label in configs}
    summarize(p,selection,tests)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=['validate','search','all'],default='all')
    args=parser.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True)
    with (ROOT/'campaign.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            execute(args.stage)
        except Exception as exc:
            (ROOT/'incomplete.json').write_text(json.dumps({'status':'incomplete','error':str(exc)},ensure_ascii=False,indent=2)+'\n')
            raise
        else:
            (ROOT/'incomplete.json').unlink(missing_ok=True)


if __name__=='__main__':
    main()
