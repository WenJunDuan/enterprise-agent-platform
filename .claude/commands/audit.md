---
description: 审核单个输入文件或目录
allowed-tools: Read, Write, Glob, Skill, Task
---

读取指定输入路径（单个文件或目录），**在当前会话内一次性完成审核并直接输出最终结论**。

## 执行方式（低延迟：单 agent 内联，不嵌套子 agent）

为把单次审核压进 ~2 分钟，**默认不再 spawn `expense-extractor` / `expense-auditor` 子 agent**，由你在本会话内一次性完成“事实提取 + 合规判断 + 输出”。只有在确需多业务域协同（HR / legal 辅助域）时才调度子 agent。

1. 解析输入，尽量少往返：
   - 目录：用**一次** `Glob` 列出目录内文件，再 `Read` 关键材料（`audit-request.json`、申请单、报销单、发票、行程单、酒店单据等），综合全部材料，不要只看第一个文件。
   - 单文件：直接 `Read`。
   - 不要用 `Bash test -d` / `find` 这类额外探测，能用 `Read` / `Glob` 就不要多发往返；同一份材料只读一次。
2. 在内部完成“事实提取”作为事实底稿：`claim_id`、申请人、类别、金额、币种、日期、发票号、附件、`missing_fields`、`ambiguities`、字段间冲突。**不要为此单独输出或单独调用 extractor**，提取与判断在同一会话内连续完成。
3. **一次性** `Read` 本案适用的本地规则文件（按 `category` 选择，可一并读取）：
   - 通用流程 / 个人垫付阈值 → `knowledge/expense/general.rules.json`
   - 票据 → `knowledge/expense/invoice.rules.json`
   - 借款 / 责任链 → `knowledge/expense/loan.rules.json`
   - 招待 → `knowledge/expense/entertainment.rules.json`
   - 差旅 / 住宿 / 交通 / 补助 → `knowledge/expense/travel.rules.json`、`knowledge/expense/transport.rules.json`
   - 阈值速查 → `knowledge/expense/thresholds.json`（与主规则文件冲突时以主规则为准）
   读取每个规则文件顶层 `source` 作为追溯信息；不要现场从 PDF 重新造规则。规则文件缺失时按降级规则输出 `manual_review`（`rule_gap`），不要编造规则。
4. 如 `knowledge/memory/expense/` 中存在与本案高度相似的案例 / 异常 / 复核记忆，作为辅助证据（`memory:` 来源）写入 `evidence_chain`，不能替代结构化规则。
5. 在**同一次推理**中完成合规判断：规则命中（`priority` 越小越优先，同优先级 `reject` 优先于 `approve`）、金额 / 限额 / 比例、预算与流程、事前申请一致性、发票有效性、异常迹象，据此给出 `verdict` / `risk_score` / `policy_refs`（必须来自命中的 `rule_id`）/ `evidence_chain`。
6. 审核时只使用本地规则与制度文件，不使用训练记忆中的制度，不编造缺失的规则、附件或审批记录。

## 复核与辅助域

- 【暂时关闭复核】一律只做一次性审核，**不调度 `expense-reviewer`**；即使命中高风险、证据冲突或 `manual_review`，也只在结论中如实标注，交人工另行处理，不在本流程内发起第二轮 SDK 复核。
- 仅在以下条件才调度 HR 辅助域（`attendance-checker` / `leave-auditor`）：差旅 / 交通报销涉及周末、节假日、打卡、请假、调休、加班或出勤冲突，或需要“考勤 / 出勤事实”作为旁证。
- 仅在以下条件才调度 legal 辅助域（`contract-reviewer`）：材料包含合同 / 协议 / 付款约定，或高额付款、采购、合作、供应商结算需要合同条款佐证。

## 输出契约

1. 最终审核结论必须符合 `.claude/contracts/common/audit-result.schema.json`。决策只用 `verdict`（`approved` / `rejected` / `manual_review`）表达；不要输出 `result` / `conclusion`，它们由服务端从 `verdict` 派生（schema 也不接受这两个字段）。
2. `explanation`、`reasons`、`evidence_chain` 必须使用中文。
3. `manual_review` 时，`explanation` 必须明确写出不能自动放行的原因、缺少什么材料，或哪条规则无法闭合。
4. `manual_review` 时，必须同时填写 `manual_review_reason`，且只能从以下枚举中选择一个最贴切的原因：
   - `missing_approval`
   - `rule_gap`
   - `data_conflict`
   - `insufficient_evidence`
   - `budget_exceeded`
   - `invoice_invalid`
   - `pre_approval_mismatch`
5. 如输出 `risk_dimensions`，每项都必须是 `{name, score}` 结构，`name` 只能取 `invoice / amount / approval / budget / anomaly`，`score` 必须为 0-10 整数。
6. 只返回一个 JSON 对象，且该 JSON 对象必须直接符合 `.claude/contracts/common/audit-result.schema.json`；不要输出 Markdown、表格、解释性前言、分节标题或任何 JSON 之外的文字。
7. 优先直接返回完整审核结果给调用方，不要手工再包装一层新的 envelope，也不要手工写入重复的 `logs/results/by-request/...` 文件。

参数: $ARGUMENTS
用法: /audit data/case1
目录示例: /audit data/case1
