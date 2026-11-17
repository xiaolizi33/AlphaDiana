"""Rebuild formal experiment accounting, paired uncertainty and cases without API calls."""
import json
import math
import random
from formal_campaign import ROOT, BOTH, protocol
from campaign import read_rows, digest


def paired(base, method):
    a={r['task_id']:r for r in base}; b={r['task_id']:r for r in method}
    if set(a)!=set(b): raise ValueError('Unpaired tasks')
    fixed=[k for k in a if not a[k]['correct'] and b[k]['correct']]
    lost=[k for k in a if a[k]['correct'] and not b[k]['correct']]
    values=[int(b[k]['correct'])-int(a[k]['correct']) for k in a]
    rng=random.Random(20261116)
    estimates=sorted(sum(rng.choices(values,k=len(values)))/len(values) for _ in range(10000))
    discordant=len(fixed)+len(lost)
    p=min(1.,2*sum(math.comb(discordant,k) for k in range(min(len(fixed),len(lost))+1))/2**discordant)
    return {'fixed':fixed,'regressed':lost,'delta_accuracy':sum(values)/len(values),
            'paired_bootstrap_95_percentile':[estimates[249],estimates[9749]],
            'exact_mcnemar_two_sided_p':p,'bootstrap_seed':20261116,'bootstrap_replicates':10000}


def main():
    p,_=protocol()
    summary=json.loads((ROOT/'test_summary.json').read_text())
    selection=json.loads((ROOT/'selection.json').read_text())
    manifest=json.loads((ROOT/'test_manifest.json').read_text())
    assert summary['protocol_hash']==p['hash']==selection['protocol_hash']==manifest['protocol_hash']
    assert manifest['selection_hash']==digest(selection)
    runs={path.stem.removeprefix('math500_formal_'):read_rows(path) for path in (ROOT/'results').glob('*.jsonl')}
    strategies={n:json.loads((ROOT/'strategies'/f'{n}.json').read_text()) for n in ('A','B','C')}
    assert strategies['A']['source_rows_hash']==strategies['B']['source_rows_hash']
    assert strategies['A']['request_messages']==strategies['B']['request_messages']
    assert strategies['C']['source_rows_hash']==digest(runs['G_A'])
    def tokens(labels):
        return sum(r['token_usage']['total_tokens'] for label in labels if label in runs for r in runs[label])
    accounting={
        'independent':{'omega':sum(strategies[n]['token_usage']['total_tokens'] for n in ('A','B')),
                       'feedback_solver':tokens(['G_base']),'diagnostic_solver':0,
                       'development_solver':tokens(['D_A','D_B']),'test_solver':tokens(['T_independent'])},
        'recursive':{'omega':sum(strategies[n]['token_usage']['total_tokens'] for n in ('A','C')),
                     'feedback_solver':tokens(['G_base','G_A']),'diagnostic_solver':tokens(['G_AC']),
                     'development_solver':tokens(['D_A','D_AC']),'test_solver':tokens(['T_recursive'])}}
    same=selection['independent']['chain_hashes']==selection['recursive']['chain_hashes']
    result={'protocol_hash':p['hash'],'same_selected_strategy':same,'branch_actual_tokens':accounting,
            'physical_tokens':tokens(list(runs))+sum(r['token_usage']['total_tokens'] for r in strategies.values()),
            'paired_vs_base':{label:paired(runs['T_base'],runs[f'T_{label}']) for label in ('independent','recursive')},
            'replicate_comparison' if same else 'method_comparison':paired(runs['T_independent'],runs['T_recursive']),
            'test_failures':{label:{'execution':sum(r['metadata']['execution']['exit_code']!=0 for r in rows),
                                   'truncation':sum(r['finish_reason']=='length' for r in rows)} for label,rows in runs.items() if label.startswith('T_')},
            'interpretation':'Both searches selected A. Test groups are separate single-shot executions of the same strategy; their difference is output variability, not a recursive-method effect.' if same else 'Distinct selected strategies; one seed only.'}
    (ROOT/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    baseline={r['task_id']:r for r in runs['T_base']}
    independent={r['task_id']:r for r in runs['T_independent']}
    keys=[k for k in baseline if not baseline[k]['correct'] and independent[k]['correct']]
    if not keys: keys=[k for k in baseline if baseline[k]['correct']!=independent[k]['correct']]
    if keys:
        key=keys[0]
        case={'task_id':key,'rule':'first baseline error fixed by selected A, otherwise first changed correctness',
              'note':'Mechanism illustration for selected A; not evidence of recursive benefit',
              'rows':{label:next(r for r in runs[f'T_{label}'] if r['task_id']==key) for label in ('base','independent','recursive')}}
        (ROOT/'case_study.json').write_text(json.dumps(case,ensure_ascii=False,indent=2)+'\n')
    lines=['# MATH-500 正式对照结果','','|组别|选中策略|正确数|准确率|测试 token|','|---|---|---:|---:|---:|']
    for label,r in summary['test_groups'].items():
        strategy='base' if label=='base' else '+'.join(selection[label]['chain'])
        lines.append(f"|{label}|{strategy}|{r['correct']}/{r['n']}|{r['correct']/r['n']:.1%}|{r['tokens']}|")
    lines+=['','开发集：A 17/20，B 15/20，A+C 15/20；独立和递归搜索均选择 A。',
            '两组 A 在测试集上分别执行一次，没有重采样替换已评分答案。两组差异反映输出波动，不能归因于递归策略。',
            '','|分支|Ω 生成|反馈求解|G/AC 诊断|开发|测试|','|---|---:|---:|---:|---:|---:|']
    for label,a in accounting.items(): lines.append('|'+label+'|'+'|'.join(str(v) for v in a.values())+'|')
    lines+=['','共享调用在分支表中分别计入，物理总量仅计一次。',
            f"物理总用量 {result['physical_tokens']} token；项目累计保守费用预留 ¥{summary['project_reserved_cny']:.6f}（非账户实扣），上限 ¥50。",'']
    for label,a in result['paired_vs_base'].items():
        lo,hi=a['paired_bootstrap_95_percentile']
        lines.append(f"- {label} 相对 base：改对 {len(a['fixed'])} 题、改错 {len(a['regressed'])} 题；准确率差 {a['delta_accuracy']:+.1%}，配对 bootstrap 95% 区间 [{lo:+.1%}, {hi:+.1%}]。")
    lines+=['','仅单 seed、60 道测试题；公开题集可能存在于预训练数据，模型别名无法保证版本不变。没有观察到开发集选择递归链的证据。',
            '配对统计与失败计数见 analysis.json，完整逐题原始输出位于 results/，案例位于 case_study.json。']
    (ROOT/'test_report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
