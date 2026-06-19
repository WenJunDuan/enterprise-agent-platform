---
description: 评标：按招标文件评分标准对一袋投标文件评分与合规判定，一次性内联产出结论
allowed-tools: Read, Glob, Skill, Task
---

读取指定投标目录（含招标文件 + 投标文件各章节），**在当前会话内一次性完成评标并直接输出最终结论**。你直接 `Read` 文件（PDF/图片/文本均可），不依赖 OCR 预处理。

## 执行方式（单 agent 内联五步，少往返）

为把单次评标压进可控时延，**默认不 spawn 子 agent**，由你在本会话内连续完成 S0–S4。仅当投标章节特别多、单会话读不下时，才用 `Task` 把 S2 事实抽取按章节并行拆给子 agent，再合并。

### S0 立案清点
- 用**一次** `Glob` 列目录文件。按文件名/内容分类：招标文件、投标文件各章节、投标人标识。
- 形成文件清单（章节号 → 文件）。不要逐字深读，先建索引。

### S1 评分计划
- `Read` 本案适用的本地规则（两层，可一并读）：
  - 项目层：`knowledge/tender/{招标编号}.rules.json`（该项目第三章评标办法的分值/权重）
  - 通则层：`knowledge/tender/statute-*.rules.json`（招标投标法实施条例、评标方法暂行规定等）
- 把评分办法逐项展开为评分计划：每项记 `{item, max, rule_ids, 需读章节, tag}`。
- 项目层规则缺失时，对相关评分项按降级走 `manual_review`（`rule_gap`），**不要现场从招标文件 PDF 编造评分规则**。

### S2 事实抽取（把大文件压成小底稿）
- 按计划里"需读章节"，逐个/分批 `Read` 相关投标文件，抽取评标所需事实，对齐 `.claude/contracts/tender/extract-result.schema.json`：
  - 投标人、统一社会信用代码、法定代表人
  - 拟派项目负责人：姓名 / 注册证号 / 出处（文件+页）
  - 业绩：每条 `项目名称 / 项目经理 / 出处（文件+页）`
  - 投标报价、章节-页码索引
- 一致性线索写进 `ambiguities`，例如"拟派负责人姓名在不同文件写法不一致（牛亚犇/生亚犇）""所报业绩项目经理与拟派负责人疑似不一致"。
- 只抽事实，不在本步给分。

### S3 逐项评判
- 对评分计划每一项，结合事实底稿（必要时按页码回读该章节原文）判定，写入 `extracted_data.scoring`，每项 `{item, max, score, status, basis}`：
  - 规则可依文档判定 → `status:"scored"`，给 `score` 与 `basis`
  - 命中"不可判定"标签 → `status:"manual_review"`、`score:null`，**绝不判 0**：
    - `requires_live_event`（项目负责人答辩等现场环节）
    - `requires_external_data`（企业信用等外部公示数据，不在投标文件内）
    - `requires_cross_bid_comparison`（价格分、有效投标数等需横向比较所有投标）
  - 命中废标 / 资格一票否决（未实质性响应、重大偏差、资格不符等）→ `status:"rejected"`
- 一致性核验：若业绩的项目经理与拟派项目负责人不一致，该业绩项 `manual_review`/不得分，`manual_review_reason:"data_conflict"`，证据链**同时引用业绩页与拟派负责人页**两处出处（依据：实施条例第40/42条、业绩与拟派负责人应一致）。

### S4 汇总结论
- 合成最终 `verdict`：
  - 命中任一废标/资格否决 → `rejected`
  - 存在任一 `manual_review` 评分项，或关键证据缺失/规则缺口/证据冲突 → `manual_review`（填 `manual_review_reason`）
  - 全部评分项 `scored` 且无否决项 → `approved`
- 给出 `policy_refs`（来自命中的 `rule_id`，如 `tender_evalmethod_005` / `tender_r2024007_004`）、页级 `evidence_chain`、`risk_score`，并把逐项 `scoring` 留在 `extracted_data` 中。

## 输出契约

1. 最终结论必须符合 `.claude/contracts/common/audit-result.schema.json`。决策只用 `verdict`（`approved` / `rejected` / `manual_review`），不要输出 `result` / `conclusion`（服务端从 `verdict` 派生）。
2. `claim_id` 为投标编号或投标人标识。
3. `explanation` / `reasons` / `evidence_chain` 用中文，措辞平实、专业、克制（像评标/审计意见）：禁用夸张或口语词（硬伤、铁证、实锤等），定性留有余地（用"疑似/需人工核实"，证据不确凿不下终局结论）。
4. `manual_review` 时，`explanation` 必须写明哪些评分项不能自动判定、缺什么材料、哪条规则无法闭合，并填 `manual_review_reason`（只能取 `missing_approval` / `rule_gap` / `data_conflict` / `insufficient_evidence` / `budget_exceeded` / `invoice_invalid` / `pre_approval_mismatch` 之一最贴切者）。
5. `extracted_data.scoring` 为逐项 `{item, max, score, status, basis}`；未判定项 `score:null` 不计入合计，并在文字中说明需要什么外部输入（现场记录/外部评价表/全部投标报价）。
6. 只返回一个 JSON 对象，直接符合 `audit-result` 契约；不要输出 Markdown、表格、前言或任何 JSON 之外的文字。
7. 评标只用本地规则与制度文件，不使用训练记忆中的规则，不编造缺失的规则、附件或评分依据。

## 复核与多投标人

- 当前为一次性内联评标，**默认不调度 `tender-reviewer`**；高风险/证据冲突在 `verdict`/`risk_score`/`explanation` 中如实标注，交人工处理。
- v1 仅评单个投标人；价格横比、有效投标数等 `requires_cross_bid_comparison` 项保持 `manual_review`，留多投标人阶段统一落定。

参数: $ARGUMENTS
用法: /tender-evaluate-bid data/tenders/r2024007
