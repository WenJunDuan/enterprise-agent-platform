# A-002 自审：Agent 中间契约

## 结论

- VERDICT: PASS

## 本轮目标

- 给 `expense-extractor` 增加稳定的事实提取契约
- 给 `expense-reviewer` 增加稳定的复核差异契约
- 明确 `extractor -> auditor -> reviewer` 的输入输出职责边界

## 实际改动

- 新增 `.claude/contracts/expense/extract-result.schema.json`
  - 约束 extractor 只输出事实性字段
  - 明确 `applicant`、`expense`、`invoice_numbers`、`attachments`、`missing_fields`、`ambiguities`
  - 显式禁止把 `verdict` 等业务判断字段混入 extractor 结果
- 新增 `.claude/contracts/expense/review-delta.schema.json`
  - 约束 reviewer 输出“与初审相比发生了什么变化”
  - 包括 `agrees_with_initial`、`disagreement_points`、`additional_policy_refs`、`additional_evidence_chain`、`final_recommendation`
  - 增加 if/then 规则：不同意初审时，`disagreement_points` 至少一项
- 更新 `.claude/agents/expense/extractor.md`
  - 明确输出必须符合 `extract-result.schema.json`
  - 明确“只提取事实，不做合规判断”
- 更新 `.claude/agents/expense/auditor.md`
  - 明确消费 `extract-result`
  - 明确当前主产物仍是 `audit-result`
  - 明确高风险时把原始材料 + `extract-result` + 初审 `audit-result` 一起交给 reviewer
- 更新 `.claude/agents/expense/reviewer.md`
  - 明确 reviewer 直接产物是 `review-delta`
- 更新 `.claude/CLAUDE.md`
  - 把 expense 主链路的两个中间契约挂到全局调度说明里
- 更新 `.ai_state/design/agent-next-phase-blueprint.md`
  - 将 A-002 的职责分工从概念说明收紧成明确执行口径

## 验证

- 新增 `tests/test_agent_contracts.py`
  - 验证 `extract-result.schema.json` 可接受有效 payload
  - 验证 extractor schema 拒绝 `verdict` 这类业务判断字段
  - 验证 `review-delta.schema.json` 可接受有效 payload
  - 验证 reviewer disagreement 约束生效
  - 验证 agent 文本显式引用了对应 contracts
- `uv run pytest tests/test_agent_contracts.py` 通过
- `uv run pytest` 通过，当前共 33 项
- `uv run ruff check server tests` 通过

## 为什么这版更对

1. extractor 不再只是“提几个字段”的模糊角色，而是有了明确的事实提取边界。
2. reviewer 不再只是“再看一遍并给意见”，而是明确承担“输出复核差异”的职责。
3. 后续 A-003 做业务记忆沉淀时，可以直接消费稳定的 `audit-result` 与 `review-delta`，而不是去解析自由文本。
4. 后续 A-005 做追溯查询时，`review_delta` 也已经具备可检索的结构。

## 风险与遗留

- 当前 contracts 只在文档和测试层落地，还没有在 Claude runtime 中通过 `output_format` 强制中间 agent 一定产出这些 schema；也就是说，它们现在是“明确的设计契约”，还不是“运行时硬约束”。
- 由于现有主流程最终仍只对 `audit-result` 做 Python 侧 schema 校验，`extract-result` 与 `review-delta` 目前主要用于稳定协作和后续扩展，不直接进入 Python API 返回。
- `.claude/skills/` 的能力名与 agent 中引用的 skill 名目前仍带有“分组目录 + 逻辑能力名”混用现象。A-002 已经把 handoff 契约补齐，但 skill 关系进一步收口仍可在后续小轮次继续优化。

## 下一步建议

- 进入 A-003：设计并落地审后业务记忆沉淀层
- 记忆层建议直接建立在 `audit-result` + `review-delta` 两类结构化产物之上，不再回退到自由文本总结
