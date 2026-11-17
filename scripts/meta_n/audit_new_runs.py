"""Cross-check request IDs, usage and reservations for every new experiment."""
from datetime import datetime,timezone
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]/'experiments'
RUNS={'cobench_corrected':['cobench_corrected'],
      'deepseek_recursive_ablation':['deepseek_ablation_depth1','deepseek_ablation_full'],
      'deepseek_recursive_ablation_16k':['deepseek_ablation_16k_depth1','deepseek_ablation_16k_full']}
def main():
    ledger=[json.loads(l) for l in (ROOT/'budget_reservations.jsonl').read_text().splitlines()]
    audit={}
    for name,scopes in RUNS.items():
        records=[json.loads(p.read_text()) for p in (ROOT/name).glob('**/requests/*.json')]
        reservations=[r for r in ledger if r.get('scope') in scopes]
        assert {r['request_id'] for r in records}=={r['request_id'] for r in reservations}
        assert all(r['status']=='complete' for r in records)
        usage=sum(r.get('usage',{}).get('total_tokens',0) for r in records)
        audit[name]={'physical_calls':len(records),'physical_tokens':usage,
                     'reserved_cny':sum(r['reserved_cny'] for r in reservations),
                     'truncated_outputs':sum(r['response']['choices'][0]['finish_reason']=='length' for r in records),
                     'report':str(ROOT/name/'report.md')}
    audit['totals']={'new_physical_calls':sum(v['physical_calls'] for v in audit.values()),
                     'new_physical_tokens':sum(v['physical_tokens'] for v in audit.values()),
                     'new_reserved_cny':sum(v['reserved_cny'] for v in audit.values()),
                     'project_cumulative_reserved_cny':sum(r['reserved_cny'] for r in ledger)+.000042,
                     'not_actual_provider_billing':True,'utc':datetime.now(timezone.utc).isoformat()}
    (ROOT/'new_runs_audit.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit,indent=2))
if __name__=='__main__':main()
