# Mini-project 最终交付（2026-11-18）

本交付包含 AlphaDiana harness、官方 Ω 生成入口、独立和递归搜索配置、修复后两组正式实验和 15 页约 18 分钟汇报。

新增的 [三次独立搜索报告](repeated_search_20261118/REPORT.md) 汇总首轮与两次新搜索。MATH 完成 3 次，CO 完成 2 次并保留 1 次策略失败。当前汇报已更新为重复实验结果，完整新原始证据附在 repeated_search_20261118/raw_records.tar.gz。

[累计六层扩展](depth6_20261118/REPORT.md) 已完成。自然阶段在三层后发出 no-op 信号，第 4–6 层采用明确的强制非空生成条件。六层指定链 T58/60，保存基线 T45/60；开发集仍选择基线。当前汇报与原始记录已更新。

## 阅读顺序

1. [环境、数据与复现命令](README.md)
2. [正式重跑结果表](review_rerun_20261118/RESULTS.md) 与 [任务覆盖核对](review_rerun_20261118/COMPLETION.md)
3. [实现审阅](IMPLEMENTATION_REVIEW.md) 与 [问题复盘](ISSUES_AND_LESSONS.md)
4. [汇报 PPTX](presentation/MetaN_18min.pptx) 与 [逐页讲稿](presentation/speaker_notes.md)
5. [Archive 核心曲线](figures/archive_curve.png) 与 [消融结果图](figures/ablation_scores.png)

正式实验的全部策略源码、请求响应、逐题结果、代表性数学案例和 token 分账保存在 review_rerun_20261118/raw_records.tar.gz，附逐文件 SHA-256 清单。工作区最终总包还包含历史实验、调试日志、研究笔记和 Git bundles。

## 本次审阅结论

当前相关离线验证通过 35 项，包含 Metaⁿ、结果持久化和 provider 超时回归。首轮正式重跑有 297 条有效评分和 303 条完整请求日志。此前 completion audit 中的演示文稿待办已由本交付补齐，原审阅记录保留其当时状态。

首轮 MATH-500 两分支均选择 A，测试为 base 44/60、独立 56/60、递归分支 52/60。后两者是同一策略的不同执行。CO-Bench 为 base .832881、A .664186、A+C .764236。两组均只运行一次搜索，当前结果的一般性递归收益证据有限。历史错误深度入口的数值继续按实现变体标注。官方 16k 消融使用搜索 validation，实际 token 不等。

## GitHub

交付 fork 为 https://github.com/xiaolizi33/AlphaDiana-MetaN ，提交分支为 reproduction/meta-n-review。该仓库从 tmlr-group/AlphaDiana 新建，保留 GitHub fork 关系。原个人仓库 xiaolizi33/AlphaDiana 保留。

汇报采用中文、简洁研究汇报样式，逐页时间共 18 分钟，实际时长取决于讲述速度。论文部分依据用户提供 PDF。图像为既有实验曲线。当前检查包含离线测试、PPTX 结构及逐页渲染检查。
