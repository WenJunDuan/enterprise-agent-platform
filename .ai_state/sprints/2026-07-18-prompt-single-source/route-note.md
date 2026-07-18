# Route Note · D3 prompt-single-source (spike 先行)

日期: 2026-07-18 · 新会话接续 (上会话 5 sprint 全 merge+push, main 861 绿, origin 同步)

## 分诊

**候选路径**(本机可动项, 逐项证据):

| 候选 | 证据 | 结论 |
|---|---|---|
| D8 部署机 runbook | handoff 明示"部署机的活"(真标书+网关四指标) | 非本机, 跳过 |
| D4 / D5 / D9 / D10 | D4 卡部署机 V4Pro 基线; D5 依赖 D3+D4; D9 依赖 D4+前端红区授权; D10 依赖 D3 拍板 | 全被卡 |
| **D3 spike** | handoff 排序②; 依赖为空; spike 先出数, 用户再拍统一方向 | **选定** |
| D11 残留收口包 | 依赖 D1/D2 均 done, 可动; 但含 R4 安全硬化独立轮+R7 前端红区需授权 | 备选(D3 spike 被环境卡死时替补) |
| dependabot 14 漏洞 | handoff 排序④, 历史既有 | 顺位靠后 |

**决策**: 起 D3 spike — 实测 expense 三种 prompt 投递模式延迟差值, 出数后交用户拍统一方向(D3 与 D10 同场拍板)。**置信度: 高**(handoff 明示顺序; spike 无前置依赖; 本机 .env 就位、eval 底座就位)。

## Spike 设计

**问题**: 三域三套 prompt 投递机制(expense=Python 常量内联 / tender=command 文件 / ocr=内联), 双源漂移风险。统一方向取决于 command 模式的延迟代价。

**实测漂移证据(spike 探面时发现)**: `.claude/commands/audit.md` 与 `server/audit/runner.py:AUDIT_INSTRUCTIONS` 已实质分叉 — command 文件缺「数据真实性快速核验」整节与 JSON 引号纪律(「」代半角双引号), 且仍写着 spawn extractor/auditor 的旧协同注记。漂移不是理论风险, 已发生。

**三模式**(case = `tests/eval_fixtures/placeholder-invoice`, golden 期望 rejected):

| 模式 | 机制 | setting_sources | 工具 | 度量什么 |
|---|---|---|---|---|
| A | 生产现状 `run_inline_directory_audit`(AUDIT_INSTRUCTIONS+案件+规则全内联) | `[]` | env 默认(文本模式=零工具) | 基线 |
| B1 | command as-is: `/audit <dir>`, agent 自行 Glob/Read 案件+规则 | `["project"]` | Read+Glob, max_turns=16 | command 模式全代价(机制+工具往返) |
| B2 | command + context 注入(tender P4 形态): 指令来自 command 文件, 案件+规则随 context 内联 | `["project"]` | 同 A | 纯机制开销(CLAUDE.md/系统提示膨胀), **现实统一候选形态** |

各 3 轮, 按 A,B1,B2 交错跑(抵消网关时段漂移)。记录: 墙钟时延 / verdict 与 golden 一致性 / cost_usd / 契约重试次数(B 侧镜像 A 的 retry 环保证公平)。`archive_to_results=False` 不污染 results 表。

**判读口径**(供拍板): 若 B2−A 中位差值 ≤ 可接受阈值(阈值由用户定, decisions_needed 在册) → 统一到 command 单源; 否则反向统一(Python 单源, .claude expense 资产标注非生产真相源)。B1 数据供参考(若统一后仍想省 context 注入的工程量)。verdict 漂移(若 B1/B2 判非 rejected)= 双源漂移已造成行为分叉的直接证据, 加重单源紧迫性。

**写区**: spike 脚本+结果落 `.ai_state/sprints/2026-07-18-prompt-single-source/spike/`(评测工装非产品代码, 绿区主 agent 直做; server/ 零改动)。

## Spike 结果 (2026-07-18, 完场, 证据=spike/results.jsonl 13 attempts, 05:47-05:59 UTC 交错跑)

环境: model=deepseek-v4-flash, 文本模式(structured=False), case=case-taxi(规则案,期望 rejected 引 expense_travel_005)。

| 指标 | A 生产内联 | B1 command as-is | B2 command+context |
|---|---|---|---|
| 成功样本墙钟 | 62.0 / 50.2 (**中位 56.1s**) | 58.9 / 83.5 / 47.9 (**中位 58.9s**) | 62.5 / 55.5 / 33.9 (**中位 55.5s**) |
| attempt 级契约失败 | **4/6**(全部漏 explanation; R3 双试全挂=生产该单 failed) | 0/3 | 1/4(空 policy_refs 撞承重闸) |
| verdict 稳定性 | 2/2 rejected | **1/3 漂移**(R2 manual_review/insufficient_evidence) | 3/3 rejected |
| 成功单成本 | $0.285 / $0.254 | $0.374 / $0.432 / $0.332 | $0.389 / $0.392 / $0.307 |

**判读**:
1. **时延差值 ≈ 0**: 三模式中位差 <6%, command 机制(载 CLAUDE.md+commands 的系统提示膨胀)的延迟代价在本案尺度完全在噪声内。D3 立项时的核心担忧(延迟)**不构成方向约束**。
2. **成本**: command 侧 +~30-40%($0.36-0.39 vs $0.27)——真实但非决定性。
3. **可靠性不对称(意外主发现)**: A 的契约失败率 4/6 vs B 侧合计 1/7, 且失败形态不同(A 恒漏 explanation; B2 一次空 policy_refs)。交错跑排除时段漂移。极可能是**两源 prompt 内容已漂移**所致(command 文件对输出契约的表述让 flash 更守约), 而非机制本身——这把单源统一的紧迫性从「卫生债」升级为「生产可靠性」: 当前 flash 下生产 A 路径约 1/3 轮次两试全挂直接 failed。
4. **B1 淘汰**: agent 自行 Glob/Read 出现 1/3 verdict 漂移(自主取证引入非确定性), 且比 B2 慢/贵。若统一到 command, 形态必须是 **B2(context 注入, tender P4 同形态)**。
5. **caveat**: 单案件/单模型/3 轮小样本; flash 契约完整性弱是背景噪声, 但 A/B 不对称方向一致、幅度大(4/6 vs 1/7)。

**给用户的拍板项**(D3 与 D10 直连按 roadmap 同场拍板):
- 方向 a: 统一 command 单源(B2 形态)——吃 +35% 成本, 换 .claude 资产单一真相源
- 方向 b: 统一 Python 单源——.claude expense 资产标注非生产真相源; 若 D10 直连 spike 胜出这是自然归宿
- 方向 c(主 agent 推荐): 先修下方 prompt-闸矛盾 + 补齐 D10 直连 spike 数据, 再同场拍——本 spike 已证延迟不卡方向, 剩余变量是 D10 直连形态
- 不论方向: 两源漂移已在生产可靠性上收费, 修 explanation 缺失应尽快(哪怕先做内容对齐不动机制)

## 附录 · spike 首跑暴露的产品级矛盾 (2026-07-18, 未修, 待用户拍)

**现象**: 首跑用 `tests/eval_fixtures/placeholder-invoice`(golden 期望 rejected), Mode A 生产路径两次尝试均硬失败:
`JSONContractError: audit result with verdict=rejected must cite at least one policy_ref.`
(证据: `spike/results-placeholder-case.jsonl`, 每次 ~20s, 网关连通正常, model=deepseek-v4-flash)

**根因**: prompt 与服务端语义闸互相矛盾 —
- `server/audit/runner.py:56`(AUDIT_INSTRUCTIONS 数据真实性快速核验节): 「该判定基于数据真实性而非业务限额, 此时 `policy_refs` **允许为空数组**」
- `server/common/output_contracts.py:281-286`(`_validate_audit_result` 承重依据闸, 有意设计): approved/rejected **无条件**要求 ≥1 policy_ref

模型忠实执行 prompt(空 policy_refs)→ 被闸拒 → 重试同样失败 → 生产 audit 对占位/造假类案件在 literal 模型(当前 `MODEL_NAME=deepseek-v4-flash`)下**必然 failed**。此前未暴露疑因旧模型(v4-pro)恰好会顺手引用 `expense_travel_026`(禁止虚报)之类规则过闸 = 模型依赖的隐性 flaky。golden manifest 的 placeholder-invoice 用例在 flash 下同理必挂 — **D1 audit 回归闸在部署机跑 flash 时会假红**。

**两个修复方向(二选一, 涉语义闸从严/从宽属安全面, 留用户拍)**:
1. **prompt 从严(倾向)**: 删「允许空数组」承诺, 改为数据真实性拒绝须引用反虚报类规则(expense 域有真实 `expense_travel_026`; 但需确认 meal/entertainment 域有对应规则, 否则该类案件降 manual_review — 闸对 manual_review 不要求 policy_refs, 语义也更稳妥)
2. 闸从宽: 为数据真实性拒绝开例外(如 anomaly 维度高分时豁免)— 弱化承重依据闸, 与「结论必须可回溯到规则」的平台红线冲突, 不推荐

**影响面**: expense 生产链路 + D1 golden manifest(`tests/eval_fixtures/golden_manifest.json` 唯一用例正是此形态)。tender 域不涉(其 prompt 无此承诺)。
