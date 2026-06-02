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

## 执行顺序（一次性，少往返）

> 本文件是审核细则的**参考手册**，不是必走的串行调用链。审核时应直接读取下列规则文件并在一次推理中完成校验，避免为每个子能力各发起一次模型往返。下面的 `expense-audit-*` 子 skill 仅在某条细则拿不准时按需查阅。

1. 优先消费 `expense-extractor` 输出的结构化数据；若当前只有原始附件，不要直接猜字段，先回到提取阶段。
2. 一次性读取本案适用的 `knowledge/expense/*.rules.json`（按 `category` 选择，见上方“本地规则与制度源”），读取顶层 `source` 作为追溯信息；不要在审核现场直接从 PDF 重新提取新规则。可参考的细则：
   - 票据 → `expense-audit-invoice-parse`
   - 差旅/住宿/交通/补助 → `expense-audit-travel-compliance`
   - 招待/礼品/客户陪同 → `expense-audit-entertainment-compliance`
   - 事前申请一致性 → `expense-audit-pre-approval-match`
   - 预算/流程/借款/责任链 → `expense-audit-budget-check`
   - 金额/限额/审批阈值 → `expense-audit-amount-validate`
3. 规则命中后，读取 `knowledge/memory/expense/` 中的案例/异常/复核记忆作为辅助证据（不能替代结构化规则）：
   - 命中且与判断一致 → 以 `memory:` 来源写入 evidence chain
   - 命中但不适用当前案件 → 在 `explanation` 说明不适用原因
4. 在同一次推理中整理 `policy_refs`（来自命中的 `rule_id`）、`evidence_chain` 与 `verdict`，三者必须一致，并直接产出符合契约的最终结果，不必再单独调用 `common-evidence-chain` / `common-result-format` 包一层。

## 降级规则

出现以下任一情况时，停止给出确定性通过结论，输出 `manual_review`：

- 未命中结构化规则
- 关键字段缺失，例如职级、城市、发票抬头、预算归属、出差起止时间
- 多份附件互相冲突且无法唯一解释
- OCR/扫描质量不足以稳定提取关键字段
- 结构化 rules 与制度来源存在覆盖缺口，需要后续用 `system-rule-init` 补齐
