---
name: expense-audit-invoice-parse
description: Use when 需要解析发票、收据、电子票据或行程单，并按本地 invoice 规则检查票据合规性
---

# 报销票据解析

## 读取规则

- `knowledge/expense/invoice.rules.json`
- `knowledge/expense/general.rules.json`
- 制度追溯源：`knowledge/external/数睿员工手册.pdf` 第 `6.3.3`、`6.3.4` 节

## 提取字段

至少提取以下字段：

- `invoice_number`
- `invoice_type`
- `issue_date`
- `amount`
- `tax_amount`
- `invoice_title`
- `payer_entity`
- `is_e_invoice`
- `receipt_type`
- `source_doc`

## 检查步骤

1. 将票据事实与报销单事实对齐，检查金额、主体、日期是否一致。
2. 按 `invoice.rules.json` 检查：
   - 是否要求原始发票
   - 缺发票时是否只能部分报销
   - 发票是否超出 `90/180` 天窗口
   - 电子发票是否疑似重复
   - 收款收据、定额发票、抬头不一致是否违规
3. 若发现制度源提到但结构化 rules 尚未覆盖的票据问题，只能标记“规则覆盖缺口”，不要自行扩展判断标准。

## 输出要求

- 产出 `normalized_invoices`、`invoice_findings`、`policy_refs_candidates`
- OCR 置信度不足、票据字段缺损或多张票据互相冲突时，直接输出 `manual_review`
