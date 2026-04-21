---
name: expense-audit
description: Use when 审核报销、发票、差旅、招待或借款事项，需要基于本地 expense 规则文件编排子技能并输出可追溯结论
---

# 报销审核总控

## 本地规则与制度源

- `knowledge/expense/general.rules.json` ← `knowledge/external/数睿员工手册.pdf` 第 `6.3` 节
- `knowledge/expense/invoice.rules.json` ← `knowledge/external/数睿员工手册.pdf` 第 `6.3.3`、`6.3.4` 节
- `knowledge/expense/loan.rules.json` ← `knowledge/external/数睿员工手册.pdf` 第 `6.4` 节
- `knowledge/expense/entertainment.rules.json` ← `knowledge/external/数睿员工手册.pdf` 第 `6.5` 节
- `knowledge/expense/travel.rules.json` ← `knowledge/external/数睿员工手册.pdf` 第 `6.6` 节
- `knowledge/expense/transport.rules.json` ← `knowledge/external/数睿员工手册.pdf` 第 `6.7` 节
- `knowledge/expense/thresholds.json` 是上述结构化规则提炼出的阈值聚合，不是独立制度源

## 执行顺序

1. 优先消费 `expense-extractor` 输出的结构化数据；若当前只有原始附件，不要直接猜字段，先回到提取阶段。
2. 根据 `category`、费用明细和附件类型选择子 skill：
   - 票据类 → `expense-audit-invoice-parse`
   - 差旅/住宿/交通/补助 → `expense-audit-travel-compliance`
   - 招待/礼品/客户陪同费用 → `expense-audit-entertainment-compliance`
   - 事前申请一致性 → `expense-audit-pre-approval-match`
   - 预算/流程/借款/责任链 → `expense-audit-budget-check`
   - 金额、限额、审批阈值 → `expense-audit-amount-validate`
3. 所有规则命中必须先通过 `common-rule-query` 从本地 JSON 读取；不要在审核现场直接从 PDF 重新提取新规则。
4. 在规则命中完成后，再通过 `common-memory-query` 查询 `knowledge/memory/expense/` 中的案例/异常/复核记忆；记忆只能作为辅助证据，不能替代结构化规则。
   - 如果记忆命中且与你的判断一致，把它以 `memory:` 来源写入 evidence chain
   - 如果记忆命中但你认为当前案件不适用，也要在 `explanation` 里说明不适用原因
5. 汇总结论前必须交给 `common-evidence-chain` 与 `common-result-format`，确保 `policy_refs`、`evidence_chain`、`verdict` 一致。

## 降级规则

出现以下任一情况时，停止给出确定性通过结论，输出 `manual_review`：

- 未命中结构化规则
- 关键字段缺失，例如职级、城市、发票抬头、预算归属、出差起止时间
- 多份附件互相冲突且无法唯一解释
- OCR/扫描质量不足以稳定提取关键字段
- 结构化 rules 与制度来源存在覆盖缺口，需要后续用 `system-rule-init` 补齐
