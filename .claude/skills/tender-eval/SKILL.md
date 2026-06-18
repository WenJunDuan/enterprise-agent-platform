---
name: tender-eval
description: Use when 评标、招投标评分、投标文件合规审查，需要基于本地 tender 两层规则评分并输出可追溯结论
---

# 评标总控

## 本地规则（两层）

- **通则层**（稳定，跨项目）：`knowledge/tender/statute.rules.json`
  ← 招标投标法 / 政府采购法 / 综合评分法通则、资格一票否决项等（把源文件放入 `knowledge/external/` 后用 `/init-rules <源文件> tender` 生成）
- **项目层**（每标一份）：`knowledge/tender/{招标编号}.rules.json`
  ← 对应招标文件第三章《评标办法》，用 `/init-rules <招标文件> tender` 生成

> tender 域的 `category` 轴用法：`statute` 表示通则层；`{招标编号}`（如 `r2024007`）表示某个具体项目的评分规则。rule_id 用下划线连接，例如 `tender_statute_001`、`tender_r2024007_004`。

## 执行顺序（一次性，少往返）

1. 优先消费 `tender-extractor` 输出的结构化事实；若当前只有原始材料，不要直接猜字段，先回到提取阶段。
2. 一次性读取通则层 + 本项目层规则；读取顶层 `source_path` / `source_version` 作为追溯；不要在评标现场直接从招标文件 PDF 重新造规则。
3. 读取 `knowledge/memory/tender/` 中的相似案例 / 异常记忆作为 `memory:` 辅助证据（不能替代结构化规则）。
4. 逐评分项判定，写入 `extracted_data.scoring`，每项 `{item, max, score, status, basis}`，并整理 `policy_refs`（来自命中的 `rule_id`）/ `evidence_chain` / `verdict`，一次产出契约结果。

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
- 通则 / 项目规则存在覆盖缺口，需要后续用 `system-rule-init` 补齐
