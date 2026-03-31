---
name: common-result-format
description: Use when 需要把审核结论整理成 audit-result schema 要求的统一 JSON 结果
---

# 通用结果整理

适用于所有需要输出统一审核结论的业务域，目标 schema 位于 `.claude/contracts/common/audit-result.schema.json`。

## 判定规则

- `approved`: 所有必需检查完成，未命中拒绝规则，且 `policy_refs` 非空
- `rejected`: 命中明确拒绝规则，或事实足以确定不合规
- `manual_review`: 缺证据、缺规则、规则冲突、结构化信息不足、附件质量不足

## 字段要求

- `policy_refs`: 使用 `rule_id` 数组，不要写自然语言摘要
- `risk_score`: `0-30` 低风险，`31-69` 中风险，`70-100` 高风险
- `extracted_data`: 仅保留已确认的结构化字段，不要补全不存在的信息
- `evidence_chain`: 严格使用 `source/finding/conclusion`
- `reviewed_by`: 当前 agent 名称，例如 `expense-auditor`
- `timestamp`: ISO 8601 字符串

## 禁止事项

- 不要输出 schema 之外的字段
- 不要在 `approved` 或 `rejected` 时让 `policy_refs` 为空
- 不要把待确认事项伪装成通过结论

输出格式如下：

```json
{
  "claim_id": "",
  "verdict": "approved | rejected | manual_review",
  "reasons": [],
  "policy_refs": [],
  "risk_score": 0,
  "extracted_data": {},
  "evidence_chain": [],
  "reviewed_by": "",
  "timestamp": ""
}
```
