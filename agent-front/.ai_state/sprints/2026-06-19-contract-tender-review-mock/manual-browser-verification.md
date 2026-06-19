---
sprint_slug: "2026-06-19-contract-tender-review-mock"
created: "2026-06-19"
status: "passed_in_edge"
---

# Manual Browser Verification

Dev server:

- `http://127.0.0.1:5174/contracts`
- `http://127.0.0.1:5174/contracts/tender-review`
- `http://127.0.0.1:5174/contracts/tender-review/history`

Automated test/lint/build passed and both routes return HTTP 200. Edge visual
verification was completed with Computer Use and Playwright-driven Edge checks
earlier in the sprint. The latest UI refinement pass was verified with source
scans plus lint/test/build and did not save screenshots.

## Checks

1. [x] Open `/contracts/tender-review` and confirm page title is `项目管理`.
2. [x] Confirm sidebar group is `智能招投标审核` and contains `项目管理` plus `历史评审`.
3. [x] Confirm sidebar group is `智能报销审核` and it only contains `报销审核`.
4. [x] Confirm breadcrumb is `智能招投标审核 / 项目管理`.
5. [x] Confirm `/contracts/tender-review` shows the dashboard content and no removed upload/engine/date-count block.
6. [x] Confirm no `合同审查清单` page appears from the menu.
7. [x] Open `/contracts`; route returns HTTP 200 and index route redirects to `项目管理`.
8. [x] Open `/contracts/tender-review/history`; confirm it shows the history heading, prototype description, filters, table, and no `创建评审` button.
9. [x] Click `创建评审` from `/contracts/tender-review`; confirm it opens the mock create screen.
10. [x] Click `开始分析`; confirm the mock progress completes and enters `分析中心`.
11. [x] Click `评分对比`; confirm the comparison table opens.
12. [x] Click `生成报告`; confirm the report preview opens.
13. [x] Click `返回对比`; confirm it returns to the comparison view.
14. [x] Confirm `创建评审` and `历史评审` use the same main container width (`1176px` in the 1440px desktop viewport).
15. [x] Confirm create-page add/remove tender file, add/remove bidder, and add/remove bidder file controls work.
16. [x] Confirm history search, status filter, and time filter controls work.
17. [x] Confirm history row actions only expose `分析中心` / `审核报告`; `评分对比` remains available only inside the analysis screen.
18. [ ] Mobile-width visual check not executed in this run.

## Latest UI Refinement Checks

1. [x] Sidebar group `OCR 识别` renamed to `智能 OCR`, while the child entry remains `OCR 识别`.
2. [x] Source scan found no native `<select>` markup in `src`.
3. [x] `项目管理` uses shared `DataTableToolbar` / `DataTablePagination`; project search width is widened and stats cards are shorter.
4. [x] `报销审核` source scope has no `刷新` or `清空摘要` actions.
5. [x] `OCR 识别` places `开始识别` and `加载示例` on opposite sides of the upload action row.
6. [x] `创建评审` centers/widens the stepper and file actions now consume selected files instead of appending generated mock filenames.

## Runtime Fix

Latest Edge verification found the history route was nested under a parent
route that rendered the dashboard without an `Outlet`. The parent was changed
to an `Outlet`, the dashboard moved to an index route, and history now renders
as a distinct route.

Follow-up Edge/Playwright verification found a `CardDescription is not defined`
runtime 500 after the mock implementation copy was removed from the project
info card. The import was restored because the upload card still uses
`CardDescription`; `创建评审` now opens cleanly and no longer displays the mock
implementation copy.
