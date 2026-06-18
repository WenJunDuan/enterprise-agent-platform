# Tender 招投标评标域 Design

> Sprint 2026-06-18 · Path: Feature · 对话驱动开发，事后补档（未走显式 PACE stage 切换）

## Goal

新增第 5 个业务域 `tender`（招投标评标），让平台能按招标文件评分标准对投标文件评分 + 合规判定，输出可追溯结论。

起因：用户用 DeepSeek 快速模式评一份真实标（川姜花苑 R2024-007 施工总承包），DeepSeek 把"项目负责人答辩 / 企业信用 / 价格标"三项因"投标文件里没有"判 0——正是本平台宪法禁止的过度确定。本域要把这类不可判定项纠正为 `manual_review`。

## Scope

涉及：

- domain key `tender`（小写 ascii，与 expense/hr/legal 一致；rule_id 形如 `tender_r2024007_004`）
- 三 agent：`tender-extractor` / `tender-evaluator` / `tender-reviewer`（reviewer 默认关闭，对齐 expense 现状）
- 两契约：`contracts/tender/{extract-result,review-delta}.schema.json`（audit-result 复用 `common`）
- skill：`skills/tender-eval`（评标总控 + 不可判定项 → manual_review + 降级规则）
- 知识两层：`knowledge/tender/statute.rules.json`（通则，待生成）+ `knowledge/tender/{招标编号}.rules.json`（项目级）
- 路由：`CLAUDE.md` 表 + tender 调度段 + 多域协同示例；`rule-init` skill 加 tender 两层说明
- enum：`rule.schema.json` + `init-rules-report.schema.json` 各加 `"tender"`

不涉及（留 v2）：

- 资格审查 / 一票否决 / 串标围标识别等程序合规
- `/audit` 内联自动按域路由（仍 expense 硬编码 `EXPENSE_RULES_DIR`，tender 走专用 agent 规避）
- `server/` 任何 Python 改动（本域纯 `.claude/` + `knowledge/` 配置驱动，零代码）

## Key Decisions（与用户对齐）

1. 域名 `tender`（而非 bidding / procurement）——伞形名 + 与现有 ascii key 一致。
2. 规则**混合两层**：通则 `statute`（跨项目稳定）+ 项目 `{招标编号}`（每标一份），都由 `/init-rules` 从真实源文件生成。
3. v1 只做评分评审，程序合规留 v2。

## Design

### 不可判定项 → manual_review（核心，零 schema 改动）

评分规则用现成的 `tags` 字段打标：

- `requires_live_event`（答辩等现场环节）
- `requires_external_data`（企业信用等外部公示数据，不在投标文件内）
- `requires_cross_bid_comparison`（价格分需横向比较所有投标报价）

`tender-evaluator` 命中即 `status:"manual_review"`、`score:null`，**绝不判 0**。逐项写入 `extracted_data.scoring`（`{item, max, score, status, basis}`），整体 `verdict` 至少 `manual_review`。

### 一致性核验

业绩项目经理 ≠ 拟派项目负责人 → 该业绩项 `manual_review` / 不得分（`data_conflict`），证据链同时引用两处出处（业绩页 + 拟派负责人页）。姓名跨文件写法不一致（如 牛亚犇 / 生亚犇）由 extractor 写入 `ambiguities`。

### 输出

每份投标 → 一个符合 `common/audit-result` 的结论：`verdict` / `policy_refs`（命中的 rule_id）/ `evidence_chain` / `risk_score`。决策只用 `verdict`，不输出 `result` / `conclusion`（服务端派生）。
