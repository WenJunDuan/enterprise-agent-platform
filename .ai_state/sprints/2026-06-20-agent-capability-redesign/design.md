# Agent 能力重构 Design — 五诉求 → 两脊椎

> Sprint 2026-06-20 · Path: System · 对话驱动（评审 round4 之后的架构决策），落档先于实现

## Goal

让 agent 架构具备五项能力：**任务拆解、多工具 API 联动、长时序记忆、幻觉抑制、结果反馈修正**。

核心判断（good taste 收敛）：这不是五个并行模块，是 **两根脊椎**。其中四项共用同一机制——**类型化契约 + 过闸验证**；只有「记忆」是独立维度（本质是时间 + 出处 + 从属规则）。

直接动因：round4 评审的 F1（默认路径不做 schema/引用校验）是这四项能力的共同地基缺口。建一次闸，幻觉抑制与反馈修正是副产品，拆解与工具联动因为有了可验证边界而变安全。

## 背景：五诉求 → 机制映射

| 诉求 | 第一性原理 | 现状（已验证） | 那一刀 |
| --- | --- | --- | --- |
| 任务拆解 | 仅当子任务可独立验证 + 可并行/需不同工具时才拆，否则是延迟税（延迟 = N × 网关 RTT） | 内联审核**故意**砍了子 agent 嵌套（对的）；命令 S0→S4 是隐式散文计划 | PLAN 产出**类型化任务图**（自身过 schema），只对 tender 多章节并行这类真需要场景拆 |
| 多工具 API 联动 | 可靠性 = 契约清晰度 × 错误结构化 × 幂等；工具数与可靠性反相关 | OCR=确定性 Python、只把字段映射交模型（被低估的正确决策） | 外部 API（企业信用 / 发票真伪）= 每个一个强契约工具，**结果先过代码校验再进推理上下文**；按域路由保持每 agent ≤ 一把工具 |
| 幻觉抑制 | 不能靠「让模型小心」，只能让每条承重声明可外部验证、验不过就拒 | 提示词已要求引用而非记忆；`run_agent_json` 已有重试环；但**无任何代码校验引用** | `policy_refs`→真 rule_id、`evidence_chain`→真实输入片段，解不出 → `manual_review`；**算术搬出模型**（金额/限额/日期由代码重算） |
| 结果反馈修正 | 需要信号 + 修正路径 + 信号回流防复发 | `review-output.py` 二次复核（为成本关掉，对）；risk≥70/data_conflict 阈值已设计 | 分层：① 确定性过闸（同步免费）② gated 二次模型（仅高风险）③ **人工否决 → 案例记忆**（唯一复利回路，现缺失） |
| 长时序记忆 | 检索键匹配 + 信任/衰减模型，否则污染上下文 | `memory_store` + `knowledge/memory/{domain}` + distill/query skill；但 `case-memory.schema.json` 缺 tender 枚举 | 三层（制度 > 案例 > 工作）；案例记忆加 `valid_until`/`superseded_by`/`decided_under_rule_version`；规则升版自动标陈旧 |

## 架构：两脊椎

### 脊椎一 · 验证闸（Verification Gate）

放在 `apply_schema_semantics`（`server/common/contract.py`），DRAFT 之后、COMMIT 之前。三件事，从便宜到贵：

1. **schema 形** — `jsonschema.validate(parsed, load_output_schema(name))`，text/structured 两路都跑。失败抛 `JSONContractError`，被 `server/audit/runner.py` 既有重试环接住。
2. **引用解析（幻觉闸）** — 把命中规则 ID 集合传进校验器，断言 `policy_refs ⊆ 已注入规则集`；`evidence_chain` 每条 source 须解析到真实输入文件/字段。`verdict=approved` 时硬性回查。解不出 → 降级 `manual_review`。
3. **数值重算** — 金额/限额/日期由 OCR 确定性给数，比较（880 > 800?）由 Python 重算，不信模型自报。

> 这道闸同时关掉 F1、提供幻觉抑制、并充当反馈修正的「便宜层」（确定性、同步、抓大多数错）。

### 脊椎二 · 记忆轴（Memory Axis）

铁律：**案例记忆从属于制度记忆**。否则自我强化错误回路（判错先例被召回→被加强）。

- **制度记忆（权威）** = `knowledge/*/*.rules.json`，人工策展、带版本号。非「记忆」，是 ground truth。
- **案例记忆（情节）** = `knowledge/memory/{domain}/`，带 `request_id`/`result_file` 回链 + 置信衰减 + `decided_under_rule_version`。召回只当**建议**，判决前必须拿当前规则复检。
- **工作记忆（短时）** = 单次任务内抽取的事实，ephemeral。
- **人工修正 → 案例记忆** = 唯一有复利的回路。人否决一次 = 一条高置信负样本。现在这条路完全缺失，是长期改进的关键缺口。

## Build Order（脊椎一先，记忆轴后；每步是下一步地基）

1. **G1 验证闸最便宜三件**：schema 校验 + 引用解析器 + 算术重算（落 `server/common/contract.py` / `output_contracts.py`）。半天，杠杆最高，同时关 F1。
2. **G2 PLAN 类型化任务图**：命令产出可过 schema 的结构化 plan，而非散文。
3. **G3 工具契约化**：外部 API 一个强 I/O 契约 + 结果过闸（先 tender `requires_external_data` 一个真用例）。
4. **G4 记忆三层 + 衰减 + 规则版本绑定**；先修 `case-memory.schema.json` 缺 tender 枚举（现在 tender 连记忆都存不进）。
5. **G5 人工否决 → 案例记忆** 回路；二次复核维持 gated（不退回全量）。

## Out of Scope（本 sprint 不做）

- 不重开全量二次复核（ROI 负，CLAUDE.md 已治理）。
- 不引入向量库 / RAG 重型检索——案例记忆量级小，先用结构化 key + 衰减，够了再升级。
- 不改 LiteLLM / 模型层。

## 关联

- 评审依据：[`../2026-06-19-review-backend-refactor/reviews/round4-fullstack-review.md`](../2026-06-19-review-backend-refactor/reviews/round4-fullstack-review.md)（F1 = G1 地基；F3/F8 与记忆轴 tender 枚举相关）
- 顺手裹挟：删 legal/HR 死域（F8）应先于 G2/G3，避免为死域做抽象。
