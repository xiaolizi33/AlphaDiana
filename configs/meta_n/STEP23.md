# Step 2/3：递归生成与开发集选择

## 执行命令

从 interview 目录执行（与零层共用 .venv 和密钥）：

```sh
.venv/bin/python AlphaDiana/scripts/meta_n/campaign.py --stage 2
.venv/bin/python AlphaDiana/scripts/meta_n/campaign.py --stage 3
.venv/bin/python AlphaDiana/scripts/meta_n/report_search.py
.venv/bin/python -m pytest AlphaDiana/tests/harness/meta_n -q
```

stage 3 会检查并复用 stage 2 的结果。成功生成的策略不重复请求；生成开始前先写 attempt
标记，意外中断后停止，避免自动重新采样。Diana 对已评分题断点续跑；统计检查首个样本，
不能用重跑的较好结果替换。若有未评分错误，campaign 停止，需要先检查。

## 固定的 pilot 协议

`experiments/recursive_pilot/protocol.json` 在首次调用前冻结，带内容 hash：

- 合成整数数学题 22 道：G=6、D=8、T=8，无重复题面。
- G 仅供策略生成反馈；D 仅供选择；T 封存，不在本次 Step 2/3 执行。
- 六种题型：无相邻 1 的二进制串计数、模幂、带下界组合计数、gcd 和、模约束子集计数、整除异或计数。
- solver/Ω 均用 deepseek-flash，关闭 thinking；solver temperature=0，Ω=0.7。
- 每题输出上限 2048；Ω 输出上限 4096。相同的保守输入 token bound（以 UTF-8 字节 +1024 上界计）：solver=16000、Ω=80000。
- 固定官方 trace sampler RNG；G 小于 sampler 容量。完整实际请求保留，能检查选了哪些轨迹。
- 独立和递归分支均有 300000 token 上界预留、¥5 费用预留 cap；共享调用同时记入两分支，账单实际费用只算一次。
- 项目全部调用（含上一阶段）仍受 ¥50 总预留限制；Step 2/3 合计另限 ¥10。
- 预算按请求前最大值预留且不退款，包含失败请求，实际用量另表报告。未花完预算不增加候选。
- 并列时选浅链，同深时 A 优先。无效 B/C 不增加修复调用，回退 A；无效 A 停止。

这批题为了验证方法链路而构造，规模小、题型模板相近，不能作为论文式泛化结论。
模型响应当前仍返回 deepseek-flash 别名，服务端版本未能由 usage 独立确认。

## 流程

```text
G/base → 已评分轨迹 T0 → Ω → A
G/A    → 已评分轨迹 TA + A 源码 → 同一 Ω → C
G/A+C  → 运行并保存，验证递归链
T0     → 同一 Ω 独立再生成 → B
D/A、D/B、D/A+C → 独立选 A/B，递归选 A/A+C → selection.json
T/base、T/独立胜出者、T/递归胜出者 → 只生成配置，等待下一步执行
```

A 和 B 的完整请求必须逐字一致，源轨迹 hash 也必须一致；它们是两次独立采样。
C 输入包含 TA 和 A 的源码，不接触 B 或 D/T 模型结果。各深度都显式附带
官方 Layer1Solver 源码；这是可审计的 prompt 附加内容，不修改官方 Ω 模板或解析器。

## 代码职责

- `harness/meta_n/layers.py`：加载带 hash 策略文件；调用官方 `MetaLayer` 和
  `merge_code_libraries`。C 外层先执行，A 内层收到 C 的 outer_context；同名 helper 后层覆盖。
- `IsolatedMetaLayer` 只替换 pre_process 的执行位置：在无密钥 macOS worker 内调用官方
  `run_pre_process`，保留校验、跳过与上下文语义，并保存每层输入/输出事件。
  worker 仅额外开放读取 Python 环境和 meta_n 源码，不开放项目密钥。
- 官方 library 逻辑在主进程仅做静态校验/拼接；生成 helper 与 solve() 最终在沙箱执行。
- `agent.py`：配置加载任意策略链，保持每题一次模型调用、固定 temperature=0；
  `metadata.executed_script` 保存实际拼接代码，避免 Diana 标准化 trajectory 时丢掉附加字段。
- `campaign.py`：冻结数据与协议、Diana 调用、Trace 转换、Ω 生成、开发选择。
- `report_search.py`：只读原始产物重建统计，导出可阅读策略源码和下一阶段测试配置。

原有 Step 1 不加载任何策略，保持相同入口。新增测试核查了 C→A 顺序、outer_context、
helper 覆盖、父链不变、split 无交集、协议防改及并列选 A。

## 查看产物

所有真实产物位于 `experiments/recursive_pilot/`：

- `strategies/A.json、B.json、C.json`：策略、parent、hash、原始请求/响应和 usage。
- `strategies/*.request.json、*.response.json`：即使后续解析失败也保留接口记录。
- `strategies/{A,B,C}/pre_process.py、*.py`：从 JSON 导出的可阅读源码。
- `configs/`：G/D 实际运行配置，以及尚未执行的 T 三组配置。
- `results/{G_base,G_A,G_AC,D_A,D_B,D_AC}.jsonl`：Diana 原生评分与轨迹。
- `selection.json`：冻结的胜出者、策略 hash、协议 hash 和开发集结果 hash。
- `case_study.json`：A 出错而 A+C 修正的生成集案例，包含完整前后记录。
- `search_summary.json、report.md`：正确数、生成/反馈/开发 token 分账。

G_AC 是为验证 Step 2 要求增加的诊断运行，其真实成本计入递归 cap 并单独列出。
比较时不要称两个分支实际消耗相等；这里对齐的是机会数和预算上限。

## 本次实测结果与预算补充

原先 300000 token 的**上界预留** cap 在 D_AC 最后一题请求前触发。
原 cap 下递归开发评估为 7/8 已完成，记录保存在 `original_cap_outcome.json`，
不声称该预算下已完成全部比较。随后在请求前冻结 `budget_extension.json`，
将两分支共同扩展到 600000 token 预留上限，费用 cap 不变。
只补跑此前被预算拒绝、从未请求 API 的那一道题；原始 runtime_error 保留在 JSONL。
`read_rows` 只允许该类请求前预算拒绝被后续记录补齐，拒绝替换任何已评分答案。
这是看到部分开发结果后的预算补充，因此完整结果标为探索性补充，不是原始预算预注册结果。

|集合|base|A|B|A+C|
|---|---:|---:|---:|---:|
|G（6题）|6/6|5/6|未运行|6/6|
|D（8题）|未运行|7/8|7/8|8/8|

独立分支冻结 A，递归分支冻结 A+C。T 未调用。
本轮物理合计 65953 token。分支费用表包含共享用量：独立 28879 token，
递归含诊断 52550 token，不能直接相加当作物理总量。
包括先前零层与 preflight 的项目累计保守费用预留约 ¥2.091，远低于 ¥50；
预留不是账户实际扣款。

案例 synthetic_16：A 下因长篇输出触及 2048 输出上限，未产出可执行完整答案；
C 从该轨迹生成了简短代码输出约束和 `dp_mod_count`。A+C 下实际生成的 solve() 为：

```python
def solve():
    return dp_mod_count(list(range(1, 17)), 5, 0)
```

执行返回 13112，Diana 判正确。记录中的 layer_events 显示执行顺序为 C(depth=2)、
A(depth=1)，A 的 outer_context 收到 C 的指导。A 本身没有读取 outer_context 的分支，
所以该例证明的是外层指导进入最终 prompt、helper 被调用，不应声称 A 根据 C 主动改变了自身逻辑。
该例来自生成集，不能用作未见测试集收益证据。
