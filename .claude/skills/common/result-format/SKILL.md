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

- 决策只用 `verdict` 表达；`result`（布尔）与 `conclusion`（中文标签）由服务端从 `verdict` 派生，**不要输出**（schema 也不接受这两个字段）
- 必须输出的字段：`claim_id`、`verdict`、`explanation`、`reasons`、`policy_refs`、`risk_score`、`extracted_data`、`evidence_chain`、`reviewed_by`、`timestamp`
- 服务端派生映射（仅供理解，无需你输出）：`approved→合规` / `rejected→不合规` / `manual_review→待人工复核`
- `policy_refs`: 使用 `rule_id` 数组，不要写自然语言摘要
- `risk_score`: `0-30` 低风险，`31-69` 中风险，`70-100` 高风险
- `extracted_data`: 仅保留已确认的结构化字段，不要补全不存在的信息
- `evidence_chain`: 严格使用 `source/finding/conclusion`
- `reviewed_by`: 当前 agent 名称，例如 `expense-auditor`
- `timestamp`: ISO 8601 字符串
- `explanation`: 必须使用中文，并写成“根据……规定，判断……”的句式
- `manual_review`: `explanation` 必须明确说明为什么不能自动放行、缺少什么材料，或哪条规则无法闭合

## 禁止事项

- 不要输出 schema 之外的字段
- 不要在 `approved` 或 `rejected` 时让 `policy_refs` 为空
- 不要把待确认事项伪装成通过结论
- 不要遗漏任一必需字段
- 不要输出 `result` / `conclusion`（由服务端派生）
- 不要输出英文版审核意见

输出格式如下：

```json
{
  "claim_id": "EXP-2026-031",
  "verdict": "manual_review",
  "explanation": "根据《费用报销管理制度》差旅申请规定，判断该事项暂不能自动放行，缺少出差申请单，现有规则链路无法闭合，需人工复核。",
  "reasons": [
    "缺少出差申请单，无法核对事前审批是否满足制度要求"
  ],
  "policy_refs": [
    "expense.travel.012"
  ],
  "risk_score": 68,
  "extracted_data": {
    "category": "travel",
    "applicant": "张三",
    "amount": 1280
  },
  "evidence_chain": [
    {
      "source": "rule:expense.travel.012",
      "finding": "制度要求差旅报销需提供有效事前申请记录",
      "conclusion": "当前材料未提供对应申请单，证据不足"
    }
  ],
  "reviewed_by": "expense-auditor",
  "timestamp": "2026-03-31T09:30:00+08:00"
}
```
