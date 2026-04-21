---
description: 审核单个输入文件或目录
allowed-tools: Read, Write, Glob, Skill, Task
---

读取指定输入路径，路径既可以是单个文件，也可以是一个目录。

执行要求：

1. 如果输入是单个文件，直接读取该文件，调度 `expense-extractor` → `expense-auditor`；仅在触发复核条件时再调度 `expense-reviewer`。
2. 如果输入是目录，先枚举目录下相关材料，再综合目录内申请单、报销单、发票、行程单、酒店单据等文件一起审核，不要只看第一个文件。
3. 审核时只使用当前仓库本地规则、skills、agents 和制度文件，不要使用训练记忆中的制度，不要编造缺失规则。
4. 如果 `knowledge/memory/{domain}/` 中存在与当前案件高度相似的案例/异常/复核记忆，可以把它作为辅助证据参与判断；但记忆不能替代结构化规则，若引用了记忆，应尽量在 `evidence_chain` 中留下 `memory:` 来源。
5. 仅在以下条件触发 `expense-reviewer`：
   - 用户明确要求复核 / 第二意见
   - `risk_score >= 70`
   - 初审输出 `manual_review` 且 `manual_review_reason ∈ {data_conflict, pre_approval_mismatch, missing_approval, invoice_invalid}`
   - 初审发现证据冲突或无法形成单一稳定解释
6. 仅在以下条件触发 HR 辅助域（`attendance-checker` / `leave-auditor`）：
   - 差旅/交通报销涉及周末、节假日、打卡、请假、调休、加班或出勤冲突
   - 当前案件需要“考勤/出勤事实”作为辅助证据
7. 仅在以下条件触发 legal 辅助域（`contract-reviewer`）：
   - 材料包含合同/协议/付款约定
   - 高额付款、采购、合作、供应商结算需要合同条款佐证
8. 最终审核结论必须符合 `.claude/contracts/common/audit-result.schema.json`，同时包含完整结构化字段以及 `result`、`conclusion`、`explanation`。
9. `conclusion`、`explanation`、`reasons`、`evidence_chain` 必须使用中文。
10. `manual_review` 时，`conclusion` 必须固定为 `待人工复核`，且 `explanation` 必须明确写出不能自动放行的原因、缺少什么材料，或哪条规则无法闭合。
11. `manual_review` 时，必须同时填写 `manual_review_reason`，且只能从以下枚举中选择一个最贴切的原因：
   - `missing_approval`
   - `rule_gap`
   - `data_conflict`
   - `insufficient_evidence`
   - `budget_exceeded`
   - `invoice_invalid`
   - `pre_approval_mismatch`
12. 如输出 `risk_dimensions`，每项都必须是 `{name, score}` 结构，`name` 只能取 `invoice / amount / approval / budget / anomaly`，`score` 必须为 0-10 整数。
13. 只返回一个 JSON 对象，且该 JSON 对象必须直接符合 `.claude/contracts/common/audit-result.schema.json`；不要输出 Markdown、表格、解释性前言、分节标题或任何 JSON 之外的文字。
14. 优先直接返回完整审核结果给调用方，不要手工再包装一层新的 envelope，也不要手工写入重复的 `logs/results/by-request/...` 文件。

参数: $ARGUMENTS
用法: /audit data/case1
目录示例: /audit data/case1
