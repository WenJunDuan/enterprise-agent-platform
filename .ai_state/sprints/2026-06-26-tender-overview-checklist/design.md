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

## 设计方案

### 后端（优先零改动）
- 概要 checklist 完全可由前端从 `extracted_data.{eligibility_checks,disqualification_hits,scoring}` 派生，
  **首选不改后端**。
- 仅当需要统一"达成判定"口径供多端复用时，再在 server 侧加**纯展示派生** helper（不碰判分、不改 schema）；
  本 Sprint 默认不走这条，列为可选。

### 前端（agent-front，红区）
- 详情页导航/标签顺序改为：**概要分析（新，首位）→ 详细分析 → 评分对比 → 报告**。
- `model.ts` 新增 `buildOverviewChecklist(result): ChecklistItem[]`（与 S5 `buildIssueList` 共享底层派生，
  避免两套口径）。`ChecklistItem = { group, requirement, status: met|unmet|pending, reason, evidence[] }`。
- 新组件 `OverviewChecklist`：按组（资格审查 / 否决条款 / 硬性响应 / 材料形式）渲染，每行
  [✓/✗/⏳ 图标 + 颜色] + 要求名 + 理由（默认折叠，展开看 evidence 出处页）。
- `types.ts` 增 `ChecklistItem` / `ChecklistStatus`。
- 兼容旧结果：无 eligibility_checks/disqualification_hits 的旧数据 → checklist 退化为可派生项，不崩。

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
