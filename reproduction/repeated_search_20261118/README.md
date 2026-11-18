# 三次独立搜索补充实验

按照新增重复实验请求，在原修复后正式运行的基础上，为 MATH-500 和 CO-Bench 各安排两次新搜索。数据划分、模型别名、温度、输出上限和开发集选择规则沿用原协议，每次重新生成基线和 A/B/C。上下文采样种子依次为 20261116、20261117、20261118，DeepSeek 请求未发送确定性 seed。原始首轮结果在新增实验设计时已知。

论文所提供 PDF 的 §3 通常报告 seeds 42、43、44 的均值与标准差。附录 C 表 5 中，CO-Bench 每次运行内部的最大演化轮数为 Gemma 8、GPT-5.2 6，B=K=2，patience=4。当前补充实验重复 mini-project 的 A/B/C 对照。

## 运行入口

从包含 AlphaDiana、meta-n、experiments 和已安装 .venv 的工作区运行。环境与数据准备见上层 reproduction/README.md。凭证通过 DEEPSEEK_API_KEY 环境变量传入。

```sh
.venv/bin/python AlphaDiana/scripts/meta_n/rerun_review.py --campaign math500 --repeat-id 2 --project-cap-cny 220 --stage all
.venv/bin/python AlphaDiana/scripts/meta_n/rerun_review.py --campaign math500 --repeat-id 3 --project-cap-cny 220 --stage all
.venv/bin/python AlphaDiana/scripts/meta_n/rerun_review.py --campaign cobench --repeat-id 2 --project-cap-cny 220 --stage all
.venv/bin/python AlphaDiana/scripts/meta_n/rerun_review.py --campaign cobench --repeat-id 3 --project-cap-cny 220 --stage all
.venv/bin/python AlphaDiana/scripts/meta_n/report_repeats.py
```

新实验保守费用预留的项目累计上限为 ¥220，原各组和分支上限保留。各次输出路径包含独立 repeat 后缀，已有输出会读取并恢复。费用表为调用前保守预留，实际账单可能不同。

## 失败与恢复

CO-Bench 第 2 次的 A 输出只有 rationale，缺少有效策略，按原协议停止，该次计入失败。

其余三次任务曾因本机系统代理 127.0.0.1:7897 的 TLS 连接故障中断。失败请求、原始结果文件及其哈希保存在各实验的 recovery/01_system_proxy_tls。清理未评分的失败行后，使用 NO_PROXY=api.deepseek.com 直连恢复缺失题目。已有评分行保留，失败请求的费用预留全部计入账本。恢复命令通过 resume_repeat.py 执行，预检会核对归档失败请求与费用，调试日志包含实际命令和源码快照。

详细统计见 REPORT.md 和 summary.json。每次独立记录保留其单次运行的协议与局限，跨次解读以本补充报告为准。

恢复过程还发现 `APITimeoutError` 被结果状态的旧超时兼容逻辑误判为可计分的求解超时。已将 provider 错误排除在兼容路径外，并增加两项回归测试。涉及的原始空分记录在 recovery/02_null_timeout_score 中保留；重新请求前归档该未评分行。该修复只改变错误分类。相关 Metaⁿ、结果持久化与超时测试合计 35 项通过。

## 原始材料

raw_records.tar.gz 保存全部新增实验目录、调试日志、失败记录、恢复审计与汇总输出，RAW_MANIFEST.json 列出每个文件的 SHA-256。使用 `shasum -a 256 -c raw_records.sha256` 验证压缩包。配合相邻 review_rerun_20261118 的首轮证据即可检查全部三次搜索。
