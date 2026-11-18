"""Resume a repetition after an explicitly recorded infrastructure-failure audit."""
import hashlib
import json
import os
import sys
from pathlib import Path

import campaign as core
import formal_campaign
import rerun_review


def audit_reservations(scope):
    root = core.REPO.parent / 'experiments' / scope
    approvals = [json.loads(p.read_text()) for p in sorted((root / 'recovery').glob('*/audit.json'))]
    approved = {key: value for approval in approvals for key, value in approval['failed_request_hashes'].items()}
    failures = []
    for path in (root / 'requests').glob('*.json'):
        request = json.loads(path.read_text())
        if request['status'] == 'complete':
            continue
        if approved.get(path.name) != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError(f'Unaudited request failure: {path.name}')
        failures.append(request)
    rows = [row for path in (root / 'results').glob('*.jsonl') for row in core.read_rows(path)]
    recorded = sum(row['metadata']['reserved_cny'] for row in rows if row['score_status'] == 'valid_scored')
    recorded += sum(json.loads(path.read_text())['reserved_cny'] for path in (root / 'strategies').glob('?.json'))
    recorded += sum(request['reserved_cny'] for request in failures)
    ledger = core.REPO.parent / 'experiments/budget_reservations.jsonl'
    reserved = sum(row['reserved_cny'] for row in map(json.loads, ledger.read_text().splitlines()) if row.get('scope') == scope)
    if abs(recorded - reserved) > 1e-8:
        raise ValueError('Unreconciled reservation after infrastructure recovery')


if __name__ == '__main__':
    if '--repeat-id' not in sys.argv:
        raise ValueError('Recovery is restricted to the scheduled repetitions')
    # The macOS localhost system proxy failed TLS. Direct HTTPS was read-only tested.
    os.environ['NO_PROXY'] = ','.join(filter(None, [os.environ.get('NO_PROXY'), 'api.deepseek.com']))
    formal_campaign.audit_reservations = audit_reservations
    rerun_review.main()
