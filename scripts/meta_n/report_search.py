"""Rebuild step 2/3 report from saved artifacts; makes no model requests."""
import json
from pathlib import Path
import yaml
from campaign import ROOT, REPO, save, read_rows


def main():
    protocol = json.loads((ROOT/'protocol.json').read_text())
    selection = json.loads((ROOT/'selection.json').read_text())
    groups = {}
    for path in sorted((ROOT/'results').glob('*.jsonl')):
        if path.stem.startswith('T_'):
            continue  # Keep the search snapshot independent of subsequent testing.
        rows = read_rows(path)
        groups[path.stem] = {'n': len(rows), 'correct': sum(bool(r['correct']) for r in rows),
                             'prompt_tokens': sum(r['token_usage']['prompt_tokens'] for r in rows),
                             'completion_tokens': sum(r['token_usage']['completion_tokens'] for r in rows),
                             'total_tokens': sum(r['token_usage']['total_tokens'] for r in rows),
                             'reserved_cny': sum(r['metadata']['reserved_cny'] for r in rows)}
    generation = {}
    for name in ('A', 'B', 'C'):
        r = json.loads((ROOT/'strategies'/f'{name}.json').read_text())
        source_dir = ROOT/'strategies'/name
        source_dir.mkdir(exist_ok=True)
        (source_dir/'pre_process.py').write_text(r['injection']['pre_process'] or '# No preprocessing\n')
        for helper, code in r['injection']['code_library'].items():
            if not helper.isidentifier():
                raise ValueError('Unsafe helper artifact name')
            (source_dir/f'{helper}.py').write_text(code+'\n')
        generation[name] = {'usage': r['token_usage'], 'reserved_cny': r['reserved_cny'],
                            'injection_hash': r['injection_hash'], 'valid': r['valid'], 'parent': r['parent']}
    a = json.loads((ROOT/'strategies/A.json').read_text())
    b = json.loads((ROOT/'strategies/B.json').read_text())
    assert a['source_rows_hash'] == b['source_rows_hash']
    assert a['request_messages'] == b['request_messages']
    def count(keys):
        return sum(groups[k]['total_tokens'] for k in keys)
    omega = {name: r['usage']['total_tokens'] for name, r in generation.items()}
    accounting = {
        'independent': {'omega_tokens': omega['A']+omega['B'], 'feedback_solver_tokens': count(['G_base']),
                        'development_solver_tokens': count(['D_A','D_B']), 'unused_cap_is_not_extra_candidates': True},
        'recursive': {'omega_tokens': omega['A']+omega['C'], 'feedback_solver_tokens': count(['G_base','G_A']),
                      'diagnostic_solver_tokens': count(['G_AC']), 'development_solver_tokens': count(['D_A','D_AC'])}}
    ledger = [json.loads(line) for line in (REPO.parent/'experiments/budget_reservations.jsonl').read_text().splitlines()]
    ledger = [row for row in ledger if row.get('scope') != 'future_test']
    for name, row in accounting.items():
        row['total_tokens_including_diagnostics'] = sum(v for k,v in row.items() if k.endswith('_tokens'))
        charged = [r for r in ledger if name in r.get('branches', [])]
        row['conservative_token_reservations'] = sum(r['token_bound'] for r in charged)
        row['reserved_cny'] = sum(r['reserved_cny'] for r in charged)
    result = {'protocol_hash': protocol['hash'], 'runs': groups, 'generation': generation,
              'branch_accounting': accounting, 'selection': selection,
              'physical_total_tokens': sum(r['total_tokens'] for r in groups.values())+sum(omega.values()),
              'project_reserved_cny_including_preflight': sum(r['reserved_cny'] for r in ledger)+0.000042,
              'test_executed': False, 'budget_extension': json.loads((ROOT/'budget_extension.json').read_text()) if (ROOT/'budget_extension.json').exists() else None}
    save(ROOT/'search_summary.json', result)
    lines = ['# Step 2/3 真实调试结果', '', '本次为合成数学题的工程 pilot，不是正式泛化实验。原 token 预留 cap 下递归分支未完成；两分支共同扩展 cap 后补齐最后一道未请求的开发题。补充结果是探索性的，测试集未执行。', '',
             '|运行|正确数|输入 token|输出 token|', '|---|---:|---:|---:|']
    for name, row in groups.items():
        lines.append(f"|{name}|{row['correct']}/{row['n']}|{row['prompt_tokens']}|{row['completion_tokens']}|")
    lines += ['', '开发选择：', '', f"- 独立搜索：{selection['independent']['winner']}",
              f"- 递归搜索：{selection['recursive']['winner']}", '',
              '两分支共享 A，各自只额外生成一次 B 或 C；相同 cap，不代表实际 token 相同。',
              '共同费用计入各分支比较，但实际总量只计一次；G_AC 为递归诊断额外费用，也计入其 cap。',
              '', '详细用量、分支成本和预算预留见 search_summary.json。']
    (ROOT/'report.md').write_text('\n'.join(lines)+'\n')
    # Prepare final evaluation configs without reading any test model outputs.
    template = yaml.safe_load((ROOT/'configs/D_A.yaml').read_text())
    for label, chain in [('base', []), ('independent', selection['independent']['chain']),
                          ('recursive', selection['recursive']['chain'])]:
        cfg = json.loads(json.dumps(template))
        cfg['run_id'] = f'T_{label}'
        cfg['benchmark']['config']['problems'] = protocol['T']
        cfg['agent']['config']['strategy_chain'] = [str(ROOT/'strategies'/f'{n}.json') for n in chain]
        cfg['agent']['config']['budget_branches'] = []
        cfg['agent']['config']['budget_scope'] = 'future_test'
        cfg['metadata'].update({'split':'T', 'candidate':label, 'selection_hash': selection['dev_results_hash']})
        path = ROOT/'configs'/f'T_{label}.yaml'
        path.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True))
    # Retain a concrete before/after case, including exact prompts and scripts.
    def rows(name):
        return {r['task_id']:r for r in map(json.loads,(ROOT/'results'/f'{name}.jsonl').read_text().splitlines())}
    ar, acr = rows('G_A'), rows('G_AC')
    candidates = [key for key in ar if not ar[key]['correct'] and acr[key]['correct']]
    if candidates:
        key = candidates[0]
        save(ROOT/'case_study.json', {'task_id':key, 'split':'G', 'A':ar[key], 'AC':acr[key],
                                      'note':'Generation-set mechanism example; not held-out evidence'})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
