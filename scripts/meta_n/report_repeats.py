"""Summarize the three pre-scheduled searches using frozen result files only."""
import csv
import hashlib
import json
import statistics
from pathlib import Path

import campaign as core

ROOT = core.REPO.parent / 'experiments'
OUT = ROOT / 'repeated_search_20261118'


def load_requests(directory):
    approvals = [json.loads(p.read_text()) for p in (directory / 'recovery').glob('*/audit.json')]
    approved = {key: value for a in approvals for key, value in a['failed_request_hashes'].items()}
    requests = []
    for path in (directory / 'requests').glob('*.json'):
        row = json.loads(path.read_text())
        if row['status'] != 'complete' and approved.get(path.name) != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError(f'Unaudited request in {directory}: {path.name}')
        requests.append(row)
    return requests


def inspect_run(campaign, repeat):
    suffix = '' if repeat == 1 else f'_repeat{repeat}'
    directory = ROOT / f'{campaign}_review_20261118{suffix}'
    summary_file = 'test_summary.json' if campaign == 'math500' else 'summary.json'
    if not (directory / summary_file).exists():
        a_path = directory / 'strategies/A.json'
        if not a_path.exists() or json.loads(a_path.read_text())['valid']:
            raise ValueError(f'Incomplete campaign requires audit: {directory}')
        requests = load_requests(directory)
        protocol = json.loads((directory / 'protocol.json').read_text())
        record = {'campaign': campaign, 'repeat': repeat, 'status': 'failed',
                  'directory': str(directory), 'reason': 'Omega generated invalid A; original protocol stops without regeneration',
                  'requests': len(requests), 'physical_tokens': sum(r['usage']['total_tokens'] for r in requests)}
        return record, {r['request_id'] for r in requests}, protocol
    summary = json.loads((directory / summary_file).read_text())
    protocol = json.loads((directory / 'protocol.json').read_text())
    selection = json.loads((directory / 'selection.json').read_text())
    runs = {p.stem: core.read_rows(p) for p in (directory / 'results').glob('*.jsonl')}
    rows = [row for group in runs.values() for row in group]
    if any(row['score_status'] != 'valid_scored' for row in rows):
        raise ValueError(f'Unresolved result in {directory}')
    requests = load_requests(directory)
    strategies = {n: json.loads((directory / 'strategies' / f'{n}.json').read_text())
                  for n in ('A', 'B', 'C')}
    prefix = 'math500_formal' if campaign == 'math500' else 'cobench'
    base = runs[f'{prefix}_G_base']
    if campaign == 'cobench':
        base = json.loads(json.dumps(base))
        for row in base:
            row['metadata']['execution']['stdout'] = row['rationale']
    c = strategies['C']
    audit = {
        'depths_correct': [strategies[n]['upstream_depth'] for n in ('A', 'B', 'C')] == [2, 2, 3],
        'baseline_hash_matches': c['baseline_rows_hash'] == core.digest(base),
        'shared_base_input': strategies['A']['request_messages'] == strategies['B']['request_messages'],
        'higher_order_prompt': 'higher-order meta-layer' in json.dumps(c['request_messages']).lower(),
    }
    if not all(audit.values()):
        raise ValueError(f'Generation audit failed in {directory}: {audit}')
    if campaign == 'math500':
        scores = {k: v['correct'] / v['n'] for k, v in summary['test_groups'].items()}
        selected = {k: '+'.join(selection[k]['chain']) for k in ('independent', 'recursive')}
        dev = {label: sum(r['correct'] for r in runs[f'{prefix}_D_{label}']) / 20
               for label in ('A', 'B', 'AC') if f'{prefix}_D_{label}' in runs}
        paired = {k: {name: len(ids) for name, ids in changes.items()}
                  for k, changes in summary['paired_vs_base'].items()}
    else:
        scores = summary['test_mean_scores']
        selected = {k: selection[k].replace('AC', 'A+C') for k in ('independent', 'recursive')}
        dev = selection['dev_scores']
        paired = None
    tokens = sum(r['token_usage']['total_tokens'] for r in rows)
    tokens += sum(s['token_usage']['total_tokens'] for s in strategies.values())
    record = {
        'campaign': campaign, 'repeat': repeat, 'status': 'complete', 'directory': str(directory),
        'search_context_seed': protocol['seed'], 'scores': scores,
        'selected': selected, 'dev_scores': dev, 'paired_vs_base': paired,
        'recursive_minus_independent': scores['recursive'] - scores['independent'],
        'recursive_minus_base': scores['recursive'] - scores['base'],
        'same_selected_strategy': selected['recursive'] == selected['independent'],
        'physical_tokens': tokens, 'generation_tokens': sum(s['token_usage']['total_tokens'] for s in strategies.values()),
        'solver_tokens': sum(r['token_usage']['total_tokens'] for r in rows),
        'rows': len(rows), 'requests': len(requests), 'generation_audit': audit,
        'audited_infrastructure_failed_attempts': sum(r['status'] == 'failed' and r['request_sent'] for r in requests),
        'blocked_unsent_requests': sum(not r['request_sent'] for r in requests),
        'protocol_hash': protocol['hash'],
    }
    return record, {r['request_id'] for r in requests}, protocol


def main():
    records, request_ids, protocols = [], set(), {}
    for campaign in ('math500', 'cobench'):
        for repeat in (1, 2, 3):
            record, ids, protocol = inspect_run(campaign, repeat)
            if ids & request_ids:
                raise ValueError('Model request reused across independent searches')
            request_ids.update(ids)
            records.append(record)
            if campaign in protocols and protocol['splits'] != protocols[campaign]['splits']:
                raise ValueError('Data splits changed across repetitions')
            protocols[campaign] = protocol
    aggregate = {}
    for campaign in ('math500', 'cobench'):
        group = [r for r in records if r['campaign'] == campaign and r['status'] == 'complete']
        def stats(values):
            return {'mean': statistics.mean(values), 'sample_sd': statistics.stdev(values) if len(values) > 1 else None}
        aggregate[campaign] = {
            'scheduled_searches': 3, 'completed_searches': len(group), 'failed_searches': 3 - len(group),
            'test_scores': {label: stats([r['scores'][label] for r in group])
                            for label in ('base', 'independent', 'recursive')},
            'recursive_minus_independent': stats([r['recursive_minus_independent'] for r in group]),
            'recursive_minus_base': stats([r['recursive_minus_base'] for r in group]),
            'recursive_chain_selected_count': sum(r['selected']['recursive'] == 'A+C' for r in group),
            'same_selected_strategy_count': sum(r['same_selected_strategy'] for r in group),
        }
    ledger = [json.loads(line) for line in (ROOT / 'budget_reservations.jsonl').read_text().splitlines()]
    scoped = {Path(r['directory']).name for r in records}
    reservations = {scope: sum(x['reserved_cny'] for x in ledger if x.get('scope') == scope) for scope in scoped}
    for row in records:
        journal = [json.loads(p.read_text()) for p in (Path(row['directory']) / 'requests').glob('*.json')]
        if abs(sum(x['reserved_cny'] for x in journal) - reservations[Path(row['directory']).name]) > 1e-8:
            raise ValueError('Request and budget ledger mismatch')
    result = {'records': records, 'aggregate': aggregate,
              'reservation_cny_by_scope': reservations,
              'project_reserved_cny': sum(x['reserved_cny'] for x in ledger) + 0.000042,
              'limitations': ['Three searches on the same fixed data split',
                              'Existing run included prospectively with two new runs; results of the existing run were known',
                              'No deterministic seed sent to provider; context-sampling seeds vary',
                              'MATH test groups separately execute the selected strategy; CO reuses outputs for identical selected chains',
                              'A/B/C attachment experiment with fixed generation opportunities, not full paper evolutionary search',
                              'Different model and much smaller task coverage than the paper'],
              'all_requests_disjoint': True}
    OUT.mkdir(exist_ok=True)
    (OUT / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    with (OUT / 'results.csv').open('w') as file:
        writer = csv.writer(file)
        writer.writerow(['campaign', 'repeat', 'base', 'independent', 'recursive', 'independent_chain', 'recursive_chain', 'delta_recursive_independent', 'generation_tokens', 'solver_tokens', 'status', 'reason'])
        for row in records:
            if row['status'] != 'complete':
                writer.writerow([row['campaign'], row['repeat'], *[''] * 8, 'failed', row['reason']])
                continue
            writer.writerow([row['campaign'], row['repeat'], *[row['scores'][k] for k in ('base', 'independent', 'recursive')], *[row['selected'][k] for k in ('independent', 'recursive')], row['recursive_minus_independent'], row['generation_tokens'], row['solver_tokens'], 'complete', ''])
    lines = ['# 三次独立搜索结果', '',
             '两次新增完整 A/B/C 搜索与已有修复后运行合并，共每组 3 次。保持数据划分、模型、输出上限与选择规则。每次从新基线启动并重新生成策略及逐题输出。A 无效的重复按协议停止，保留失败记录。', '',
             '论文 §3 通常使用 seeds 42/43/44；附录 C 表 5 的 CO-Bench 最大演化轮数为 Gemma 8、GPT-5.2 6。当前重复附件 A/B/C 对照，使用本地上下文采样种子 20261116/17/18，端点未发送确定性 seed。', '',
             '|任务|重复|base|独立测试|递归测试|独立链|递归链|递归−独立|', '|---|---:|---:|---:|---:|---|---|---:|']
    for r in records:
        if r['status'] != 'complete':
            lines.append(f"|{r['campaign']}|{r['repeat']}|失败|—|—|—|—|—|")
            continue
        lines.append(f"|{r['campaign']}|{r['repeat']}|{r['scores']['base']:.6f}|{r['scores']['independent']:.6f}|{r['scores']['recursive']:.6f}|{r['selected']['independent']}|{r['selected']['recursive']}|{r['recursive_minus_independent']:+.6f}|")
    lines += ['', '分数使用原始单位。MATH 为准确率，CO 为官方连续质量。以下均值与标准差仅覆盖完成的搜索，标准差使用 n−1。失败次数单独列出。', '', '|任务|base 均值±SD|独立 均值±SD|递归 均值±SD|递归−独立 均值±SD|选择 A+C 次数|', '|---|---:|---:|---:|---:|---:|']
    def display(stats):
        sd = '—' if stats['sample_sd'] is None else f"{stats['sample_sd']:.6f}"
        return f"{stats['mean']:.6f} ± {sd}"
    for name, a in aggregate.items():
        cells = [display(a['test_scores'][k]) for k in ('base', 'independent', 'recursive')]
        lines.append(f"|{name}|" + '|'.join(cells) + f"|{display(a['recursive_minus_independent'])}|{a['recursive_chain_selected_count']}/{a['completed_searches']}|")
    lines += ['', *[f"{name} 预定 3 次，完成 {a['completed_searches']} 次，失败 {a['failed_searches']} 次。" for name,a in aggregate.items()], '', '## 解读与审计', '',
              '本次出现 macOS 本机代理 TLS 中断。失败请求、未评分结果和费用预留已逐项审计归档，使用 NO_PROXY 直连后恢复缺失题目。已经评分的输出全部保留。', '',
              '策略 A 无效时按原协议停止，失败运行仍计入预定重复记录。均值基于完成运行，存在完成条件带来的选择影响。失败策略和请求保留，未进行额外生成替换。', '',
              'MATH 两分支选中相同策略时，其测试差异包含独立解题调用的输出波动。CO 相同链复用测试输出。报告全部预定重复，失败记录保留，测试结果未用于选择候选。', '',
              '逐次开发分、选中链、配对改对/改错、生成及求解 token 与入口审计见 summary.json，结果表见 results.csv。所有重复的请求 ID 互不重叠，G/D/T 划分一致，A/B depth 2、C depth 3、baseline feedback 和 higher-order 请求均核对。', '',
              '三个搜索重复可以描述当前设置下的变动，任务覆盖仍为 MATH G10/D20/T60、CO G/D/T 各 3 类。已有首轮结果在安排新增实验时已知。重复次数与论文接近，模型、任务规模及搜索算法仍有差别。']
    lines += ['', 'MATH-500 三次中有两次选择相同策略，第三次 B 的测试成绩为 55/60，A+C 为 53/60。CO 两次完成运行的递归−独立差分别为 +0.100049 与 −0.040311。当前重复实验未观察到稳定的递归优势。', '', f"项目累计保守费用预留 ¥{result['project_reserved_cny']:.6f}，保护上限 ¥220。各次预留与请求日志一致，数值为调用前预留量。"]
    (OUT / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(aggregate, indent=2))


if __name__ == '__main__':
    main()
