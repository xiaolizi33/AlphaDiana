# MATH-500 六层策略链扩展

用户选定第 3 次修复后实验的 A+C 链，再累计添加四个策略层，达到六层。官方基础求解器深度为 1，因此最终求解器的官方深度为 7。

本实验有两个阶段。自然阶段新增第 3 层后，G 集达到 10/10；随后 Ω 两次主动返回空策略，明确认为生成集已经饱和。该自然停止点和两次完整 rationale 均保留。为完成固定六层诊断，第 4–6 层在官方 Ω 请求末尾增加了要求输出非空可执行策略的条件。该条件在实际请求中核验，属于对自然收敛行为的干预。

新增层均读取当前祖先源码、当前 G 轨迹及 pre-parent 评分反馈。每层生成后由 Diana 在 G10/D20 上执行并评分，按开发分选定最佳深度，再执行六层目标链的 T60。原测试集在本次扩展前已有结果，因此本次按探索性固定深度实验解读。基线和前两层的历史记录来源、哈希与新生成记录可逐项追踪。

## 材料

- REPORT.md 与 depth_results.csv 记录逐层分数和测试结果。
- depth_curve.png 显示原始逐层准确率，没有平滑或跨 seed 置信区间。
- case_trajectory.md 与 case_trajectory.json 展示实际逐层执行与上下文传递。
- token_accounting.json 分开记录新阶段的生成与求解 token。
- raw_records.tar.gz 保存自然阶段、强制继续阶段、容量调整、完整策略请求响应及调试源码快照。逐文件哈希见 RAW_MANIFEST.json，压缩包哈希见 raw_records.sha256。

六层阶段的费用保护为新增 ¥85、项目累计 ¥250，费用表均为调用前保守预留。第 6 层 Ω 曾在发送前触发本地容量保护，输入容量从 160,000 调整为 256,000 的保守边界，失败请求未发送且预留为零。原失败记录与源码调整记录均保留。

## 运行与核验

从包含 .venv、AlphaDiana、meta-n、experiments 的工作区运行，环境与数据准备沿用上层 reproduction/README.md。模型凭证通过 DEEPSEEK_API_KEY 设置。

```sh
.venv/bin/python AlphaDiana/scripts/meta_n/deepen_math.py --stage validate
.venv/bin/python AlphaDiana/scripts/meta_n/deepen_math.py --stage all
```

上面的自然阶段可能随模型响应在不同深度停止。本次记录在第 3 层后收到两次 no-op。使用归档的三层链继续固定深度诊断时运行

```sh
.venv/bin/python AlphaDiana/scripts/meta_n/force_depth6.py --stage validate
.venv/bin/python AlphaDiana/scripts/meta_n/force_depth6.py --stage all
.venv/bin/python AlphaDiana/scripts/meta_n/report_depth6.py --root experiments/math500_depth6_20261118_forced
```

force_depth6.py 针对本次保存的三层起点，导入 A、C、第 3 层及其原始执行记录。已完成的调用按记录恢复，重新创建实验输出会产生新的端点调用与费用。自然阶段的早期 source hash 与后续输入容量调整分别保存在调试快照及 implementation_amendments 中，检查时结合相应版本。
