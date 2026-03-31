---
name: expense-audit-budget-check
description: Use when 需要核对报销流程、预算归属、审批责任、个人垫付条件或借款结清要求
---

# 报销预算检查

## 读取规则

- `knowledge/expense/general.rules.json`
- `knowledge/expense/loan.rules.json`
- `knowledge/expense/thresholds.json`
- 制度追溯源：`knowledge/external/数睿员工手册.pdf` 第 `6.3.1`、`6.3.2`、`6.3.4`、`6.4.2`、`6.4.3` 节

## 检查内容

1. 核对是否满足完整报销流程：提交人、直接领导、预算分管领导、纸质单据、财务稽核、出纳付款。
2. 核对费用归属是否符合“谁受益、谁报销”，并确认预算分管领导与费用归属匹配。
3. 检查是否存在无预算、超预算、未经审批的费用；这些情况不能直接判定为通过。
4. 对个人垫付场景检查：
   - 单次金额是否超过对公付款阈值
   - 超过合同阈值时是否具备双签版合同复印件
5. 对借款场景检查：
   - 是否承诺还款时间
   - 是否前账未清又新增借款
   - 是否存在借款逾期或挪用风险

## 输出要求

- 输出 `matched_rules`、`budget_findings`、`required_workflow_steps`、`approval_gaps`
- 缺少预算口径、审批链、借款状态或合同附件时，输出 `manual_review`
