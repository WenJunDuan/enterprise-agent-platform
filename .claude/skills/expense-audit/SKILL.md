---
name: expense-audit
description: Use when 审核报销、发票、差旅、招待或借款事项，需要基于本地 expense 规则文件编排子技能并输出可追溯结论
---

# 报销审核总控

## 本地规则与制度源

- `knowledge/expense/travel.rules.json` ← `knowledge/external/南通市市级机关国内差旅住宿费标准.pdf`（高新区差旅须知，援引通州〔2015〕1 号《南通市通州区机关事业单位差旅费管理办法》）
- `knowledge/expense/meal.rules.json` ← `knowledge/external/南通高新区工作餐管理制度.docx`
- `knowledge/expense/entertainment.rules.json` ← `knowledge/external/南通高新区接待管理办法.docx`

## 执行顺序（一次性，少往返）

> 本文件是审核细则的**参考手册**，不是必走的串行调用链。审核时应直接读取下列规则文件并在一次推理中完成校验，避免为每个子能力各发起一次模型往返。

1. 优先消费 `expense-extractor` 输出的结构化数据；若当前只有原始附件，不要直接猜字段，先回到提取阶段。
2. 一次性读取本案适用的 `knowledge/expense/*.rules.json`，按 `category` 选择（见上方“本地规则与制度源”）：
   - 差旅 / 住宿 / 交通 / 伙食补助 → `travel.rules.json`
   - 工作餐 / 快餐 → `meal.rules.json`
   - 接待 / 商务餐 / 公务接待 / 陪餐 → `entertainment.rules.json`
   读取每个规则文件顶层 `source_path` / `source_version` 作为追溯信息；不要在审核现场直接从 PDF 重新提取新规则。
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
