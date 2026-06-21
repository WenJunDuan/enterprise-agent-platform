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

## Spec Compliance (spec-compliance, 2026-06-20T20:32:16+08:00)

Context: required `git diff main...HEAD --stat`, `--name-only`, and `git log main...HEAD --oneline` are empty because the sprint implementation is already on `main`; sprint file scope was cross-checked from commit `3413216 feat(front): align audit and tender review UI`, current source, checklist, and evidence.

### MISSING

- 未发现。AC1-AC6/AC8/AC9 are present in current source: design requires `智能报销审核`/`报销审核`, `智能招投标审核` with only `项目管理` and `历史评审`, `/contracts` redirect, separated tender/history pages, completed-only history, and local mock/model split (design.md:69, design.md:70, design.md:72, design.md:74, design.md:76, design.md:77); actual navigation/routes/model are in `src/app/navigation/registry.ts:9`, `src/app/navigation/registry.ts:20`, `src/app/navigation/registry.ts:34`, `src/app/navigation/registry.ts:48`, `src/routes/_authenticated/contracts/index.tsx:3`, `src/routes/_authenticated/contracts/tender-review.tsx:3`, `src/routes/_authenticated/contracts/tender-review/index.tsx:4`, `src/routes/_authenticated/contracts/tender-review/history.tsx:4`, `src/features/contract/tender-review/mock-data.ts:3`, and `src/features/contract/tender-review/model.ts:94`.
- 未发现。AC7/AC11/AC12/AC14/AC15 are covered by current UI/evidence: design requires create/analyze flow, browser action acceptance, equal create/history width, history actions limited to `分析中心`/`审核报告`, compact stats/query, OCR split actions (design.md:75, design.md:79, design.md:80, design.md:82, design.md:83); actual flow/actions are in `src/features/contract/tender-review/use-tender-review-page.ts:140`, `src/features/contract/tender-review/components/page-heading.tsx:53`, `src/features/contract/tender-review/components/history-view.tsx:183`, `src/features/contract/tender-review/components/dashboard-view.tsx:78`, `src/features/contract/tender-review/components/dashboard-view.tsx:259`, `src/features/ocr/ocr-workbench-page.tsx:65`, with acceptance evidence in `.ai_state/sprints/2026-06-19-contract-tender-review-mock/evidence.yaml:46`.

### EXTRA

- 合理 refactor: `src/components/layout/nav-group.tsx` was changed even though File Structure Plan only lists navigation registry, audit, contract tender-review, and route files (design.md:85). Actual change indents sidebar child items via `ps-[4ch]` in `src/components/layout/nav-group.tsx:42`, matching the sprint state note but not explicitly listed in design.md.
- 合理 runtime 配套: `vite.config.ts` was changed even though the design says OCR behavior stays unchanged and no new interface work is planned (design.md:37, design.md:42), and File Structure Plan does not list Vite config (design.md:85). Actual proxy bypass for HTML navigations is in `vite.config.ts:87` and applied to `/audit`/`/ocr` in `vite.config.ts:119`; evidence records this as SPA route loading support in `.ai_state/sprints/2026-06-19-contract-tender-review-mock/evidence.yaml:88`.

### DEVIATED

- 未发现。The design allows `dashboard | create | history | analysis | report` while exposing only dashboard/history in sidebar (design.md:50, design.md:51); actual screen type and routing match that in `src/features/contract/tender-review/types.ts:3`, `src/app/navigation/registry.ts:48`, and `src/features/contract/tender-review/components/screen-content.tsx:10`.
- 未发现。Design says `评分对比` stays inside analysis, not as a history row action (design.md:34, design.md:35); actual history rows expose only `分析中心`/`审核报告` in `src/features/contract/tender-review/components/history-view.tsx:183`, while `评分对比` is inside analysis mode controls in `src/features/contract/tender-review/components/analysis-workbench-view.tsx:56`.

### 总评 (PASS | REWORK)

PASS
