---
name: expense-audit-pre-approval-match
description: Use when 需要比对差旅或招待的事前申请与实际报销内容，判断申请前置条件是否满足
---

# 报销事前匹配

## 读取规则

- 差旅场景：`knowledge/expense/travel.rules.json`
- 招待场景：`knowledge/expense/entertainment.rules.json`
- 制度追溯源：`knowledge/external/数睿员工手册.pdf` 第 `6.5.2`、`6.5.3`、`6.6.3`、`6.6.4` 节

## 对比维度

1. 是否存在有效的事前申请记录。
2. 申请时间是否早于实际发生时间。
3. 申请中的金额、目的地、出差事由、参与人、预计时长是否与实际报销一致。
4. 是否存在：
   - 事后补提申请
   - 超出申请金额
   - 超出预计时间但未重新申请
   - 实际行程被拆分报销

## 输出要求

- 输出 `matched_rules`、`pre_approval_status`、`mismatch_fields`、`policy_refs_candidates`
- 若规则要求事前申请但记录缺失，或申请记录与事实冲突且无法确认，输出 `manual_review`
