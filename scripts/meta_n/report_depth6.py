"""Render the depth-six extension from frozen numeric records and real traces."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import campaign as core
from deepen_math import ROOT


def load_rows(split, depth):
    label = {1: 'A', 2: 'AC'}.get(depth, 'base' if split == 'G' and depth == 0 else f'L{depth}')
    name = f'math500_formal_{split}_{label}.jsonl'
    path = ROOT / 'results' / name
    if not path.exists():
        path = ROOT / 'imported/results' / name
    return core.read_rows(path)


def main():
    summary = json.loads((ROOT / 'summary.json').read_text())
    protocol = json.loads((ROOT / 'protocol.json').read_text())
    if summary['protocol_hash'] != protocol['hash']:
        raise ValueError('Summary and protocol mismatch')
    if summary['strategy_layers'] != 6:
        raise ValueError('Six strategy layers were not reached')
    depths = list(range(7))
    generation = [summary['rounds'][str(d)]['G']['accuracy'] * 100 for d in depths]
    development = [summary['rounds'][str(d)]['D']['accuracy'] * 100 for d in depths]
    plt.rcParams.update({'font.family': 'sans-serif',
                         'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica'],
                         'text.usetex': False})
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(depths, generation, color='#5B0DAD', lw=1.4, marker='o', label='Generation G (10 tasks)')
    ax.plot(depths, development, color='#5BBCCA', lw=1.4, marker='s', label='Development D (20 tasks)')
    ax.axhline(development[0], color='#3D78C2', lw=1.5, ls='--', label='Base development')
    ax.axvline(2.5, color='#777777', lw=1.2, ls='--', alpha=.85, label='Four-layer extension begins')
    ax.set(xlim=(-.15, 6.15), ylim=(-2, 104), xticks=depths,
           xlabel='Accumulated strategy layers (base = 0)', ylabel='Accuracy (%)')
    title = 'One MATH-500 chain; layers 1-2 imported, layers 3-6 newly generated'
    if summary.get('forced_generation_started_at_layer'):
        title = 'One MATH-500 chain; forced nonempty generation at layers 4-6'
        ax.axvline(3.5, color='#C45A2A', lw=1.2, ls=':', label='Forced continuation begins')
    ax.set_title(title, fontsize=11)
    ax.tick_params(direction='out', length=4, width=.8)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(1)
    ax.grid(False)
    ax.legend(loc='lower right', fontsize=9, frameon=True, facecolor='white', edgecolor='#AAAAAA')
    fig.tight_layout(pad=.8)
    fig.savefig(ROOT / 'depth_curve.png', dpi=300, facecolor='white')
    plt.close(fig)
    with (ROOT / 'depth_results.csv').open('w') as file:
        writer = csv.writer(file)
        writer.writerow(['strategy_layers', 'upstream_depth', 'G_correct', 'G_n', 'D_correct', 'D_n', 'origin'])
        for depth in depths:
            row = summary['rounds'][str(depth)]
            writer.writerow([depth, depth + 1, row['G']['correct'], row['G']['n'], row['D']['correct'], row['D']['n'],
                             'imported' if depth in [1, 2] else 'imported G; new D' if depth == 0 else 'new'])
    current = {row['task_id']: row for row in load_rows('G', 6)}
    parent = {row['task_id']: row for row in load_rows('G', 5)}
    changed = [key for key in current if current[key]['correct'] != parent[key]['correct']]
    key = (changed or list(current))[0]
    case = {'task_id': key, 'split': 'G', 'selection_rule': 'First G task with changed correctness from depth5 to depth6; otherwise first G task',
            'posthoc_illustration': True, 'rows': {str(d): next(row for row in load_rows('G', d) if row['task_id'] == key) for d in depths}}
    (ROOT / 'case_trajectory.json').write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
    case_lines = ['# 六层执行代表轨迹', '', f'题目 `{key}`，来自 G 集。案例在运行完成后按明确规则选择，用于查看层间传递。', '',
                  case['rows']['6']['problem'], '', '|策略层数|输出|正确|实际预处理顺序|', '|---:|---|---|---|']
    for depth, row in case['rows'].items():
        events = row['metadata'].get('layer_events', [])
        case_lines.append(f"|{depth}|{row['predicted']}|{row['correct']}|{' → '.join(str(e['depth']) for e in events)}|")
    case_lines += ['', '## 第六层实际上下文传递', '', '|官方层深度|收到的外层上下文字符数|本层输出上下文字符数|', '|---:|---:|---:|']
    for event in case['rows']['6']['metadata']['layer_events']:
        case_lines.append(f"|{event['depth']}|{len(event['outer_context'])}|{len(event['context'])}|")
    case_lines += ['', '完整逐层请求、生成代码、执行程序与轨迹见 case_trajectory.json、strategies/ 和 results/。单条链上的观察不能隔离某条指令的因果效应。']
    (ROOT / 'case_trajectory.md').write_text('\n'.join(case_lines) + '\n')
    phases = [ROOT]
    if summary.get('natural_phase_root'):
        phases.append(Path(summary['natural_phase_root']))
    requests = [json.loads(path.read_text()) for phase in phases for path in (phase / 'requests').glob('*.json')]
    strategy_records = []
    for path in [p for phase in phases for p in (phase / 'strategies').glob('L*.json')]:
        record = json.loads(path.read_text())
        if isinstance(record, dict) and 'injection' in record:
            if path.parent.parent == ROOT and len(phases) > 1 and path.stem == 'L3_attempt1':
                continue
            strategy_records.append(record)
    omega_tokens = sum(r['token_usage']['total_tokens'] for r in strategy_records)
    accounting = {'new_generation_tokens': omega_tokens,
                  'new_solver_tokens': summary['new_physical_tokens'] - omega_tokens,
                  'new_total_tokens': summary['new_physical_tokens'],
                  'new_reservation_cny': summary['new_reserved_cny'],
                  'request_journals': len(requests),
                  'failed_requests': sum(r['status'] != 'complete' for r in requests),
                  'valid_strategy_draws': sum(r['valid'] for r in strategy_records),
                  'nonaccepted_strategy_draws': sum(not r['valid'] for r in strategy_records),
                  'empty_strategy_draws': sum(not r['injection'].get('pre_process') and not r['injection'].get('code_library') for r in strategy_records)}
    (ROOT / 'token_accounting.json').write_text(json.dumps(accounting, indent=2) + '\n')
    lines = ['# MATH-500 累计六层递归扩展', '',
             '按用户指定，从第 3 次修复后实验的 A+C 继续生成四个外层，累计六层策略。前两层与其 G/D 评分沿用原始记录，每个新外层均读取完整祖先策略源码、当前 G 轨迹、当前分数及上一代基线反馈。官方编号为 base=1、六层策略求解器=7。', '',
             '|策略层数|官方深度|G 正确数|D 正确数|来源|', '|---:|---:|---:|---:|---|']
    for depth in depths:
        row = summary['rounds'][str(depth)]
        origin = '沿用' if depth in [1, 2] else 'G 沿用，D 新运行' if depth == 0 else '新增生成并执行'
        lines.append(f"|{depth}|{depth+1}|{row['G']['correct']}/10|{row['D']['correct']}/20|{origin}|")
    base_test = {r['task_id']: r for r in core.read_rows(ROOT / 'imported/results/math500_formal_T_base.jsonl')}
    deep_test = {r['task_id']: r for r in core.read_rows(ROOT / 'results/math500_formal_T_L6.jsonl')}
    if set(base_test) != set(deep_test):
        raise ValueError('Unpaired baseline and depth-six test tasks')
    fixed = [key for key in base_test if not base_test[key]['correct'] and deep_test[key]['correct']]
    regressed = [key for key in base_test if base_test[key]['correct'] and not deep_test[key]['correct']]
    paired = {'fixed': fixed, 'regressed': regressed, 'net_correct_change': len(fixed) - len(regressed)}
    (ROOT / 'paired_test.json').write_text(json.dumps(paired, indent=2) + '\n')
    if fixed:
        task_id = fixed[0]
        test_case = {'selection_rule': 'First baseline test error corrected by the fixed depth-six chain; posthoc illustration',
                     'task_id': task_id, 'rows': {'source_base': base_test[task_id], 'depth6': deep_test[task_id]}}
        (ROOT / 'test_case_trajectory.json').write_text(json.dumps(test_case, ensure_ascii=False, indent=2) + '\n')
    best = summary['development_best_depth']
    lines += ['', f'开发集选中策略层数 {best}，平分时选浅层。深度选择冻结后再执行测试。', '',
              '|测试对象|正确数|准确率|', '|---|---:|---:|']
    for label, row in summary['test'].items():
        lines.append(f"|{label}|{row['correct']}/{row['n']}|{row['accuracy']:.2%}|")
    lines += ['', f"六层链相对保存的基线测试输出改对 {len(fixed)} 题、改错 {len(regressed)} 题，净增加 {len(fixed)-len(regressed)} 题。逐题配对清单见 paired_test.json，事后选择的一个改对测试例子见 test_case_trajectory.json。", '', '![逐层准确率](depth_curve.png)', '',
              f"本阶段新增 {accounting['new_total_tokens']:,} token，其中 Ω 生成 {omega_tokens:,}，求解 {accounting['new_solver_tokens']:,}。新增保守费用预留 ¥{accounting['new_reservation_cny']:.6f}，阶段上限 ¥85，项目累计保护上限 ¥250。沿用前两层的历史消耗未重复计入本阶段。", '',
              '代表题、完整六层上下文传递与输出见 case_trajectory.md 和 case_trajectory.json。每轮 audits/ 和 rounds/ 记录深度、输入来源哈希、实际执行顺序与策略链哈希。', '',
              '## 解释范围', '',
              '这是沿一条既有链连续加深的探索性实验。旧测试集结果在设计扩展前已知，新增策略生成仅使用 G，深度选择仅使用 D。本次没有为四次额外生成机会配置等预算独立搜索对照，也没有新增独立数据划分。', '',
              '为容纳六层源码和指导，输入容量上限提高到 solver 64,000、Ω 160,000 的保守边界；第 6 层 Ω 的输入在发送前超过边界后，经记录调整为 256,000。该边界按 UTF-8 字节数加余量估算，并非实际 token 消耗。模型别名、温度、输出上限和评分器沿用原协议。观察到的质量变化同时包含策略改变和解题采样波动，单次链扩展不能建立一般性的递归收益结论。']
    if summary.get('forced_generation_started_at_layer'):
        lines += ['', '## 自然收敛与固定深度条件', '',
                  '自然生成在策略第 3 层后出现停止信号。请求第 4 层时，Ω 两次明确返回空策略，说明 G10 已达到 10/10、没有观测到可修复失败。两次请求和 rationale 均保留。', '',
                  '为完成用户指定的六层诊断，后续第 4–6 层在官方 Ω 输入末尾增加了要求输出非空可执行策略的指令。实际请求可审计，链中代码和执行均由真实模型生成。这项强制非空条件偏离论文自然停止行为，结果按固定深度探索解读。阶段费用和 token 包含自然阶段、空策略请求及强制继续阶段。']
    (ROOT / 'REPORT.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'test': summary['test'], 'best_depth': best, 'accounting': accounting}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    ROOT = args.root.resolve()
    main()
