# Sprint Design — 详细分析 + 风险对比 重构（显分）

> 用户 2026-07-01 需求（手动测试后反馈）。agent-front 红区,用户已授权。

## 需求（用户原话拆解）
1. 详细分析"内容要素太多",要重构:需展示**招标项目** + **分数**(单项合计、总分、实际得分),并**列出扣分**。
2. 详细分析**中间区(评审要点)+右侧区(证据底稿)保留**,改的是**左侧区**。
3. 风险对比页"综合点":加**评分**+**风险 checklist**,相当于"概要分析 list + 详细分析的评分",**每家一块**(checklist+分)横排。

## 用户已拍板
- **分数可见范围**:所有场景都显示(**撤销 S5 专家侧隐藏**)。
- **风险对比布局**:每投标人一块卡(符合性 checklist + 总分/实得 + 关键单项分)。

## 关键前提（已核实,决定可行性）
- 数据**都在**,S5 只是**展示层隐藏**(文案"分值已隐藏""需结合问题清单复核"),未删数据:
  - `data.scoreSummary: TenderScoreSummary` = `{maxTotal 总分, earnedTotal 实得, deductedTotal 已扣, pendingTotal 待核验, deductedItems[], rejectedItems[], pendingItems[]}`。
  - `data.scoringItems: TenderScoringItem[]` = `{item, max, score, status, basis, deductionHits/awardHits(经 ReviewItem)}`。
  - `resultDetails: AuditResult[]` = **全部投标人**完整结果 → 每家可派生 checklist/scoreSummary/issueList。
  - `reviewBidders[].total/rank` = 服务端真实总分/排名(compare.result.bidders.total_score)。
  - `buildOverviewChecklist`(S10) / `buildScoreSummary` / `buildScoringItems` / `buildIssueList` 均可复用。

## 设计方案

### A. 详细分析（DetailWorkbench）— 左侧区重构
三栏保持:左(改) / 中(评审要点,保留) / 右(证据底稿,保留)。左侧从"风险提示/问题清单/辅助小结"改为**评分总览**:
1. **招标项目卡**:`projectInfo`(name/code/method/controlPrice) + 当前投标人名。
2. **分数卡**(4 数):总分 `maxTotal` · 实际得分 `earnedTotal` · 已扣 `deductedTotal` · 待核验 `pendingTotal`。
3. **类目单项合计**:按 `scoreCategory`(商务/技术) 汇总各类 max/实得(复用 scoring-detail-table 的 group 逻辑)。
4. **扣分清单**:逐条列出所有 `deduction_hits`(哪项 / 扣几分 / 触发原文 quote / 出处页),来源 `scoringItems[].deductionHits`。这是"列出扣分"的落点。
- 中间 `ReviewItemCard` 已逐项显 deductionHits + award,**补显实际得分**(现在只显 max/status)→ 每卡加 `得分 score/max`。

### B. 风险对比（CompareWorkbench）— 每家一块综合卡
- `model.ts` 新增 `buildBidderCards(resultDetails, reviewBidders, compare)`:每投标人 → `{ bidder(名/tag/total/rank), checklist: ChecklistItem[], score: {maxTotal,earnedTotal,deductedTotal,pendingTotal}, topIssues: IssueItem[] }`,接入 `data.bidderCards`。
- `TenderReviewMockData` 加 `bidderCards?: BidderCard[]`;`types.ts` 加 `BidderCard`。
- 新组件 `bidder-compare-cards.tsx`:横排每家一卡:头部(名+排名+总分/实得)→ 符合性 checklist(✓/✗/⏳ 复用 overview 视觉)→ 关键扣分/风险(topIssues)。
- 撤销 CompareWorkbench 的"分值已隐藏/需结合问题清单复核"文案,改为真实分数展示。

### C. 撤销 S5 隐藏（限本 2 视图）
- analysis-workbench-view.tsx:510/571/580 的"分值(与排序)已隐藏""需结合问题清单复核" -> 显真实分。
- **report-view.tsx 暂不动**(用户本次只提详细分析+对比;报告显分另行确认,避免 scope creep)。

## 不可违反 / 护栏
- **概要分析(S10)不动**:它是无分数的符合性视图,保持原样;显分只在详细分析+对比。
- 三态纪律仍守:checklist 的 `confirmed:false`/manual/读不清 -> ⏳ 待核验(复用 buildOverviewChecklist,已含 R2b + 文本层防泄漏)。
- 待核验项 `score:null` 不计入实得合计(scoreSummary 已如此)。
- 后端零改;纯展示层。

## 验收
- 详细分析左侧显:招标项目 + 总分/实得/已扣/待核验 + 类目合计 + 扣分逐条(带出处)。中/右不变。
- 风险对比每家一卡:checklist + 总分/实得 + 关键项。
- model.test.ts 覆盖 `buildBidderCards`(多家派生、总分实得、checklist 传透、空数据兜底)。
- bun test + tsc build + eslint 全绿;后端 pytest 全绿(应零变更)。

## 流程
红区 worktree 隔离 -> TDD(model 层) -> 组件 -> 自测(build/lint/test) -> CC×Codex 多轮交叉 review -> 清 worktree 合 main -> 全量测 -> 用户手检。
