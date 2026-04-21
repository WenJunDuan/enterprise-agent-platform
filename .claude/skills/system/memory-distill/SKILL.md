---
name: system-memory-distill
description: Use when 需要把已归档审核结果提炼为可复用的结构化业务记忆资产，并回写到 knowledge/memory
---

# 业务记忆沉淀

## 目标

把 `logs/results/by-request/...` 中已经完成归档的审核结果，提炼成可复用的业务记忆资产，写入 `knowledge/memory/{domain}/`。

这些记忆资产用于：

- 复用高频异常模式
- 固化人工复核触发经验
- 沉淀 reviewer 发现的关键分歧
- 为后续同类审核提供可追溯的案例参考

## 输入要求

1. 必须先读取待提炼的结果归档文件。
2. 必须读取 `knowledge/_schema/case-memory.schema.json`，确保输出结构合法。
3. 如存在对应的 reviewer 差异结果，也可一并读取，用于强化 `review_pattern` 类型记忆。

## 可沉淀的内容

- `case_pattern`：可复用的常见通过/拒绝模式
- `exception_pattern`：高频人工复核、证据缺失、规则冲突、预算异常等例外模式
- `review_pattern`：reviewer 对初审进行修正或升级时形成的稳定分歧模式

## 禁止沉淀的内容

- 路径不存在、网络超时、网关失败、SDK 重试等基础设施问题
- 只适用于单一文件命名错误或单次临时环境问题的噪音
- 无规则依据、无证据链支撑的主观总结
- 无法回链到 `request_id` / `result_file` 的“口头经验”

## 输出规则

1. 输出文件路径：`knowledge/memory/{domain}/{memory_id}.json`
2. `memory_id` 应稳定、可读、可追溯，推荐格式：
   - `{domain}.{category}.{pattern}.{recommended_verdict}.v1`
3. `policy_refs` 只写规则 ID，不写自然语言。
4. `recommended_verdict` 只表达建议性业务结论，不替代未来具体案件的最终 verdict。
5. `manual_review_reason` 只有在建议结论为 `manual_review` 时才填写具体值；否则填 `null`。
6. `source_trace.request_id` 和 `source_trace.result_file` 必须保留。
7. `distilled_by` 固定为 `system-memory-distill`。
8. 只在形成了稳定、可复用模式时写入；如果只是一次性噪音，则不要写文件。

## 建议提炼方法

1. 先看 `verdict`、`manual_review_reason`、`policy_refs`、`evidence_chain`。
2. 识别“这次审核里可复用的判断模式是什么”，而不是复述整份结果。
3. 提炼成：
   - 适用条件 `applicable_when`
   - 复核检查点 `checkpoints`
   - 建议结论 `recommended_verdict`
   - 简短理由 `rationale`
4. 最后保留完整回链信息，确保未来能追到原始结果。
