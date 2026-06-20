---
name: tender-eval
description: Use when 评标、招投标评分、投标文件合规审查，需要基于本地 tender 两层规则评分并输出可追溯结论
---

# 评标总控

## 本地规则与评分标准

- **通则层国家法规**（稳定、跨项目，作**法律底座**）：
  - `knowledge/tender/evalmethod.rules.json` ←《评标委员会和评标方法暂行规定》（发改委12号令）
  - `knowledge/tender/regulation.rules.json` ←《招标投标法实施条例》
  - 由 `/init-rules <法规源文件> tender` 生成；管废标 / 资格 / 一致性 / 程序的法定依据，**不含**具体项目的分值权重。
- **会话项目评分标准（criteria）**（每标一份，**不预建**）：本项目评分项 / 满分 / 评分规则就在**它自己的招标文件第三章《评标办法》**里，评标时由 `/tender-evaluate` 在 S1 **直读招标文件**解析为 `extracted_data.criteria`（对齐 `.claude/contracts/tender/criteria.schema.json`），随结论持久化作本次会话规则。

> 通则层 `rule_id` 形如 `tender_evalmethod_001` / `tender_regulation_003`（下划线连接），可作 `policy_refs`。criteria 来自招标文件第三章、**无 `rule_id`**，其标准与命中写入 `evidence_chain`。

## 执行顺序（一次性，少往返）

1. 优先消费 `tender-extractor` 输出的结构化事实；若当前只有原始材料，不要直接猜字段，先回到提取阶段。
2. `Read` 招标文件第三章《评标办法》直读解析为 `extracted_data.criteria`（招标文件**没写的标准不臆造补充**）；并读通则层 `evalmethod` / `regulation` 法规作法律底座，读取顶层 `source_path` / `source_version` 作为追溯。
3. 读取 `knowledge/memory/tender/` 中的相似案例 / 异常记忆作为 `memory:` 辅助证据（不能替代结构化规则）。
4. **对照 `criteria` 逐评分项判定**，写入 `extracted_data.scoring`，每项 `{item, max, score, status, basis}`；承重 `policy_refs` 只引通则层真实 `rule_id`，criteria 命中写 `evidence_chain`；一次产出契约结果。

## 不可判定项 → manual_review（绝不判 0）

评分项命中以下任一标签时，该项 `status: "manual_review"`、`score: null`，并使整体 `verdict` 至少为 `manual_review`：

- `requires_live_event`：现场环节，如项目负责人答辩、现场演示——投标文件里没有，不代表得 0。
- `requires_external_data`：外部数据，如企业信用评价（来自政府 / 行业公示表），不在投标文件内。
- `requires_cross_bid_comparison`：需横向比较，如价格分（须对所有有效投标报价统一计算）。

> 原则：文档里"找不到证据" ≠ "客观得 0 分"。把不可判定项判 0 是范畴错误，会系统性低估投标人，且对方无从申辩。这类项一律 `manual_review`，并写清需要什么（现场记录 / 外部评价表 / 全部投标报价）。

## 降级规则（输出 manual_review）

出现以下任一情况时，停止给出确定性通过结论：

- 未命中结构化规则（`rule_gap`）
- 关键字段缺失：投标报价、拟派项目负责人、业绩项目经理、资格证明
- 拟派项目负责人与业绩 / 承诺书中的姓名不一致或归属冲突（`data_conflict`）
- 多份材料互相冲突且无法唯一解释
- 缺招标文件 / 读不出第三章《评标办法》（无法取本项目 `criteria`），或通则层法规存在覆盖缺口（后者可用 `system-rule-init` 补齐）
