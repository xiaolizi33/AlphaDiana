"""Rebuild corrected comparison tables and curves from immutable raw outputs."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import cobench_corrected as campaign
from plot_templates import grouped_bar as style

ROOT=campaign.ROOT

def main():
    summary=json.loads((ROOT/'summary.json').read_text());selection=summary['selection']
    rows={f.stem.replace('cobench_',''):campaign.read_rows(f) for f in (ROOT/'results').glob('*.jsonl')}
    strategies={n:json.loads((ROOT/'strategies'/f'{n}.json').read_text()) for n in ['A','B','C']}
    def tokens(rs):return sum(r['token_usage']['total_tokens'] for r in rs)
    def omega(n):return strategies[n]['token_usage']['total_tokens']
    token_table={
      'independent':{'omega':omega('A')+omega('B'),'feedback':tokens(rows['G_base']),
                     'diagnostic':0,'dev':tokens(rows['D_A'])+tokens(rows['D_B'])},
      'recursive':{'omega':omega('A')+omega('C'),'feedback':tokens(rows['G_base'])+tokens(rows['G_A']),
                   'diagnostic':tokens(rows['G_AC']),'dev':tokens(rows['D_A'])+tokens(rows['D_AC'])}}
    tests={name:rows['T_'+winner] for name,winner in [('base','base'),('independent',selection['independent']),('recursive',selection['recursive'])]}
    base={r['task_id']:r['score'] for r in tests['base']}
    paired={n:{'quality_improved':sum(r['score']>base[r['task_id']]+1e-12 for r in rs),
               'quality_worsened':sum(r['score']<base[r['task_id']]-1e-12 for r in rs),
               'zero_to_positive':sum(base[r['task_id']]==0 and r['score']>0 for r in rs),
               'positive_to_zero':sum(base[r['task_id']]>0 and r['score']==0 for r in rs)} for n,rs in tests.items() if n!='base'}
    journals=[json.loads(p.read_text()) for p in (ROOT/'requests').glob('*.json')]
    tokens_journal=sum(r.get('usage',{}).get('total_tokens',0) for r in journals)
    ledger=[json.loads(l) for l in (ROOT.parent/'budget_reservations.jsonl').read_text().splitlines()]
    scope=[r for r in ledger if r.get('scope')=='cobench_corrected']
    assert len(scope)==len(journals) and all(r['status']=='complete' for r in journals)
    assert tokens_journal==summary['physical_tokens']
    audit={'physical_calls':len(journals),'physical_tokens':tokens_journal,'token_table':token_table,'paired':paired,
           'reserved_cny':sum(r['reserved_cny'] for r in scope),'ledger_and_responses_reconciled':True}
    (ROOT/'analysis.json').write_text(json.dumps(audit,indent=2)+'\n')
    style.benchmarks=['Held-out tasks'];style.BEST_METHOD='Recursive selection'
    fig,ax=plt.subplots(figsize=(7.4,4.5));data={label:[round(100*summary['test_mean_scores'][key],1)] for label,key in [('Base','base'),('Independent selection','independent'),('Recursive selection','recursive')]}
    style.draw_panel(ax,data,style.COLORS_CMP,style.HATCHES_CMP,list(data),'Corrected comparison (3 held-out task families)',[0],.78,(-.65,.65),(1.0,1.0))
    ax.set_ylabel('Mean normalized score × 100');ax.set_ylim(0,115);ax.set_xlabel('');fig.tight_layout();fig.savefig(ROOT/'test_scores.png',dpi=300);plt.close(fig)
    plt.rcParams.update({'font.family':'sans-serif','text.usetex':False})
    fig,ax=plt.subplots(figsize=(7.5,4.3));points={}
    common=tokens(rows['G_base'])+omega('A')+tokens(rows['D_A'])
    for name,candidate,color in [('independent','B','#5BBCCA'),('recursive','AC','#5B0DAD')]:
        values=token_table[name];end=sum(values.values());ys=[selection['dev_scores']['A'],max(selection['dev_scores']['A'],selection['dev_scores'][candidate])]
        start=common+(tokens(rows['G_A']) if name=='recursive' else 0)
        points[name]={'search_tokens':[start,end],'best_dev_score':ys}
        ax.plot([start,end],ys,'o-',color=color,label=name)
    ax.set_xlabel('Cumulative search tokens (shared costs counted per branch)');ax.set_ylabel('Best development normalized score');ax.set_title('Two evaluated search opportunities; no smoothing');ax.legend();ax.set_ylim(0,1.05);ax.tick_params(direction='out');fig.tight_layout();fig.savefig(ROOT/'search_curve.png',dpi=300);plt.close(fig)
    (ROOT/'curve_data.json').write_text(json.dumps(points,indent=2))
    lines=['# 修正后的附件形式对照','',
           '使用 DeepSeek 与官方 CO-Bench。G/D/T 各 3 个此前未使用的任务类别，每类一个官方文件；该小样本回答附件形式的固定候选比较，不是论文原数值复现。',
           '同一 ResourceContract 同时进入 solver、Ω 和 scorer：每实例 10 秒，helper 合计最多 5 秒。G/D 与 T 类别互斥，T 文件含非空的官方测试实例。',
           '', '|开发候选|平均归一化分数|','|---|---:|',*[f'|{n}|{v:.4f}|' for n,v in selection['dev_scores'].items()],
           '', '|测试组|选择链|平均归一化分数|','|---|---|---:|',f"|base|base|{summary['test_mean_scores']['base']:.4f}|",
           *[f"|{n}|{selection[n]}|{summary['test_mean_scores'][n]:.4f}|" for n in ['independent','recursive']],
           '', '该指标是连续优化质量，不是数学题正确率。同链复用测试输出；不把运行波动解释成递归效应。',
           '', '|搜索分支|Ω token|反馈求解 token|额外 G/AC 诊断 token|开发 token|','|---|---:|---:|---:|---:|',
           *[f"|{n}|{v['omega']}|{v['feedback']}|{v['diagnostic']}|{v['dev']}|" for n,v in token_table.items()],
           '',f"物理调用 {len(journals)} 次，{tokens_journal:,} token。本轮保守费用预留 ¥{audit['reserved_cny']:.6f}，不是实扣账单。共享调用在分支成本中分别计入，物理总量只计一次。",
           '', '相对基线逐任务质量变化：`analysis.json` 包含改善/下降数和零分↔正分转换；它们不等同于标准数学题的改对/改错。',
           '', '基础设施修复：保留原始 PermissionError 行，以独立 score_repairs 文件只重评保存程序；未重新采样模型。总评分时限由官方实例数推导，未改变每实例 10 秒限制。全部源码变更在 implementation_amendments 和 debug_runs 中留档。',
           '', '单 seed、3 个测试任务类别，结果不作统计显著性结论。G/A+C 恢复调度分数属于生成反馈内的机制观察，不能当成独立泛化证据。',
           '', '![测试得分](test_scores.png)','', '![搜索预算曲线](search_curve.png)']
    (ROOT/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(audit,indent=2))
if __name__=='__main__':main()
