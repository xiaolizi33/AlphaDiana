"""Reconcile ablation raw usage and rebuild metrics, figures and limitations."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from plot_templates import grouped_bar as style
import recursive_ablation as campaign
ROOT=campaign.ROOT

def main():
    comparison=json.loads((ROOT/'comparison.json').read_text());full=comparison['full'];flat=comparison['depth1']
    ledgers=[json.loads(l) for l in (ROOT.parent/'budget_reservations.jsonl').read_text().splitlines()]
    usage={}
    for mode in ['full','depth1']:
        requests=[json.loads(p.read_text()) for p in (ROOT/mode/'requests').glob('*.json')]
        reservations=[r for r in ledgers if r.get('scope')=='deepseek_ablation_'+mode]
        assert len(requests)==len(reservations)
        usage[mode]={'calls':len(requests),'tokens':sum(r.get('usage',{}).get('total_tokens',0) for r in requests),
                     'truncated':sum(r.get('response',{}).get('choices',[{}])[0].get('finish_reason')=='length' for r in requests),
                     'failed_requests':sum(r['status']=='failed' for r in requests),
                     'reserved_cny':sum(r['reserved_cny'] for r in reservations)}
    (ROOT/'usage_audit.json').write_text(json.dumps(usage,indent=2)+'\n')
    style.benchmarks=['Archive-best','Best fixed chain'];style.BEST_METHOD='Full recursive search'
    data={'Four flat draws':[round(100*flat['archive_best_validation'],1),round(100*flat['best_chain_validation'],1)],
          'Full recursive search':[round(100*full['archive_best_validation'],1),round(100*full['best_chain_validation'],1)]}
    fig,ax=plt.subplots(figsize=(7.8,4.6));style.draw_panel(ax,data,['#A9A9A9','#D00000'],['','//'],list(data),'Scaled DeepSeek ablation — validation only',[0,1.3],.78,(-.65,1.95),(1.,1.))
    ax.set_ylabel('Mean normalized score × 100');ax.set_ylim(0,122);ax.set_xlabel('Estimator');fig.tight_layout();fig.savefig(ROOT/'ablation_scores.png',dpi=300);plt.close(fig)
    checkpoint=json.loads((ROOT/'full/checkpoint.json').read_text());history=checkpoint['convergence_history'];oracle=checkpoint['oracle_history']
    fig,ax=plt.subplots(figsize=(7.4,4.4));ax.plot(range(len(history)),history,'o-',color='#5BBCCA',label='Best fixed chain');ax.plot(range(1,len(oracle)+1),oracle,'s-',color='#5B0DAD',label='Archive-best')
    ax.set_xlabel('Completed evolutionary iteration');ax.set_ylabel('Validation normalized score');ax.set_title('Actual archive checkpoints (no smoothing)');ax.set_ylim(0,1.05);ax.legend();ax.tick_params(direction='out');fig.tight_layout();fig.savefig(ROOT/'archive_curve.png',dpi=300);plt.close(fig)
    lines=['# DeepSeek 递归消融流程结果','',
       '复用官方 EvolutionaryOrchestrator；此实验是 DeepSeek、3 类任务、单文件、单 seed、3 轮演化的缩小规模验证。不是论文原模型或原数值复现，也不是等实际算力的因果对照。',
       '完整分支保留策略堆叠、层间上下文和代码库；单层分支为 4 次 temperature=1.0 独立采样，不调用 Ω。两者使用相同官方 dev 数据和每实例 10 秒限制。',
       '', '|分支|Archive-best validation|最佳固定链 validation|','|---|---:|---:|',
       f"|完整递归搜索|{full['archive_best_validation']:.4f}|{full['best_chain_validation']:.4f}|",
       f"|四次单层采样|{flat['archive_best_validation']:.4f}|{flat['best_chain_validation']:.4f}|",
       '', f"Archive-best 差值：{comparison['delta_archive_best']:+.4f}。候选数 {full['archive_size']}，实际完成 {full['iterations']} 轮，最大观测深度 {full['max_observed_depth']}（base=1，depth=3 表示两层策略）。",
       '', '|分支|物理模型调用|token|截断输出|请求错误|保守费用预留 CNY|','|---|---:|---:|---:|---:|---:|',
       *[f"|{m}|{v['calls']}|{v['tokens']}|{v['truncated']}|{v['failed_requests']}|{v['reserved_cny']:.6f}|" for m,v in usage.items()],
       '', '截断输出被保留并判无效，不执行，也没有替换成更好的重采样。完整分支遵循原定演化机会和最多两次执行反馈重试规则。',
       '上述分数均来自参与搜索的 validation；Archive-best 按题取不同候选的最好分数，不等于一条固定链，也不等于未见题泛化。实际 token 不相等，不能把差值全部归因于递归。',
       '服务端未发送确定性 seed；seed=42 只控制本地编排。8k 与 16k 是独立重跑，其基线差异不能归因于输出上限本身。',
       '论文原设置还包括 36 类完整数据、更多演化轮数、三个随机 seed、原始 backbone；当前结果仅验证集成与消融流程。',
       '', '源码变更、离线预检、一次单层截断中断及其恢复均记录在 debug_runs 和 implementation_amendments。所有模型请求/响应、archive 候选、checkpoint、谱系与逐层事件保留。',
       '', '![消融得分](ablation_scores.png)','', '![Archive 曲线](archive_curve.png)']
    if full['max_observed_depth']<3:
        lines.insert(4,'**本轮 archive 没有生成 depth≥3 的候选，即没有实际形成双层策略链。因此本轮只能报告搜索尝试，不能用分差检验高层递归收益。**')
    if (ROOT/'recovery_audit/resolution.json').exists():
        lines.insert(5,'恢复匹配错误造成一次额外模型调用，其输出已排除，原截断按 0 分处理；额外 token 和费用仍计入物理用量。详见 recovery_audit/resolution.json。')
    (ROOT/'report.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'comparison':comparison,'usage':usage},indent=2))
if __name__=='__main__':main()
