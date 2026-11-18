"""Extend the third reviewed MATH search from two to six nested strategies."""
import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import shutil
from pathlib import Path

import campaign as core
import formal_campaign as formal

ROOT = core.REPO.parent / 'experiments/math500_depth6_20261118'
SOURCE = core.REPO.parent / 'experiments/math500_review_20261118_repeat3'
SCOPE = ROOT.name
ORIGINAL_CONFIG = core.client_config


def client_config(branches, omega=False, protocol=None):
    config = ORIGINAL_CONFIG(branches, omega=omega, protocol=protocol)
    config.update(budget_scope=SCOPE, budget_branches=[], global_cap_cny=250,
                  pilot_cap_cny=85, request_timeout_seconds=180, request_log_dir=str(ROOT / 'requests'),
                  halt_file=str(ROOT / 'request_halted.json'))
    return config


def freeze():
    path = ROOT / 'protocol.json'
    if path.exists():
        protocol = json.loads(path.read_text())
        if core.digest({k: v for k, v in protocol.items() if k != 'hash'}) != protocol['hash']:
            raise ValueError('Protocol checksum changed')
        return protocol
    source = json.loads((SOURCE / 'protocol.json').read_text())
    imported = ['strategies/A.json', 'strategies/C.json']
    imported += [f'results/math500_formal_{split}_{label}.jsonl'
                 for split, label in [('G', 'base'), ('G', 'A'), ('G', 'AC'),
                                      ('D', 'A'), ('D', 'AC'), ('T', 'base'), ('T', 'recursive')]]
    protocol = {k: source[k] for k in [
        'dataset', 'revision', 'snapshot_sha256', 'seed', 'splits', 'excluded_pilot_ids',
        'model', 'temperature_solver', 'temperature_omega', 'thinking', 'solver_max_tokens',
        'omega_max_tokens', 'answer_contract', 'scorer', 'math_verify_version',
        'max_concurrent', 'execution_timeout']}
    protocol.update(
        purpose='single_chain_depth_extension_from_reviewed_repeat3',
        source_directory=str(SOURCE), source_protocol_hash=source['hash'],
        source_choice='User selected the third reviewed search; retain A+C and add four outer layers',
        imported_files={name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() for name in imported},
        solver_input_bound=64000, omega_input_bound=160000,
        formal_scope_cny_reservation_cap=85, project_cny_reservation_cap=250,
        branch_search_token_reservation_cap=2000000, branch_search_cny_reservation_cap=85,
        starting_strategy_layers=2, target_strategy_layers=6, target_upstream_depth=7,
        new_layers=[3, 4, 5, 6], max_generation_attempts_per_layer=2,
        max_solver_calls=260, max_omega_calls=8,
        selection='Highest development accuracy among depths 0..6; ties prefer shallower depth',
        continuation='Always extend the last valid chain through six layers, including after a score decrease',
        generation='Official Omega sees G traces, complete ancestor source, current scores and pre-parent baseline scores',
        test_policy='Freeze depth selection after D; test depth6 and development-best; reuse source baseline T and best-depth2 T if selected',
        previously_observed_test=True, provider_seed_sent=False,
        evaluation_note='Exploratory extension after prior test results were known; no new independent held-out split',
        failure_policy='Keep invalid generation attempts and all costs; at most two draws per new layer; audit infrastructure failures before resume',
        worst_case_new_reservation_cny=80.105472,
        prior_reserved_cny=sum(json.loads(line)['reserved_cny'] for line in
                               (core.REPO.parent / 'experiments/budget_reservations.jsonl').read_text().splitlines()) + .000042,
    )
    protocol['hash'] = core.digest(protocol)
    core.save(path, protocol)
    return protocol


def import_records(protocol):
    for name, checksum in protocol['imported_files'].items():
        source = SOURCE / name
        if hashlib.sha256(source.read_bytes()).hexdigest() != checksum:
            raise ValueError(f'Imported evidence changed: {name}')
        target = ROOT / 'imported' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
            raise ValueError(f'Imported copy changed: {name}')
    for name in ['A', 'C']:
        source = ROOT / 'imported/strategies' / f'{name}.json'
        target = ROOT / 'strategies' / source.name
        target.parent.mkdir(exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        if source.read_bytes() != target.read_bytes():
            raise ValueError('Imported strategy changed')
    def rows(split, label):
        return core.read_rows(ROOT / 'imported/results' / f'math500_formal_{split}_{label}.jsonl')
    return {0: rows('G', 'base'), 1: rows('G', 'A'), 2: rows('G', 'AC')}, {1: rows('D', 'A'), 2: rows('D', 'AC')}


def audit_budget():
    approved = {}
    for path in (ROOT / 'recovery').glob('*/audit.json'):
        approved.update(json.loads(path.read_text())['failed_request_hashes'])
    recorded = 0.
    for path in (ROOT / 'results').glob('*.jsonl'):
        recorded += sum(r['metadata']['reserved_cny'] for r in core.read_rows(path)
                        if r['score_status'] == 'valid_scored' and r.get('score') is not None)
    for path in (ROOT / 'strategies').glob('L*.json'):
        record = json.loads(path.read_text())
        if isinstance(record, dict) and 'injection' in record:
            recorded += record['reserved_cny']
    for path in (ROOT / 'requests').glob('*.json'):
        request = json.loads(path.read_text())
        if request['status'] != 'complete':
            if approved.get(path.name) != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError(f'Unreviewed request failure: {path.name}')
            recorded += request['reserved_cny']
    ledger = [json.loads(line) for line in (core.REPO.parent / 'experiments/budget_reservations.jsonl').read_text().splitlines()]
    reserved = sum(r['reserved_cny'] for r in ledger if r.get('scope') == SCOPE)
    if abs(recorded - reserved) > 1e-8:
        raise ValueError('Paid requests are not fully reconciled with saved outputs')


def metric(rows):
    return {'n': len(rows), 'correct': sum(bool(r['correct']) for r in rows),
            'accuracy': sum(bool(r['correct']) for r in rows) / len(rows),
            'tokens': sum(r['token_usage']['total_tokens'] for r in rows)}


def generation_audit(record, parent_rows, baseline_rows, depth):
    audit = {
        'strategy_layers': depth, 'upstream_depth': record['upstream_depth'],
        'upstream_depth_correct': record['upstream_depth'] == depth + 1,
        'current_rows_match': record['source_rows_hash'] == core.digest(parent_rows),
        'pre_parent_rows_match': record['baseline_rows_hash'] == core.digest(baseline_rows),
        'higher_order_prompt': 'higher-order meta-layer' in json.dumps(record['request_messages']).lower(),
    }
    if not all(audit[k] for k in ['upstream_depth_correct', 'current_rows_match', 'pre_parent_rows_match', 'higher_order_prompt']):
        raise ValueError(f'Omega entry audit failed: {audit}')
    return audit


def execute(stage):
    protocol = freeze()
    import_records(protocol)
    formal.ROOT = ROOT
    core.ROOT = ROOT
    core.client_config = client_config
    _, tasks = formal.protocol()
    audit_budget()
    sources = [Path(__file__), Path(core.__file__), Path(formal.__file__),
               *sorted((core.REPO / 'alphadiana/harness/meta_n').glob('*.py'))]
    implementation = {'protocol_hash': protocol['hash'],
                      'files': {str(p.relative_to(core.REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    saved = ROOT / 'implementation.json'
    if saved.exists() and json.loads(saved.read_text()) != implementation:
        core.save(ROOT / 'implementation_amendments' / f'{core.digest(implementation)}.json', {
            'original': json.loads(saved.read_text()), 'current': implementation,
            'reason': 'Logged metadata recovery and opt-in fixed-depth support after natural convergence; existing outputs retained'})
    else:
        core.save(saved, implementation)
    formal.config(protocol, 'D', 'L0', [], [])
    if stage == 'validate':
        print('Frozen protocol, source chain, split and budget validated; no model calls.'); return
    if (ROOT / 'request_halted.json').exists():
        raise ValueError('Prior request failure requires audit before resume')
    if not os.environ.get('DEEPSEEK_API_KEY'):
        os.environ['DEEPSEEK_API_KEY'] = (core.REPO.parent / 'apikey').read_text().strip().strip("\"'")
    os.environ['NO_PROXY'] = ','.join(filter(None, [os.environ.get('NO_PROXY'), 'api.deepseek.com']))
    os.chdir(core.REPO)
    generations, development = import_records(protocol)
    chain = ['A', 'C']
    development[0] = formal.run(protocol, 'D', 'L0', [], [])
    for depth in protocol['new_layers']:
        parent_rows, baseline_rows = generations[depth - 1], generations[depth - 2]
        accepted = None
        for attempt in range(1, protocol['max_generation_attempts_per_layer'] + 1):
            name = f'L{depth}_attempt{attempt}'
            record = asyncio.run(core.generate({**protocol, 'G': tasks}, name, chain, parent_rows, [], baseline_rows=baseline_rows))
            audit = generation_audit(record, parent_rows, baseline_rows, depth)
            core.save(ROOT / 'audits' / f'{name}.json', audit)
            if record['valid']:
                accepted = name
                break
        if accepted is None:
            raise RuntimeError(f'Layer {depth} had no valid strategy in the scheduled draws')
        chain = [*chain, accepted]
        generations[depth] = formal.run(protocol, 'G', f'L{depth}', chain, [])
        development[depth] = formal.run(protocol, 'D', f'L{depth}', chain, [])
        expected_events = [index + 2 for index, injection in reversed(list(enumerate(core.load_chain(
                           [ROOT / 'strategies' / f'{name}.json' for name in chain])))) if injection.pre_process]
        for row in generations[depth] + development[depth]:
            if row['metadata']['strategy_depth'] != depth:
                raise ValueError('The actual chain depth differs from the protocol')
            if [event['depth'] for event in row['metadata']['layer_events']] != expected_events:
                raise ValueError('Runtime layer order differs from the installed chain')
        core.save(ROOT / 'rounds' / f'L{depth}.json', {
            'strategy_layers': depth, 'upstream_depth': depth + 1, 'chain': chain,
            'chain_hashes': [json.loads((ROOT / 'strategies' / f'{name}.json').read_text())['injection_hash'] for name in chain],
            'G': metric(generations[depth]), 'D': metric(development[depth]),
            'runtime_layer_order': expected_events, 'generation_audit': audit})
        print(f'ROUND {depth}/6 G={metric(generations[depth])["correct"]}/10 D={metric(development[depth])["correct"]}/20', flush=True)
    best = min(development, key=lambda d: (-metric(development[d])['accuracy'], d))
    chains = {0: [], 1: ['A'], 2: ['A', 'C']}
    chains.update({depth: json.loads((ROOT / 'rounds' / f'L{depth}.json').read_text())['chain'] for depth in protocol['new_layers']})
    selection = {'protocol_hash': protocol['hash'], 'best_depth': best, 'chain': chains[best],
                 'development': {str(d): metric(rows) for d, rows in sorted(development.items())}}
    core.save(ROOT / 'selection.json', selection)
    core.save(ROOT / 'test_manifest.json', {'protocol_hash': protocol['hash'], 'selection_hash': core.digest(selection),
              'depth6_chain': chains[6], 'best_chain': chains[best], 'previous_test_results_known': True})
    test6 = formal.run(protocol, 'T', 'L6', chains[6], [])
    if best == 6:
        test_best = test6
    elif best in [0, 2]:
        label = 'base' if best == 0 else 'recursive'
        test_best = core.read_rows(ROOT / 'imported/results' / f'math500_formal_T_{label}.jsonl')
    else:
        test_best = formal.run(protocol, 'T', f'L{best}', chains[best], [])
    baseline = core.read_rows(ROOT / 'imported/results/math500_formal_T_base.jsonl')
    if any(row['metadata']['strategy_depth'] != 6 or
           [event['depth'] for event in row['metadata']['layer_events']] != expected_events
           for row in test6):
        raise ValueError('Depth-six test did not execute the full installed stack')
    requests = [json.loads(p.read_text()) for p in (ROOT / 'requests').glob('*.json')]
    summary = {'protocol_hash': protocol['hash'], 'strategy_layers': 6, 'upstream_depth': 7,
               'starting_imported_layers': 2, 'new_layers_generated': 4,
               'rounds': {str(d): {'G': metric(generations[d]), 'D': metric(development[d])} for d in range(7)},
               'development_best_depth': best, 'test': {'source_base': metric(baseline), 'depth6': metric(test6), 'development_best': metric(test_best)},
               'new_physical_tokens': sum((r.get('usage') or {}).get('total_tokens', 0) for r in requests),
               'new_reserved_cny': sum(r['reserved_cny'] for r in requests),
               'limitations': ['One chain extension; no budget-matched flat comparator for four extra layers',
                               'Original T was observed before this extension was designed',
                               'First two layers and their evaluations are imported; new calls cover layers 3..6',
                               'Larger input capacity permits longer stacked context; model/output caps/scorer remain fixed']}
    audit_budget()
    core.save(ROOT / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['validate', 'all'], default='validate')
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / 'campaign.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute(args.stage)


if __name__ == '__main__':
    main()
