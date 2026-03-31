---
name: expense-audit-amount-validate
description: Use when 需要判断费用金额、住宿标准、补助、报销比例或审批阈值是否命中本地 expense 规则
---

# 报销金额与阈值校验

## 读取顺序

- 主规则文件优先：
  - 差旅与住宿 → `knowledge/expense/travel.rules.json`
  - 招待 → `knowledge/expense/entertainment.rules.json`
  - 发票比例与时效 → `knowledge/expense/invoice.rules.json`
  - 通用流程与个人垫付阈值 → `knowledge/expense/general.rules.json`
- `knowledge/expense/thresholds.json` 仅用于快捷定位阈值；若与主规则文件冲突，以主规则文件为准。
- 制度追溯源：`knowledge/external/数睿员工手册.pdf` 第 `6.3.4`、`6.5.2`、`6.6.2`、`6.7.3` 节。

## 校验步骤

1. 先识别费用类别、职级、城市等级、人数、日期范围、是否个人垫付、票据金额与报销金额。
2. 只在结构化 rules 已提供明确数字时做金额比较，例如住宿上限、出差补助、无票报销比例、事前申请金额门槛、对公付款阈值、合同阈值。
3. 计算输出至少包含：
   - `matched_rules`
   - `actual_amount`
   - `allowed_amount` 或 `allowed_ratio`
   - `variance`
   - `required_approval`
4. 需要引用的 `policy_refs` 必须来自命中的 `rule_id`，不要直接写自然语言结论。

## 直接转人工复核的情况

- 城市等级、职级、人数或费用归属缺失
- `thresholds.json` 与主规则文件数值不一致
- 同一费用在报销单、票据、事前申请之间金额冲突
- 规则只给出原则性描述而未给出可执行数字
