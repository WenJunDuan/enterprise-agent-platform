# Tender 评标 Harness Design（最终版）

> Sprint 2026-06-19 · Path: Feature · 架构深度讨论后定稿，与用户多轮锁定。
> **演进**：早期设想"OCR 流水线 + data/tenders 文件存储"已**作废**。用户拍板改为
> **AI 直读文件、无 OCR、多步、单 agent 内联**。本文为最终设计；下方 plan.md / checklist.yaml
> 为可执行计划（供 Claude Code 接手）。

## Goal

让 tender 域处理真实评标的数据量（招标文件 + ~18 投标章节，40MB+ PDF），对每个投标人产出一个带**页级 evidence_chain** 的 `common/audit-result`，可续跑、可审计、可解释。

## 锁定的决策

1. **AI 直读、无 OCR**：模型经 API 直接 `Read` 文件（PDF/图片/文本），不接 OCR 流水线。
2. **单 agent 内联命令**驱动：`/evaluate-bid` 一个会话内连续跑五步，对齐 expense `/audit` 的低延迟内联。
3. **大数据量靠分步压缩**：S2 把几十 MB 原件读成几 KB 事实底稿；S3 在小底稿上"整袋一次过"，仅在某项需核时按页回读章节原文。投标章节过多时，S2 可用 `Task` 并行拆给子 agent。
4. **范围 v1**：单投标人（对标川姜花苑 R2024-007）；价格横比/有效投标数等多投标人项保持 `manual_review`，留 v2。
5. **规则两层**：通则层 `knowledge/tender/statute-*.rules.json`（一法一文件）+ 项目层 `knowledge/tender/{招标编号}.rules.json`（招标文件第三章评标办法，`/init-rules` 生成）。
6. **入口两者都要**：`/evaluate-bid` 命令（先）+ HTTP 路由 `/tender/evaluate`（后）。产物仍是 `common/audit-result`。

## 五步 Harness（S0–S4，单 agent 内联，详见 .claude/commands/evaluate-bid.md）

- **S0 立案清点**：`Glob` 目录 → 分类（招标/投标章节/投标人）→ 文件清单。
- **S1 评分计划**：读项目层 + 通则层规则 → 评分项清单 `{item,max,rule_ids,需读章节,tag}`；项目规则缺失 → 该项 `manual_review(rule_gap)`。
- **S2 事实抽取**：按需读相关投标文件 → `extract-result`（投标人/拟派负责人+证号+页/业绩+项目经理+页/报价/章节-页码索引）；一致性红旗写进 `ambiguities`。
- **S3 逐项评判**：每项 → `{item,max,score,status,basis}`；`requires_live_event/external_data/cross_bid_comparison` → `manual_review`/`score:null`/**不判 0**；废标/资格否决 → `rejected`；业绩 PM≠拟派 PM → `data_conflict` 引两处出处。
- **S4 汇总**：合成 `verdict` + `policy_refs`(命中 rule_id) + 页级 `evidence_chain` + `risk_score`，逐项 `scoring` 入 `extracted_data`。

## 已就位（本 session 完成）

- 域注册：`rule.schema.json` / `init-rules-report.schema.json` enum + `tender`；`CLAUDE.md` 路由表 + 调度段 + 多域协同。
- agents：`tender-extractor` / `tender-evaluator` / `tender-reviewer`（reviewer 默认关）。
- 契约：`contracts/tender/{extract-result,review-delta}.schema.json`（audit-result 复用 common）。
- skill：`tender-eval`；`rule-init` skill 加 tender 两层说明。
- 命令：`.claude/commands/evaluate-bid.md`（五步内联 harness），已与 CLAUDE.md 接线、校验通过。
- 规则：`statute-evalmethod`(13) + `statute-regulation`(8) + 项目样例 `r2024007`(5, confidence:medium 待真招标文件覆盖)；源文件在 `knowledge/external/`。

## 不涉及（v2 / backlog）

- 多投标人 S5 价格横比/排序；资格审查/一票否决/串标围标自动识别；
- 余下 statute 法规（招标投标法顶层、实施条例 ch4、政府采购法 + 87号令 → `govproc-*`）；
- `audit-result.risk_dimensions.name` 加 tender 维度；`/audit` 按域自动路由。

## 已知坑（务必避免）

- **分层守卫**：feature 模块（audit/ocr/tender）互不 import；OCR/跨域组合放上层（routes/worker）。本方案走内联命令，路由只调 `command_adapter`，**无需新建 server/tender feature 模块**。若新建，必须在 `tests/test_layering.py` 扩展兄弟守卫纳入 tender。
- **存储**：结构化/索引/结论入 `data/db/platform.sqlite3`；不要复活 `meta.json` / by-request 文件树。
- **rule_id 用下划线**：`tender_evalmethod_001`（`rule-init/SKILL.md` 第5步写的点号是历史笔误，别跟）。
- **不判 0**：不可判定项一律 `manual_review`，禁止用 0/空冒充判定。
- **措辞克制**：`result-format` 禁用"硬伤/铁证/实锤"等词；定性留余地。
