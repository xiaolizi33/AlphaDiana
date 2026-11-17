"""Frozen three-way held-out pilot evaluation and paired report."""
import json
import os
from pathlib import Path

from campaign import ROOT, REPO, digest, freeze, load_chain, read_rows, save

LABELS = ('base', 'independent', 'recursive')


def validate_frozen():
    from alphadiana.engine.config.experiment_config import ExperimentConfig
    from alphadiana.engine.config.validator import ConfigValidator
    protocol = freeze()
    selection = json.loads((ROOT/'selection.json').read_text())
    assert selection['protocol_hash'] == protocol['hash']
    configs = {}
    manifest = {'protocol_hash': protocol['hash'], 'selection_hash': digest(selection),
                'configs': {}, 'purpose': 'held_out_synthetic_pilot',
                'no_strategy_updates': True, 'search_budget_extended': True}
    common = None
    for label in LABELS:
        path = ROOT/'configs'/f'T_{label}.yaml'
        config = ExperimentConfig.from_yaml(str(path))
        errors = ConfigValidator().validate(config)
        if errors:
            raise ValueError(errors)
        assert config.benchmark_config['problems'] == protocol['T']
        assert config.scorer_name == 'numeric'
        assert config.num_samples == config.max_concurrent == 1
        expected = [] if label == 'base' else selection[label]['chain']
        paths = config.agent_config['strategy_chain']
        assert [Path(p).stem for p in paths] == expected
        chain = load_chain(paths)
        if label != 'base':
            assert [digest(ic.model_dump()) for ic in chain] == selection[label]['chain_hashes']
        settings = {k:v for k,v in config.agent_config.items() if k != 'strategy_chain'}
        if common is None:
            common = settings
        assert settings == common
        configs[label] = config
        manifest['configs'][label] = {'yaml_hash': digest(path.read_text()), 'chain': expected,
                                      'chain_hashes': [digest(ic.model_dump()) for ic in chain]}
    save(ROOT/'test_manifest.json', manifest)
    return protocol, configs


def paired(base, method):
    assert set(base) == set(method)
    return {'fixed': [k for k in base if not base[k]['correct'] and method[k]['correct']],
            'regressed': [k for k in base if base[k]['correct'] and not method[k]['correct']],
            'both_correct': [k for k in base if base[k]['correct'] and method[k]['correct']],
            'both_wrong': [k for k in base if not base[k]['correct'] and not method[k]['correct']]}


def report(protocol):
    groups, samples = {}, {}
    for label in LABELS:
        rows = read_rows(ROOT/'results'/f'T_{label}.jsonl')
        if len(rows) != len(protocol['T']) or any(r['score_status'] != 'valid_scored' for r in rows):
            raise RuntimeError('Incomplete evaluation; retain all records without resampling')
        samples[label] = {r['task_id']:r for r in rows}
        usage = {key:sum(r['token_usage'][key] for r in rows)
                 for key in ('prompt_tokens','completion_tokens','total_tokens')}
        groups[label] = {'n':len(rows), 'correct':sum(bool(r['correct']) for r in rows),
                         'accuracy':sum(bool(r['correct']) for r in rows)/len(rows),
                         'usage':usage, 'finish_reasons':[r['finish_reason'] for r in rows],
                         'reserved_cny':sum(r['metadata']['reserved_cny'] for r in rows)}
    comparisons = {label:paired(samples['base'],samples[label]) for label in LABELS[1:]}
    direct = paired(samples['independent'],samples['recursive'])
    search = json.loads((ROOT/'search_summary.json').read_text())
    ledger = [json.loads(line) for line in (REPO.parent/'experiments/budget_reservations.jsonl').read_text().splitlines()]
    result = {'protocol_hash':protocol['hash'], 'test_executed':True, 'test_groups':groups,
              'paired_vs_base':comparisons, 'recursive_vs_independent':direct,
              'search_accounting':search['branch_accounting'],
              'search_physical_tokens':search['physical_total_tokens'],
              'test_physical_tokens':sum(r['usage']['total_tokens'] for r in groups.values()),
              'project_reserved_cny':sum(r['reserved_cny'] for r in ledger)+0.000042,
              'limitations':['8 synthetic template-related test tasks; single search seed',
                            'search reservation cap expanded after partial development results',
                            'provider model alias not immutable version'],
              'per_task':[{ 'task_id':k, **{label:{'predicted':samples[label][k]['predicted'],
                           'correct':samples[label][k]['correct']} for label in LABELS}}
                          for k in samples['base']]}
    save(ROOT/'test_summary.json',result)
    lines = ['# Pilot 测试结果', '', '使用封存的 8 道合成题；策略及开发选择保持不变。', '',
             '|组别|策略|正确数|正确率|相对基线改对|相对基线改错|测试 token|',
             '|---|---|---:|---:|---:|---:|---:|']
    for label,strategy in [('base','无'),('independent','A'),('recursive','A+C')]:
        r=groups[label]; p=comparisons.get(label,{'fixed':[],'regressed':[]})
        lines.append(f"|{label}|{strategy}|{r['correct']}/{r['n']}|{r['accuracy']:.1%}|{len(p['fixed'])}|{len(p['regressed'])}|{r['usage']['total_tokens']}|")
    delta = groups['recursive']['correct'] - groups['independent']['correct']
    baseline_delta = groups['recursive']['correct'] - groups['base']['correct']
    lines += ['', f"本次递归相对独立分支正确数差值为 {delta:+d}，相对基线为 {baseline_delta:+d}；该观察不等于普遍提升。"]
    lines += ['', '## 逐题对照', '', '|题目|基线|A|A+C|', '|---|---|---|---|']
    for row in result['per_task']:
        cells=[f"{row[label]['predicted']}（{'对' if row[label]['correct'] else '错'}）" for label in LABELS]
        lines.append('|'+row['task_id']+'|'+'|'.join(cells)+'|')
    lines += ['', '## 用量', '', '|分支|Ω 生成|生成反馈求解|诊断求解|开发评估|测试求解|',
              '|---|---:|---:|---:|---:|---:|']
    for label in LABELS[1:]:
        a=search['branch_accounting'][label]
        lines.append(f"|{label}|{a['omega_tokens']}|{a['feedback_solver_tokens']}|{a.get('diagnostic_solver_tokens',0)}|{a['development_solver_tokens']}|{groups[label]['usage']['total_tokens']}|")
    lines += ['', f"本次测试物理用量 {result['test_physical_tokens']} token；此前搜索物理用量 {result['search_physical_tokens']} token。",
              '分支表中的共享调用在每条分支分别计入，合计物理用量时只计算一次。',
              f"项目累计保守费用预留 ¥{result['project_reserved_cny']:.6f}，不是账户实际扣款；总 cap 为 ¥50。", '',
              '## 解释范围', '',
              '仅为单 seed、小规模合成题 pilot，题型模板在不同划分间重复，不能据此声称对真实数学题普遍有效。',
              '搜索阶段曾在部分开发结果已知后扩展共同 token 预留 cap，完整对照属于探索性补充。',
              '若出现差异，反映的是本次固定候选和输出上限下的观测；不代表统计显著或论文数值复现。',
              'selection.json 和 search_summary.json 保留为测试前的历史快照，其 test_executed:false 表示快照时状态；当前状态以 test_summary.json 为准。']
    (ROOT/'test_report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


def main():
    from alphadiana.engine.runner import Runner
    os.chdir(REPO)
    protocol,configs=validate_frozen()
    if not os.environ.get('DEEPSEEK_API_KEY'):
        os.environ['DEEPSEEK_API_KEY']=(REPO.parent/'apikey').read_text().strip().strip("\"'")
    for label in LABELS:
        path=ROOT/'results'/f'T_{label}.jsonl'
        if path.exists():
            existing=read_rows(path)
            if len(existing)==len(protocol['T']) and all(r['score_status']=='valid_scored' for r in existing):
                continue
            # Do not automatically retry any already attempted test error.
            if any(r['score_status']!='valid_scored' for r in existing):
                raise RuntimeError('Existing failed test attempt requires audit; no automatic retry')
        runner=Runner(configs[label])
        try:
            runner.setup()
            runner.run()
        finally:
            runner.teardown()
        rows=read_rows(path)
        if any(r['score_status']!='valid_scored' for r in rows):
            raise RuntimeError('Test errors retained; stop without automatic retry')
    report(protocol)


if __name__=='__main__':
    main()
