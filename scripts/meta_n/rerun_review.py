"""Run the reviewed attachment adapter in independent, auditable campaigns."""
import argparse
import functools
import json
from pathlib import Path

import campaign as core


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--campaign', choices=['math500', 'cobench'], required=True)
    parser.add_argument('--stage', choices=['validate', 'all'], default='all')
    args = parser.parse_args()
    if args.campaign == 'math500':
        import formal_campaign as campaign
        old_root = campaign.ROOT
        scope = 'math500_review_20261118'
        campaign.ROOT = old_root.with_name(scope)
        campaign.BOTH = [scope + '_independent', scope + '_recursive']
        campaign.audit_reservations = functools.partial(campaign.audit_reservations, scope=scope)
        campaign.ROOT.mkdir(parents=True, exist_ok=True)
        protocol_path = campaign.ROOT / 'protocol.json'
        if not protocol_path.exists():
            protocol = json.loads((old_root / 'protocol.json').read_text())
            old_hash = protocol.pop('hash')
            protocol.update(parent_protocol_hash=old_hash,
                            rerun_reason='Reviewed upstream depth and previous_scores fix',
                            project_cny_reservation_cap=150,
                            prior_reserved_cny_at_freeze=sum(
                                row['reserved_cny'] for row in map(json.loads,
                                (core.REPO.parent / 'experiments/budget_reservations.jsonl').read_text().splitlines())))
            protocol['combined_worst_case_reserved_cny'] = (
                protocol['prior_reserved_cny_at_freeze'] + protocol['formal_worst_case_reserved_cny'])
            protocol['hash'] = core.digest(protocol)
            core.save(protocol_path, protocol)
        original_config = core.client_config
    else:
        import cobench_corrected as campaign
        scope = 'cobench_review_20261118'
        campaign.ROOT = campaign.ROOT.with_name(scope)
        campaign.BOTH = [scope + '_independent', scope + '_recursive']
        original_config = campaign.client_config

    def client_config(branches, omega=False, protocol=None):
        config = original_config(branches, omega=omega, protocol=protocol)
        config.update(budget_scope=scope, global_cap_cny=150,
                      halt_file=str(campaign.ROOT / 'request_halted.json'),
                      request_log_dir=str(campaign.ROOT / 'requests'))
        return config

    core.client_config = client_config
    if args.campaign == 'cobench':
        campaign.client_config = client_config
    core.ROOT = campaign.ROOT
    core.save(campaign.ROOT / 'rerun_manifest.json', {
        'reason': 'Upstream base=1, A/B=2, C=3 with pre-parent baseline feedback',
        'historical_root': str(core.REPO.parent / 'experiments' /
                               ('math500_formal' if args.campaign == 'math500' else 'cobench_corrected')),
        'budget_scope': scope, 'global_reservation_guard_cny': 150,
        'entrypoint_sha256': __import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest(),
        'policy': 'Fresh base outputs and strategies, original splits and model parameters'})
    import sys
    sys.argv = [sys.argv[0], '--stage', args.stage]
    campaign.main()


if __name__ == '__main__':
    main()
