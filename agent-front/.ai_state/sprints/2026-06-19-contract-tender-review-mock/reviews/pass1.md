# Review Pass 1 — Sprint 2026-06-19-contract-tender-review-mock

> Superseded: this review targeted the earlier six-view implementation. The
> current user-corrected scope is documented in `../design.md`.

## Findings (按严重度排序)

### F1 [SEVERITY=P0] 招投标审核页面单文件和组件函数超过 SRP 硬性限制
- File: agent-front/src/features/contract/tender-review/index.tsx:96
- 问题: `TenderReviewPage` 所在文件共 709 行，并在同一文件内承载页面状态、工作台、新建审核、分析中心、评分对比、报告、历史评审等多个 UI 模块；`TenderReviewPage`、`Dashboard`、`DetailView`、`HistoryView` 等函数体也明显超过 40 行。当前实现能通过构建和浏览器验收，但违反 Athena coding standards 的 P0 SRP 硬性要求，后续替换真实数据/model 层时维护成本会快速上升。
- 建议: 将 `index.tsx` 拆成薄页面容器和按视图划分的组件文件，例如 `dashboard-view.tsx`、`new-task-view.tsx`、`analysis-center.tsx`、`compare-view.tsx`、`report-view.tsx`、`history-view.tsx`；页面容器仅保留状态编排和 model 调用。
- 引用: ~/.codex/standards/coding-standards.md L20-L23

### F2 [SEVERITY=P1] Dashboard summary 对空投标方数据缺少边界处理
- File: agent-front/src/features/contract/tender-review/model.ts:53
- 问题: `buildDashboardSummary` 直接用 `totalScore / data.bidders.length` 计算平均分。当前 mock 数据非空所以页面正常，但当后续真实接口替换或 mock fixture 变为空数组时会返回 `NaN`，工作台指标会显示异常；现有测试只覆盖正常数据，没有覆盖该边界。
- 建议: 在 `data.bidders.length === 0` 时返回 `averageScore: 0`、`topBidderName: '暂无'`，并补一条空投标方/空任务的模型测试。
- 引用: ~/.codex/standards/coding-standards.md L45

## Notes

- 未发现密钥、真实接口调用、`innerHTML`/XSS、shell/SQL 拼接、日志泄露或真实文件上传处理。
- `/contracts` index route 保留原 `ContractReviewPage`，`/contracts/tender-review` 独立接入，未看到 `/audit/*` 或 `/ocr` 业务源文件变更。
- `.gitignore` 的 `data/` 例外用于纳入既有 data 模块；新增的 `business-type.ts`、`system/user/data/*` 未包含敏感数据。
