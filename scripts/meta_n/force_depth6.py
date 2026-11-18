"""Continue the recorded natural stopping point as a labeled fixed-depth diagnostic."""
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
from deepen_math import ROOT as NATURAL, metric, generation_audit

ROOT = NATURAL.with_name(NATURAL.name + '_forced')
ORIGINAL_CONFIG = core.client_config
DIRECTIVE = (
    'This is an explicitly forced-depth diagnostic, requested to inspect a six-strategy-layer stack. '
    'The natural stopping signal at three strategy layers has already been recorded. '
    'For this continuation, emit a NONEMPTY, executable pre_process and/or solver_lib block in the official output schema, '
    'even when the observed G sample is saturated. Propose a conservative reusable robustness intervention grounded in the '
    'supplied code and traces. Preserve the stated execution/resource contract. '
    'Explain that its benefit on unseen tasks is uncertain. Do not claim a measured gain or use unavailable task answers. '
    'For this diagnostic, the earlier instruction permitting an empty response is superseded by this fixed-depth requirement.'
)


def config(branches, omega=False, protocol=None):
    result = ORIGINAL_CONFIG(branches, omega=omega, protocol=protocol)
    result.update(budget_scope=ROOT.name, budget_branches=[], global_cap_cny=250,
                  pilot_cap_cny=85, request_timeout_seconds=180,
                  request_log_dir=str(ROOT / 'requests'), halt_file=str(ROOT / 'request_halted.json'))
    amendment = ROOT / 'input_capacity_amendment.json'
    if omega and amendment.exists():
        result['input_token_bound'] = json.loads(amendment.read_text())['omega_input_bound']
    return result


def prepare():
    path = ROOT / 'protocol.json'
    if path.exists():
        protocol = json.loads(path.read_text())
        if core.digest({k: v for k, v in protocol.items() if k != 'hash'}) != protocol['hash']:
            raise ValueError('Protocol checksum changed')
    else:
        protocol = json.loads((NATURAL / 'protocol.json').read_text())
        natural_hash = protocol.pop('hash')
        protocol.update(purpose='forced_nonempty_continuation_after_recorded_natural_stop',
                        natural_protocol_hash=natural_hash, natural_stop_strategy_layers=3,
                        natural_empty_draws=['L4_attempt1', 'L4_attempt2'],
                        new_layers=[4, 5, 6], generation_directive=DIRECTIVE,
                        forced_generation_is_paper_departure=True)
        protocol['hash'] = core.digest(protocol)
        core.save(path, protocol)
    sources = {}
    for source in (NATURAL / 'imported').glob('**/*'):
        if source.is_file():
            sources[str(Path('imported') / source.relative_to(NATURAL / 'imported'))] = source
    for label in ['A', 'C', 'L3_attempt1']:
        sources[f'strategies/{label}.json'] = NATURAL / 'strategies' / f'{label}.json'
    for split, label in [('D', 'L0'), ('G', 'L3'), ('D', 'L3')]:
        name = f'math500_formal_{split}_{label}.jsonl'
        sources[f'imported/results/{name}'] = NATURAL / 'results' / name
    manifest = {name: hashlib.sha256(source.read_bytes()).hexdigest() for name, source in sources.items()}
    core.save(ROOT / 'IMPORT_MANIFEST.json', manifest)
    for name, source in sources.items():
        target = ROOT / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != manifest[name]:
            raise ValueError(f'Imported evidence changed: {name}')
    return protocol


def rows(split, depth):
    label = {1: 'A', 2: 'AC'}.get(depth, 'base' if split == 'G' and depth == 0 else f'L{depth}')
    return core.read_rows(ROOT / 'imported/results' / f'math500_formal_{split}_{label}.jsonl')


def audit_budget():
    ledger = [json.loads(line) for line in (core.REPO.parent / 'experiments/budget_reservations.jsonl').read_text().splitlines()]
    reserved = sum(r['reserved_cny'] for r in ledger if r.get('scope') == ROOT.name)
    requests = [json.loads(p.read_text()) for p in (ROOT / 'requests').glob('*.json')]
    approved = {}
    for path in (ROOT / 'recovery').glob('*/audit.json'):
        approved.update(json.loads(path.read_text())['failed_request_hashes'])
    for path in (ROOT / 'requests').glob('*.json'):
        request = json.loads(path.read_text())
        if request['status'] != 'complete':
            if (request['request_sent'] or request['reserved_cny'] or
                    approved.get(path.name) != hashlib.sha256(path.read_bytes()).hexdigest()):
                raise ValueError('Request failure requires audit before resume')
    if abs(sum(r['reserved_cny'] for r in requests) - reserved) > 1e-8:
        raise ValueError('Request journals and reservations differ')
    recorded = sum(r['metadata']['reserved_cny'] for p in (ROOT / 'results').glob('*.jsonl') for r in core.read_rows(p) if r['score_status'] == 'valid_scored')
    for path in (ROOT / 'strategies').glob('L*.json'):
        value = json.loads(path.read_text())
        if path.stem != 'L3_attempt1' and isinstance(value, dict) and 'injection' in value:
            recorded += value['reserved_cny']
    if abs(recorded - reserved) > 1e-8:
        raise ValueError('Paid output missing from durable result records')


def execute(stage):
    protocol = prepare()
    core.ROOT = ROOT
    formal.ROOT = ROOT
    core.client_config = config
    _, tasks = formal.protocol()
    audit_budget()
    sources = [Path(__file__), Path(core.__file__), Path(formal.__file__),
               *sorted((core.REPO / 'alphadiana/harness/meta_n').glob('*.py'))]
    implementation = {'files': {str(p.relative_to(core.REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    saved = ROOT / 'implementation.json'
    if saved.exists() and json.loads(saved.read_text()) != implementation:
        core.save(ROOT / 'implementation_amendments' / f'{core.digest(implementation)}.json', {
            'original': json.loads(saved.read_text()), 'current': implementation,
            'reason': 'Audited unsent input-capacity refusal; larger Omega capacity and zero-cost failure reconciliation'})
    else:
        core.save(saved, implementation)
    if stage == 'validate':
        formal.config(protocol, 'G', 'L4', ['A', 'C', 'L3_attempt1'], [])
        print('Forced-depth continuation and imported three-layer chain validated.'); return
    if not os.environ.get('DEEPSEEK_API_KEY'):
        os.environ['DEEPSEEK_API_KEY'] = (core.REPO.parent / 'apikey').read_text().strip().strip("\"'")
    os.environ['NO_PROXY'] = ','.join(filter(None, [os.environ.get('NO_PROXY'), 'api.deepseek.com']))
    os.chdir(core.REPO)
    generation = {d: rows('G', d) for d in range(4)}
    development = {d: rows('D', d) for d in range(4)}
    chain = ['A', 'C', 'L3_attempt1']
    chains = {0: [], 1: ['A'], 2: ['A', 'C'], 3: list(chain)}
    for depth in [4, 5, 6]:
        for attempt in [1, 2]:
            name = f'L{depth}_attempt{attempt}'
            record = asyncio.run(core.generate({**protocol, 'G': tasks}, name, chain, generation[depth - 1], [], baseline_rows=generation[depth - 2]))
            audit = generation_audit(record, generation[depth - 1], generation[depth - 2], depth)
            audit['forced_nonempty_directive_present'] = DIRECTIVE in json.dumps(record['request_messages'], ensure_ascii=False)
            if not audit['forced_nonempty_directive_present']:
                raise ValueError('The forced-generation condition was absent from the actual request')
            core.save(ROOT / 'audits' / f'{name}.json', audit)
            if record['valid']:
                break
        if not record['valid']:
            raise RuntimeError(f'No executable strategy at forced layer {depth}')
        chain = [*chain, name]
        chains[depth] = list(chain)
        generation[depth] = formal.run(protocol, 'G', f'L{depth}', chain, [])
        development[depth] = formal.run(protocol, 'D', f'L{depth}', chain, [])
        expected = [i + 2 for i, injection in reversed(list(enumerate(core.load_chain([ROOT / 'strategies' / f'{n}.json' for n in chain])))) if injection.pre_process]
        for row in generation[depth] + development[depth]:
            if row['metadata']['strategy_depth'] != depth or [e['depth'] for e in row['metadata']['layer_events']] != expected:
                raise ValueError('Actual runtime stack differs from the installed chain')
        core.save(ROOT / 'rounds' / f'L{depth}.json', {'chain': chain, 'G': metric(generation[depth]), 'D': metric(development[depth]),
                  'generation_audit': audit, 'runtime_layer_order': expected})
        print(f'FORCED ROUND {depth}/6 G={metric(generation[depth])["correct"]}/10 D={metric(development[depth])["correct"]}/20', flush=True)
    best = min(development, key=lambda d: (-metric(development[d])['accuracy'], d))
    selection = {'best_depth': best, 'chain': chains[best], 'protocol_hash': protocol['hash'],
                 'development': {str(d): metric(r) for d, r in development.items()}}
    core.save(ROOT / 'selection.json', selection)
    core.save(ROOT / 'test_manifest.json', {'protocol_hash': protocol['hash'], 'selection_hash': core.digest(selection), 'depth6_chain': chains[6], 'best_chain': chains[best]})
    test6 = formal.run(protocol, 'T', 'L6', chains[6], [])
    if any(r['metadata']['strategy_depth'] != 6 or [e['depth'] for e in r['metadata']['layer_events']] != expected for r in test6):
        raise ValueError('The test did not execute the full six-layer stack')
    if best == 6:
        best_test = test6
    elif best in [0, 2]:
        label = 'base' if best == 0 else 'recursive'
        best_test = core.read_rows(ROOT / 'imported/results' / f'math500_formal_T_{label}.jsonl')
    else:
        best_test = formal.run(protocol, 'T', f'L{best}', chains[best], [])
    baseline = core.read_rows(ROOT / 'imported/results/math500_formal_T_base.jsonl')
    journals = [json.loads(p.read_text()) for root in [ROOT, NATURAL] for p in (root / 'requests').glob('*.json')]
    summary = {'protocol_hash': protocol['hash'], 'strategy_layers': 6, 'upstream_depth': 7,
               'starting_imported_layers': 2, 'new_layers_generated': 4, 'natural_stop_strategy_layers': 3,
               'forced_generation_started_at_layer': 4, 'natural_phase_root': str(NATURAL),
               'rounds': {str(d): {'G': metric(generation[d]), 'D': metric(development[d])} for d in range(7)},
               'development_best_depth': best, 'test': {'source_base': metric(baseline), 'depth6': metric(test6), 'development_best': metric(best_test)},
               'new_physical_tokens': sum((r.get('usage') or {}).get('total_tokens', 0) for r in journals),
               'new_reserved_cny': sum(r['reserved_cny'] for r in journals),
               'limitations': ['Natural Omega emitted no-op twice at strategy layer4 after saturated G scores; layers4..6 use an explicit nonempty-generation directive',
                               'A single chain with a previously observed test split and no new budget-matched flat control']}
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
