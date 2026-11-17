"""Freeze a prospective formal protocol after excluded preflight, before G/D/T calls."""
from collections import Counter, defaultdict
import importlib.metadata
import json
import math
import random
from campaign import REPO, digest, save
from prepare_math500 import ROOT, CONTRACT, prepare


def stratified_take(pool, n, rng):
    buckets=defaultdict(list)
    for row in pool:
        buckets[(row['subject'],row['level'])].append(row)
    keys=sorted(buckets)
    rng.shuffle(keys)
    quotas={key:math.floor(n*len(buckets[key])/len(pool)) for key in keys}
    order=sorted(keys,key=lambda key:-(n*len(buckets[key])/len(pool)-quotas[key]))
    for key in order[:n-sum(quotas.values())]:
        quotas[key]+=1
    chosen=[]
    for key in keys:
        rng.shuffle(buckets[key]);chosen.extend(buckets[key][:quotas[key]])
    rng.shuffle(chosen)
    ids={r['unique_id'] for r in chosen}
    return chosen,[r for r in pool if r['unique_id'] not in ids]


def main():
    pilot=prepare()
    summary=json.loads((ROOT/'preflight_summary.json').read_text())
    assert summary['pilot_manifest_hash']==digest(pilot)
    rows=[json.loads(l) for l in (ROOT/'test.jsonl').read_text().splitlines()]
    pool=[r for r in rows if r['unique_id'] in set(pilot['formal_pool_ids'])]
    rng=random.Random(20261116)
    splits={}
    for label,n in [('G',10),('D',20),('T',60)]:
        chosen,pool=stratified_take(pool,n,rng)
        splits[label]=[{'id':r['unique_id'],'problem_hash':digest(' '.join(r['problem'].split())),
                        'subject':r['subject'],'level':r['level']} for r in chosen]
    ids=[r['id'] for split in splits.values() for r in split]
    assert len(ids)==len(set(ids))==90 and not set(ids)&set(pilot['pilot_ids'])
    ledger=[json.loads(l) for l in (REPO.parent/'experiments/budget_reservations.jsonl').read_text().splitlines()]
    # All solver calls: base/A/AC on G; A/B/AC on D; base/selected/selected on T.
    solver_calls=3*10+3*20+3*60
    solver_reserve=(16000*3+8192*12)/1e6
    omega_reserve=(80000*3+8192*12)/1e6
    worst=solver_calls*solver_reserve+3*omega_reserve
    spent=sum(r['reserved_cny'] for r in ledger)+0.000042
    assert spent+worst<50
    protocol={'status':'frozen_before_formal_calls','dataset':pilot['dataset'],'revision':pilot['revision'],
              'snapshot_sha256':pilot['snapshot_sha256'],'seed':20261116,'splits':splits,
              'excluded_pilot_ids':pilot['pilot_ids'],'preflight_summary_hash':digest(summary),
              'model':'deepseek-flash','temperature_solver':0,'temperature_omega':0.7,'thinking':'disabled',
              'solver_max_tokens':8192,'omega_max_tokens':8192,
              'solver_input_bound':16000,'omega_input_bound':80000,'answer_contract':CONTRACT,
              'scorer':'math_verify','math_verify_version':importlib.metadata.version('math-verify'),
              'max_concurrent':1,'execution_timeout':5,'max_api_retries':0,
              'selection':'dev accuracy; tie shallower then A first',
              'generation':'A and B independent from identical base G traces; C from A G traces and A source',
              'failure_policy':'no paid regeneration; invalid child falls back to A, invalid A stops; provider error stops for audit; no replacing scored outputs',
              'budget_exhaustion':'stop and report incomplete; no mid-run cap expansion',
              'branch_search_token_reservation_cap':2000000,'branch_search_cny_reservation_cap':12,
              'formal_scope_cny_reservation_cap':41,'project_cny_reservation_cap':50,
              'max_solver_calls':solver_calls,'max_omega_calls':3,
              'formal_worst_case_reserved_cny':worst,'prior_reserved_cny_at_freeze':spent,
              'combined_worst_case_reserved_cny':spent+worst,
              'all_search_calls_including_G_AC_diagnostics_counted':True,
              'shared_calls_counted_in_both_branches_but_once_physically':True,
              'public_dataset_limitation':'Unseen to strategy generation/selection, not necessarily unseen in model pretraining'}
    protocol['hash']=digest(protocol)
    target=REPO.parent/'experiments/math500_formal/protocol.json'
    # Preserve historical budget-at-freeze amounts when replaying preparation.
    if target.exists():
        old=json.loads(target.read_text()); h=old.pop('hash');assert digest(old)==h
        for key in ('prior_reserved_cny_at_freeze','combined_worst_case_reserved_cny'):
            protocol[key]=old[key]
        protocol.pop('hash');protocol['hash']=digest(protocol)
    save(target,protocol)
    print(json.dumps({k:protocol[k] for k in ('hash','max_solver_calls','formal_worst_case_reserved_cny','combined_worst_case_reserved_cny')},indent=2))


if __name__=='__main__':
    main()
