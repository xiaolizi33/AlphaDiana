# 正式题集接入与独立预检（2026-11-15）

2026-11-16 已完成正式 G/D/T 全流程：base 50/60，独立分支 A 45/60，递归分支同样选中 A、46/60；没有递归链胜出的证据。报告见 experiments/math500_formal/test_report.md。

## 来源与复现

数据：[HuggingFaceH4/MATH-500](https://huggingface.co/datasets/HuggingFaceH4/MATH-500)，
版本 `6e4ed1a2a79af7d8630a6b768ec859cb5af4d3be`。
原始 JSONL 包含 problem、answer、solution、subject、level、unique_id，500 条。
本地 snapshot 的 SHA256 保存在 pilot_manifest.json 与正式 protocol.json。
下载入口固定版本，不追踪未来 main；loader 每次检查文件 checksum。

数据卡说明其来自 MATH 的 500 题子集，并指向 OpenAI prm800k 的划分。
镜像没有声明 license 标签；[上游 MATH 仓库](https://github.com/hendrycks/math/blob/main/LICENSE)
有 MIT 许可，但这不等于镜像已独立声明同一许可。当前只在本地使用快照，提交仓库时应提供下载脚本、版本及归属说明，不把它重新标记为已明确 MIT 授权的数据发布。

在 interview 目录：

```sh
uv pip install --python .venv/bin/python -e './AlphaDiana[math]' -e ./meta-n pytest
.venv/bin/python AlphaDiana/scripts/meta_n/prepare_math500.py --run
.venv/bin/python AlphaDiana/scripts/meta_n/freeze_math500.py
.venv/bin/python -m pytest AlphaDiana/tests/harness/meta_n -q
```

首次缺少本地 snapshot 时会下载固定版本。预检 IDs 在模型调用前冻结；重跑复用已评分结果，
不自动重试请求错误。已实测重复执行没有新增 API 请求。

## 接入代码

`benchmarks/math500/benchmark.py` 只根据显式 ID 列表加载题目，验证 checksum 与重复 ID。
answer 仅填 ground_truth；solution 不进入 BenchmarkTask，metadata 只含题型、难度与来源 ID。
`MetaNAgent` 仍只传 task_id 与 problem，防止 gold 或参考解法传入 solver。

`agent.config.answer_contract` 扩展基础求解契约：非数值答案返回精确 LaTeX 字符串，
支持分数、根式、代数式、有序对、区间等；禁止把精确表达式随意转小数。
仍通过官方 Layer1Solver 生成 Python solve()，在原 macOS 沙箱执行；solver 不使用 sympy 或额外 LLM。

评分复用 Diana 的 `MathVerifyScorer`，安装 `math-verify==0.8.0`，没有改判分规则。
500 个 gold 均可被符号解析并判为自身等价；额外测试验证分数/根式等价、
有序对交换不等价、错数和空答案不通过。自身等价审计只证明解析覆盖，不证明 scorer 对所有模型输出都无误。
全部真实预检结果的 score_metadata.method 都是 math_verify，没有落入字符串 fallback。

## 独立预检结果

8 题覆盖全部 7 个 subject，所有题从正式 pool 排除，预检不用于 Ω 生成：

- 正确 6/8，截断 0/8，执行失败 0/8。
- 输入 2799、输出 1188，总计 3987 token；逐题 wall_time_sec 合计约 15.24 秒。
- 保守费用预留 ¥0.848661，不是账户实际扣款。
- 错题为 geometry/473 和 precalculus/801，保留原输出，不重采样。

产物：`experiments/math500_preparation/` 的 pilot_manifest、scorer_audit、
preflight.yaml、preflight_summary，以及 results 中的 Diana 原生 JSONL。
这些结果不是正式基线准确率，不与合成题 pilot 合并。

## 冻结的正式方案

`experiments/math500_formal/protocol.json` 在正式调用前落盘并带 hash。
按 subject × level 做比例分层抽样；固定 seed=20261116。G=10、D=20、T=60，
90 个 ID 互斥，规范化题面 hash 无重复，全部排除 8 个预检 ID。
剩余题目留用，不根据正式结果换题。该规模是预算内的小规模正式方法对照，不具备大样本结论。

- solver 与 Ω：deepseek-flash，关闭 thinking；temperature 分别为 0 与 0.7。
- solver 和 Ω 输出上限都为 8192；保守输入 token bound 分别为 16000 与 80000。
- scorer：Diana math_verify，max_concurrent=1，每题一次模型调用，SDK retries=0。
- G/base→A，G/A→C；B 从同一份 G/base 独立生成。全部从头生成，不复用合成题策略。
- D 比较 A/B 和 A/A+C；并列取浅链，同深 A 优先。冻结后测试。
- G/A+C 的诊断运行也纳入递归成本；共享调用分别计入两分支比较、物理总量只计一次。
- 两分支同样的搜索 cap：2,000,000 token 上界预留、¥12 费用预留。
- 正式阶段物理总 cap=¥41，项目累计 cap=¥50；请求前加锁预留，失败不退预留。
- 预算耗尽即报告未完成，不中途扩 cap、不为无效策略免费补生成、不替换已评分答案。

最多 270 次 solver + 3 次 Ω。按所有输入输出都达到 cap 计算，正式预留最坏 ¥40.516992，
加冻结时此前全部实验预留 ¥3.846042，合计约 ¥44.363034，低于 ¥50。
这是保守工程预留，非实际账单；固定预留率输入 ¥3/百万、输出 ¥12/百万，
已于 2026-11-15 对照 [DeepSeek 官方价格](https://api-docs.deepseek.com/quick_start/pricing/) 核验其保守性。

已生成并验证 `math500_formal/G_base.yaml`，但未发送正式请求。
后续正式 campaign 需读取此协议和独立预算分支，不直接沿用合成 pilot 的硬编码 root 和 cap。
公开题集的“未见”仅指策略生成与选择未见，不代表模型预训练未见；服务返回别名也不能保证版本不可变。

## 正式 campaign 入口（2026-11-16）

从 interview 目录运行：

```sh
.venv/bin/python AlphaDiana/scripts/meta_n/formal_campaign.py --stage validate
.venv/bin/python AlphaDiana/scripts/meta_n/formal_campaign.py --stage all
.venv/bin/python AlphaDiana/scripts/meta_n/report_formal.py
```

`validate` 不发模型请求；核验协议、snapshot、分层题面 hash、评分器版本和预算账本。
`search` 完成 G、A/B/C、D 及选择；`all` 随后冻结测试 manifest 并运行 T，生成
`experiments/math500_formal/test_summary.json` 与 `test_report.md`。
正式入口复用官方 Ω 适配，从协议读取输出上限、答案契约及独立预算分支；不读取 pilot 的预算扩展。

首次运行前冻结 `implementation.json`（适配代码 hash 与 meta-n commit），恢复时核验一致。
逐题已评分结果直接复用；已有失败或无法对应持久化结果的费用预留会阻止恢复，需人工审计。
请求异常会写入 `request_halted.json`，阻止后续付费请求；并发入口由文件锁阻止。
失败保留 `incomplete.json`，不自动重试、不扩 cap。不要删除预算账本或停止标记来绕过审计。
原 `G_base.yaml` 保留为准备阶段产物；campaign 实际冻结的运行配置位于 `configs/`。

本次实际 270 次 solver、3 次 Ω，306326 token；项目累计保守预留 ¥33.784698，非实扣。
19 项测试通过；完整重跑已验证预算账本 hash 不变、无新增请求，见 verification.json。
protocol.json 的 status 与 selection.json 的 test_executed 是冻结时快照；当前完成状态以 test_summary.json 为准。
