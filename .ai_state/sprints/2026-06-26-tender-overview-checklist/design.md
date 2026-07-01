# Sprint Design — Tender 概要分析 Checklist（S10）

> 新需求（用户 2026-06-26 提出），纳入 2026-06-tender-program 路线图为 **S10**。
> 与 S5 expert-advisory-repositioning 同源（都把专家侧从"评分结论"转向"符合性/风险提示"，
> 落地 2026-06-29 会议结论 1-2）。**本文件是设计，启动时再补 TDD。**

## 需求（用户原话）

> 目前的详情页面是「详细分析 + 评分对比 + 报告」。我需要在**详细分析前面**再加一个**概要分析**：
> 只展示类似 checklist，不需要评分，只展示招标要求有没有达到——达到打个勾 ✓，没达到打个叉 ✗，
> 下面是理由。

## 目标

详情页新增「概要分析」入口（排在详细分析之前），以**符合性 checklist** 概览本投标对招标要求的
达成情况：每条招标要求一行，✓ 达到 / ✗ 未达到 / ⏳ 待核验，下方附理由（含出处页）。**不展示任何分数。**

## 不可违反原则

- **不展示评分**：概要分析只做二元/三态符合性，不出现分数、总分、排名。
- **疑似/读不清/外部待核 → 待核验，不打叉**：`confirmed:false` 的废标信号、`manual` 资格项、读不清项
  一律 ⏳ 待核验，**绝不**当作"未达到"✗（守 2026-06-23 R2b 纪律 + 不可判定不判 0）。
- **零判分行为变更**：后端 verdict/score/scoring 逻辑不动；概要分析是**展示层对既有 extracted_data 的派生**。
- agent-front 红区：subagent + worktree 隔离，需用户授权（compound/2026-06-19-decision-agent-front-cc-out-of-scope.md）。

## 数据来源（前端从既有 extracted_data 派生，后端尽量零改）

每条 checklist 项 = 一条招标要求的达成判定，映射规则：

| 招标要求来源 | ✓ 达到 | ✗ 未达到 | ⏳ 待核验 |
|---|---|---|---|
| 资格审查 `eligibility_checks[]` | status=pass | status=fail | status=manual |
| 废标/否决 `disqualification_hits[]` | 未命中 | confirmed:true 命中 | confirmed:false 疑似/读不清 |
| 硬性响应项 `scoring[score_mode=pass_fail]` | got≥max | status=rejected 或 got=0(已核实) | manual/读不清 |
| 必交材料缺失 `scoring[status=rejected]` | — | 该项必交材料确缺 | 材料疑似在但读不清 |

- 每行理由 = 对应项的 `basis` / `evidence`（出处「文件+第N页+章节」+ quote），可展开。
- **不纳入 checklist**：档次/扣减/加分等"程度"评分项（非二元达成）→ 仍在「详细分析」展示。
- 资格审查恒置 checklist 首组（最高优先级），与现有报告分段一致。

## 设计方案（2026-07-01 定稿 — S5 已 ship，S10 复用其派生底层，不再"先于 S5"）

> 现状核实：S5 已交付 `buildIssueList`（model.ts:818，问题导向：只列 issue/risk/pending，**跳过达标项**
> `if (!pending && !failed) return`）+ 详情页 mode 切换 `detail`(详细分析)/`compare`(风险对比)
> (analysis-workbench-view.tsx)。S10 概要 checklist 是**符合性导向**（每条要求都出一行，含 ✓ 达标），
> 必须复用 S5 的**同一套源 getter + pending/failed 判定谓词**，保证两视图永不打架
> （issueList 里 pending 的项，checklist 必 ⏳，绝不 ✗）。

### 后端（零改动，已确认可行）
- checklist 完全由前端从 `selectedResult.extracted_data.{eligibility_checks,disqualification_hits,scoring}`
  派生。**本 Sprint 不改后端**（不碰判分/schema）。

### 前端（agent-front，红区）改动清单
1. `types.ts`：加 `ChecklistStatus = 'met'|'unmet'|'pending'`、`ChecklistItem`；
   `TenderReviewMode` 加 `'overview'`；`TenderReviewMockData` 加 `overviewChecklist?: ChecklistItem[]`。
   `ChecklistItem = { id, group, requirement, status, reason, evidence: TenderScoreEvidence[] }`
   —— **刻意不含 score/points/max 字段**（编译期保证无分数泄漏）。
2. `model.ts`：新增 `buildOverviewChecklist(result)`，接进 `buildTenderReviewData`
   (`overviewChecklist: buildOverviewChecklist(selectedResult)`)。**复用现有私有 helper**：
   `getEligibilityCheckRecords` / `getDisqualificationHitRecords` / `getScoringItems` /
   `isPendingSignal` / `isUnconfirmedDisqualification` / `getEligibilityStatus` / `getIssueEvidence` /
   `collectIssueText`（不新造第二套口径）。
3. 新组件 `components/overview-checklist-view.tsx`：按组渲染（资格审查 → 否决条款 → 硬性响应/材料），
   每行 [✓ emerald / ✗ red / ⏳ muted 图标+**文字标签**（不靠颜色单独传达，守 a11y P0）] + 要求名 +
   理由；evidence 出处默认折叠、可展开。沿用 `IssueListPanel` 视觉惯例。
4. `analysis-workbench-view.tsx`：ModeButton 增「概要分析」**置首** → [概要分析, 详细分析, 风险对比]；
   `BidderTabs` 展示条件 `mode === 'detail'` 放宽为 `mode !== 'compare'`（概要也是按选中投标人）；
   body 增 `mode === 'overview' → <OverviewChecklist>`。
5. `use-tender-review-page.ts`：**单投标人首屏 landing 由 'detail' 改 'overview'**（概览在前，见待定 Q1）；
   compare（≥2 家）landing 不变。

### buildOverviewChecklist 派生规则（三组，逐条要求 → met/unmet/pending）
| 组 | 源 | ✓ met | ✗ unmet | ⏳ pending |
|---|---|---|---|---|
| 资格审查 | `eligibility_checks[]` | status=pass | fail/failed/rejected | manual/manual_review/pending/pendingSignal |
| 否决条款 | `disqualification_hits[]`(仅有意义命中) | —（无全量条款清单，不合成 met 行） | confirmed 命中 | isUnconfirmedDisqualification/pendingSignal |
| 硬性响应/材料 | `scoring[]` 中 `score_mode==='pass_fail'` **或** `status==='rejected'`（按 id 去重；程度项 banded/deduction/additive/formula 一律排除） | score≥max | rejected/failed 或 score<max | manual_review/score==null/pendingSignal |

- reason = 各项 `basis`；evidence = `getIssueEvidence`（文件+第N页+quote）。
- **不纳入**：档次/扣减/加分等"程度"项 → 仍只在「详细分析」展示（塞进二元 checklist 是范畴错误）。

## 待用户拍板（启动前）
- **Q1 单投标人首屏默认落在「概要分析」还是维持「详细分析」？** 建议落「概要分析」（符合"概览在前"原意）。
- **Q2 红区授权 + 流水线确认**：worktree 隔离 → TDD 实施 → CC×Codex 多轮交叉 review → 清 worktree 合 main → 全量测 → 用户手检。

## 验收标准
- 详情页「概要分析」排在详细分析之前，纯 checklist、无任何分数。
- 三态映射正确；`confirmed:false`/`manual`/读不清 → ⏳ 待核验（不打叉）。
- 每行有理由 + 出处页可追溯。
- model.test.ts 覆盖：三态映射、confirmed:false→pending、无评分字段泄漏、旧数据兜底。
- 前端 `bun test` + lint + build 全绿；若动后端 `uv run pytest -q` 全绿。

## 风险与处理
- 风险：把"程度"评分项硬塞进二元 checklist → 误导。处理：只纳入资格/否决/pass_fail/必交材料，程度项留详细分析。
- 风险：与 S5 各搞一套派生口径 → 不一致。处理：`buildOverviewChecklist` 与 S5 `buildIssueList` 共享底层
  派生函数；建议 **S10 先做**（更聚焦、纯展示），S5 在其上扩展风险七类。
- 风险：S10 与 S5 都改详情页同文件 → 冲突。处理：顺序做（S10 → S5），或同 worktree。
- 风险：误把疑似当"未达到"。处理：见原则护栏，测试覆盖。

## 关系与排期
- 归入路线图 **S10**，stream=product，effort=M，依赖无（可独立起）；与 **S5** 同源、建议先于 S5。
- 红区：需用户授权动 agent-front + worktree 隔离。
