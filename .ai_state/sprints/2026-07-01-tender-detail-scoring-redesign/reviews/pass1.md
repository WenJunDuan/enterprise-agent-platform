## Spec Compliance (spec-compliance, 2026-07-01T00:00:00Z)

### MISSING (功能做少了)
- M1: design.md L29 "扣分清单逐条列出所有 deduction_hits (哪项/扣几分/触发原文 quote/出处页), 来源 scoringItems[].deductionHits"。实际 scoring-overview-panel.tsx 使用 scoreSummary.deductedItems (TenderScoreIssue 类型), 该类型只有 item/basis/deduction 字段, 无 quote 无 source page。TenderScoreIssue 定义见 types.ts:175-184。中间栏 ReviewItemCard 的 deductionHits 显示已正确含 quote/source (analysis-workbench-view.tsx:362-370), 但左侧"扣分明细"卡中 触发原文 quote + 出处页 未出现。

### EXTRA (功能做多了)
- E1 [合理]: scoring-overview-panel.tsx 新增独立"待核验项"卡片 (design L28 仅要求分数卡里显 pendingTotal 数字), 属于合理 UI 扩展, 不影响 spec。
- E2 [合理]: BidderCompareCards 把 checklist 中非 met 项逐条列出 (unmet+pending 明细), design 只要求"checklist 三态图标", 属合理强化。
- E3 [合理]: analysis-workbench-view.tsx 同时删除了旧 CompareTable / IssueListPanel / getAdvisorySummary 等已废弃组件, 属于顺手清理。

### DEVIATED (功能做偏了)
无明显偏离。以下条目已核实为符合:

- [符合] AC1 左侧区显招标项目: scoring-overview-panel.tsx:51-65 渲染 projectInfo.name/code/method/controlPrice + bidderName。
- [符合] AC1 总分/实得/已扣/待核验: scoring-overview-panel.tsx:68-84 四格 Stat 卡对应 maxTotal/earnedTotal/deductedTotal/pendingTotal。
- [符合] AC1 类目合计: scoring-overview-panel.tsx:98-114 summarizeByCategory 按 business/technical 汇总 max/earned。
- [符合] AC2 中/右不变: ReviewItemCard 中间栏保留 deductionHits (analysis-workbench-view.tsx:362-380); 证据底稿右栏未动。
- [符合] AC3 ReviewItemCard 补显得分/满分: analysis-workbench-view.tsx:332-341, item.got/item.max 已显示。
- [符合] AC4 风险对比每家一卡: bidder-compare-cards.tsx 实现, checklist + 总分/实得 + 关键风险横排。
- [符合] 撤销隐藏文案: 旧"分值已隐藏/需结合问题清单复核"文案已完全删除。
- [符合] 护栏 S10 不动: 概要分析仍走 OverviewChecklistView 无分数 (analysis-workbench-view.tsx:90-94)。
- [符合] 护栏 report-view 不动: git diff 无 report-view.tsx 变更。
- [符合] 三态纪律: buildBidderCards 复用 buildOverviewChecklist (model.ts:1369), R2b 防判叉逻辑继承。
- [符合] 待核验不计入实得: buildScoreSummary 仅 status===scored && score!=null 计入 earnedTotal (model.ts:1314-1318)。
- [符合] 后端零改: 仅 agent-front/ 下 6 个前端文件。
- [符合] 测试: model.test.ts:1388-1429 覆盖多家派生/总分实得/空数据兜底/buildTenderReviewData 集成。

### Spec Compliance 总评

- MISSING 数: 1
- EXTRA 数: 3 (合理 refactor 3 个 / scope creep 0 个)
- DEVIATED 数: 0
- **建议**: REWORK
  - M1 修法: buildScoreSummary/toScoreIssue 补 quote/source 字段并在 ScoringOverviewPanel 扣分明细行渲染, 或 ScoringOverviewPanel 直接改为消费 scoringItems prop 的 deductionHits 字段。
