# Metaⁿ 零层流程（Step 1）

正式题集接入与独立预检见 [MATH-500](MATH500.md)。

后续 Step 2/3 已实现，参见 [递归与选择说明](STEP23.md)。测试入口参见 [Step 4](STEP4.md)。本文保留最初零层运行记录；当前 harness 也支持策略链。

已在 2026-11-14 用 DeepSeek 实际完成 3 道自定义调试题；3/3 正确。
这些题只用于接通工程链路，不是正式题集，不支持方法优劣结论。
模型请求 `deepseek-flash`，关闭 thinking，temperature=0，max_tokens=2048；
无 SDK 自动重试。服务实际返回模型标识及 usage 保存在逐题结果中。

## 运行

在 interview 工作目录：

```sh
uv pip install --python .venv/bin/python -e ./meta-n -e ./AlphaDiana pytest
.venv/bin/python -m pytest AlphaDiana/tests/harness/meta_n/test_zero.py -q
.venv/bin/python AlphaDiana/scripts/meta_n/run_zero.py
```

依赖 sibling `meta-n` checkout 的可编辑安装；当前尚未制作为独立分发包。
运行器优先使用环境变量 `DEEPSEEK_API_KEY`，否则读取 interview/apikey；
密钥不会放进 YAML、模型 prompt 或结果中。脚本固定工作目录，避免相对路径漂移。
需要 macOS、sandbox-exec 和 Xcode Command Line Tools 的 Python 3。

也可在 AlphaDiana 目录、配置好环境变量后用标准 CLI：

```sh
../.venv/bin/alphadiana run configs/meta_n/zero_pilot.yaml
```

保持相同 run_id 重跑，Diana 跳过已评分题；已实测跳过全部 3 题，未新增请求。
Diana 对失败记录的重跑语义仍保留，任何新请求都再次预留预算。

## 数据如何流动

```text
zero_pilot.yaml
  → Diana CustomBenchmark：读取题面和标准答案
  → Diana Runner：分配一题
  → MetaNAgent：只将 task_id + 题面转为 TaskDescription
  → 官方 Layer1Solver：构造 Python prompt、调用模型、提取代码
  → SolverClient：先预留费用，再调用 DeepSeek，保留完整 usage
  → executor：在 macOS 沙箱中执行 solve()
  → AgentResponse：答案 + prompt + 原始输出 + 代码 + 执行记录 + usage
  → Diana NumericScorer：对照标准答案评分
  → Diana ResultStore：保存逐题 JSONL、轨迹和运行清单
```

“零层”是没有生成策略，`strategy_chain: []`。官方名称 Layer1Solver 是基础
solver 的类名，不代表这里已经加载第一层策略。该次运行未加载策略链。
没有调用 Ω，也没有安装 A/B/C。

executor 调用无参数 solve()，优先取返回值；返回 None 时用 stdout。
打印后抛异常仍判执行失败，不接受打印出来的答案。脚本墙钟上限 5 秒，
CPU 上限 3 秒，输出文件上限 1 MiB，杀掉执行进程组后清理临时目录。
子进程不继承 API 密钥；禁止联网、读取 /Users 和其他临时工作区，禁止向工作区外写文件。
这是 macOS 调试执行器，允许读取系统运行时，不能视为通用容器隔离；正式实验前应统一执行环境。
基础 prompt 中上游提到可选 llm helper，本适配明确说明不提供，保持每题单次模型调用。

## 结果与预算

输出在 interview/experiments/zero_baseline：

- meta_n_zero_pilot.jsonl：每行一题，含答案、评分、prompt、代码轨迹、usage。
- meta_n_zero_pilot/：Diana 的 manifest、逐题文件及生命周期记录。
- pilot_summary.json：Diana 汇总结果。

本次 API 共输入 778、输出 56，总计 834 token；三题答案为 391、120、9。
费用不是账户账单：采用输入 ¥3/百万、输出 ¥12/百万的保守预留估价，
实际用量对应 ¥0.003006。价格参考 2026-11-14 官方页面：
https://api-docs.deepseek.com/quick_start/pricing/ 。
预留价高于当日 Flash 峰值美元报价按 10 CNY/USD 折算，用于阻断预算，不代表实际汇率或人民币价格。

每个请求先按输入字节上界 + 1024 及最大输出预留，落盘并加文件锁；
本次保留预留总额 ¥0.093423。失败或结果不明也不退预留，避免漏记请求。
同一 pilot 累计预留上限 ¥1，项目总预留上限 ¥50，含此前 preflight 的 ¥0.000042；
ledger 在 interview/experiments/budget_reservations.jsonl。不要删除 ledger 来重新获得预算。
此账本仅覆盖使用该适配器的调用，后续策略生成入口也必须接入同一预算机制。

后续再冻结正式数学题集和 G/D/T 划分，当前样本不得混入正式测试集。
