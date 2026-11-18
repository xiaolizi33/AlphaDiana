# 修复后的 A/B/C 入口重跑

2026-11-18 完成 MATH-500 正式对照和资源契约修正后的 CO-Bench 正式对照。沿用原数据划分、模型别名、输出上限、选择规则和执行资源参数。本次重新调用端点生成 base、A/B/C 和全部评分输出，实验目录独立冻结。

## 入口验证

两组 A/B 的 upstream_depth 为 2，C 为 3。C 的真实请求包含官方 higher-order meta-layer depth 3 提示。baseline_rows_hash 与各自本次 G/base 记录一致。每组的 generation_audit.json 保存核对结果。

31 项 Metaⁿ 测试通过。297 条任务结果均为 valid_scored，303 次请求日志均为 complete。请求预留费用与结果、策略记录核对一致，详见 experiments/review_rerun_audit_20261118.json。

## MATH-500

开发集 A 19/20、B 18/20、A+C 15/20，两条分支均选中 A。沿用原 MATH-500 协议，对相同选中链执行两次独立测试。

|测试执行|选中链|正确数|准确率|
|---|---|---:|---:|
|base|base|44/60|73.33%|
|independent|A|56/60|93.33%|
|recursive|A|52/60|86.67%|

两次 A 执行的差异体现采样变动。此次开发集选择没有采用 C。

完整结果位于 experiments/math500_review_20261118/test_report.md 和 test_summary.json。

## CO-Bench

开发集平均质量 A 为 0.054913，B 为 0，A+C 为 0.341593。独立分支选中 A，递归分支选中 A+C。

|测试组|选中链|平均质量|
|---|---|---:|
|base|base|0.832881|
|independent|A|0.664186|
|recursive|A+C|0.764236|

A+C 相对 A 增加 0.100049，仍低于 base。三类测试任务中，差异来自 Assortment problem，A 为 0，A+C 为 0.300147，base 为 0.498642。

完整结果位于 experiments/cobench_review_20261118/report.md 和 summary.json。

## 运行记录

新增可重复入口 AlphaDiana/scripts/meta_n/rerun_review.py，通过 --campaign math500 或 --campaign cobench 运行。使用独立预算 scope，沿用先前实验文档的全局 ¥150 预留保护和各组原有预算上限。本次新增保守费用预留合计 ¥34.825719，其中 MATH-500 ¥30.991485，CO-Bench ¥3.834234。该值为调用前预留量。

调试日志、源码快照和退出状态位于 experiments/debug_runs/20261118_review_rerun。两组主运行均以 0 退出。

本次范围选取两组正式对照。历史合成 pilot 和 CO-Bench smoke 继续保留原审查标注。官方 orchestrator 16k 消融沿用已有结果。

两组均为单次搜索，MATH-500 使用 60 道测试题，CO-Bench 使用 3 类测试任务。当前观察支持报告这些具体结果，一般性递归收益仍需更多重复实验验证。DeepSeek 模型别名与温度设置也无法确保跨日期的输出一致。
