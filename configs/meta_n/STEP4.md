# Step 4：固定测试集评估

从 interview 目录运行：

```sh
.venv/bin/python AlphaDiana/scripts/meta_n/evaluate_test.py
```

入口先核验 protocol hash、selection hash、三组题目、策略源码 hash 和公共模型设置，
将配置 hash 写入 `experiments/recursive_pilot/test_manifest.json`，然后交给 Diana Runner。
三组分别为 base、独立分支已选 A、递归分支已选 A+C；使用相同 8 题和 2048 输出上限。
不会调用 Ω，也不会改变策略或开发选择。

每组每题只保留首次已评分结果。输出截断、代码执行错误等按 Diana 原 scorer 记录，
不为了提高正确率重跑。如果出现请求层错误则停止，不自动重试。
成功结束后再运行同一命令会读取已有记录，重建报告，不产生新 API 调用。

输出：

- `results/T_{base,independent,recursive}.jsonl`：Diana 原始逐题记录。
- `test_summary.json`：正确率、改对/改错的题目 ID、三组逐题答案、完整 token 分账。
- `test_report.md`：便于阅读的结果表及限制说明。
- `test_manifest.json`：请求前冻结的测试输入与策略信息。

`selection.json`、`search_summary.json` 和 `report.md` 是测试前的历史快照，保持原样，
其中 test_executed=false 表示快照时尚未测试。当前测试状态以 test_summary.json 为准。
`report_search.py` 只统计 G/D，并排除测试阶段预算预留，因此仍可重建搜索快照。

这次测试仍属于合成题 pilot：仅 8 题、单 seed，题型模板与 G/D 相近。
搜索阶段扩展过共同 token 预留上限，完整结果属于探索性补充。
正式研究实验应另行冻结真实题集和预算，重新生成候选；不得根据本次测试重新挑选 A/B/C。
