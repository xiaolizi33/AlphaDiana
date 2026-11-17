"""Independent MATH-500 preflight; freezes excluded pilot IDs before paid calls."""
import argparse
from collections import defaultdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random

from campaign import REPO, digest, read_rows, save
ROOT = REPO.parent/'experiments/math500_preparation'
CONTRACT = ('Implement solve() with no arguments. Return only the final mathematical answer. '
            'For exact fractions, radicals, symbolic expressions, tuples, sets or intervals, return a Python raw string '
            'containing the exact LaTeX answer; do not replace exact values with decimal approximations. '
            'Use only Python standard library; llm/llm_batch and sympy are unavailable. '
            'Output only a fenced Python code block, without prose derivation.')


def prepare():
    if not (ROOT/'test.jsonl').exists():
        import urllib.request
        revision='6e4ed1a2a79af7d8630a6b768ec859cb5af4d3be'
        ROOT.mkdir(parents=True,exist_ok=True)
        with urllib.request.urlopen('https://huggingface.co/api/datasets/HuggingFaceH4/MATH-500/revision/'+revision,timeout=45) as response:
            save(ROOT/'source_info.json',json.load(response))
        for filename in ('README.md','test.jsonl'):
            with urllib.request.urlopen(f'https://huggingface.co/datasets/HuggingFaceH4/MATH-500/resolve/{revision}/{filename}',timeout=45) as response:
                (ROOT/filename).write_bytes(response.read())
    raw=(ROOT/'test.jsonl').read_bytes()
    rows=[json.loads(l) for l in raw.decode().splitlines()]
    assert len(rows)==500
    hashes=[digest(' '.join(r['problem'].split())) for r in rows]
    assert len(set(hashes))==500, 'Duplicate normalized problems'
    path=ROOT/'pilot_manifest.json'
    if path.exists():
        manifest=json.loads(path.read_text())
        assert manifest['snapshot_sha256']==hashlib.sha256(raw).hexdigest()
        return manifest
    rng=random.Random(20261115)
    subjects=defaultdict(list)
    for r in rows:
        subjects[r['subject']].append(r)
    pilot=[]
    for subject, candidates in sorted(subjects.items()):
        rng.shuffle(candidates)
        pilot.append(candidates[0]['unique_id'])
    remaining=[r['unique_id'] for r in rows if r['unique_id'] not in pilot]
    rng.shuffle(remaining)
    pilot.append(remaining.pop())
    info=json.loads((ROOT/'source_info.json').read_text())
    manifest={'dataset':'HuggingFaceH4/MATH-500','revision':info['sha'],
              'snapshot_sha256':hashlib.sha256(raw).hexdigest(),'seed':20261115,
              'pilot_ids':pilot,'formal_pool_ids':remaining,'pilot_excluded_from_formal':True,
              'model':'deepseek-flash','thinking':'disabled','temperature':0,'max_tokens':8192,
              'answer_contract':CONTRACT,'math_verify_version':importlib.metadata.version('math-verify'),
              'license_note':'HF mirror has no license tag; upstream hendrycks/math repository MIT; do not relabel HF snapshot as explicitly MIT licensed',
              'source_card':'https://huggingface.co/datasets/HuggingFaceH4/MATH-500',
              'upstream_license':'https://github.com/hendrycks/math/blob/main/LICENSE'}
    save(path,manifest)
    return manifest


def make_config(manifest):
    return {'run_id':'math500_independent_preflight','agent':{'name':'meta_n','version':'0.3.0',
            'config':{'model':'deepseek-flash','api_base':'https://api.deepseek.com','max_tokens':8192,
                      'input_token_bound':16000,'strategy_chain':[],'execution_timeout':5,
                      'answer_contract':CONTRACT,
                      'budget_ledger':str(REPO.parent/'experiments/budget_reservations.jsonl'),
                      'budget_scope':'math500_preflight','pilot_cap_cny':2,'budget_branches':[]}},
            'benchmark':{'name':'math500','config':{'snapshot':str(ROOT/'test.jsonl'),
                         'sha256':manifest['snapshot_sha256'],'ids':manifest['pilot_ids']}},
            'scorer':{'name':'math_verify','config':{}},'num_samples':1,'max_concurrent':1,
            'output_dir':str(ROOT/'results'),'metadata':{'pilot_manifest_hash':digest(manifest),
                'purpose':'independent_cost_and_scoring_preflight_not_formal_scores'}}


def audit_scores():
    from alphadiana.scorer.math_verify_scorer import math_verify_equal
    rows=[json.loads(l) for l in (ROOT/'test.jsonl').read_text().splitlines()]
    failed=[r['unique_id'] for r in rows if math_verify_equal(r['answer'],r['answer']) is not True]
    pairs=[(r'\frac{1}{2}','0.5',True),(r'\sqrt{12}',r'2\sqrt{3}',True),
           (r'\frac{\sqrt{2}}{2}',r'\frac{1}{\sqrt{2}}',True),
           ('(3,4)','(4,3)',False),('42','43',False),('42','',False)]
    from alphadiana.scorer.math_verify_scorer import MathVerifyScorer
    from alphadiana.benchmarks.base import BenchmarkTask
    from alphadiana.harness.base import AgentResponse
    scorer=MathVerifyScorer()
    observations=[{'expected':a,'predicted':b,'target':target,
                   'actual':scorer.score(BenchmarkTask('check','',a),AgentResponse(answer=b)).correct}
                  for a,b,target in pairs]
    assert all(r['actual'] is r['target'] for r in observations)
    save(ROOT/'scorer_audit.json',{'self_equivalence_count':500-len(failed),'total':500,
                                  'unparsed_or_failed_ids':failed,'regression_checks':observations})
    if failed:
        raise RuntimeError('Unparsed gold answers require review before formal evaluation')


def run(manifest):
    import yaml
    from alphadiana.engine.config.experiment_config import ExperimentConfig
    from alphadiana.engine.config.validator import ConfigValidator
    from alphadiana.engine.runner import Runner
    cfg=make_config(manifest)
    path=ROOT/'preflight.yaml'
    text=yaml.safe_dump(cfg,sort_keys=False,allow_unicode=True)
    if path.exists() and path.read_text()!=text:
        raise ValueError('Frozen preflight config changed')
    path.write_text(text)
    record=ROOT/'results/math500_independent_preflight.jsonl'
    existing=read_rows(record) if record.exists() else []
    if any(r['score_status']!='valid_scored' for r in existing):
        raise RuntimeError('Prior error retained; no automatic paid retry')
    if len(existing)!=len(manifest['pilot_ids']):
        config=ExperimentConfig.from_yaml(str(path))
        assert not ConfigValidator().validate(config)
        runner=Runner(config)
        try:
            runner.setup();runner.run()
        finally:
            runner.teardown()
    rows=read_rows(record)
    assert len(rows)==8 and all(r['score_status']=='valid_scored' for r in rows)
    summary={'n':len(rows),'correct':sum(bool(r['correct']) for r in rows),
             'truncated':sum(r['finish_reason']=='length' for r in rows),
             'execution_failed':sum(r['metadata']['execution']['exit_code']!=0 for r in rows),
             'usage':{k:sum(r['token_usage'][k] for r in rows) for k in ('prompt_tokens','completion_tokens','total_tokens')},
             'wall_time_sec':sum(r['wall_time_sec'] for r in rows),
             'scoring_methods':[r['score_metadata'].get('method') for r in rows],
             'reserved_cny':sum(r['metadata']['reserved_cny'] for r in rows),
             'pilot_manifest_hash':digest(manifest)}
    save(ROOT/'preflight_summary.json',summary)
    print(json.dumps(summary,indent=2))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');args=parser.parse_args()
    os.chdir(REPO)
    manifest=prepare();audit_scores()
    if args.run:
        if not os.environ.get('DEEPSEEK_API_KEY'):
            os.environ['DEEPSEEK_API_KEY']=(REPO.parent/'apikey').read_text().strip().strip("\"'")
        run(manifest)
    else:
        print('Prepared pinned snapshot, 8 excluded pilot IDs, and scorer audit')


if __name__=='__main__':
    main()
