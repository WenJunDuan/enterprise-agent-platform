---
version: "9.6.4-front"
scope: "agent-front"
path: "System"
stage: "ship"
current_sprint_slug: "2026-06-19-contract-tender-review-mock"
current_roadmap_slug: ""
source_ai_state: "../.ai_state"
created_at: "2026-06-18"
next_action: ""
---

# Agent Front State Index

This `.ai_state` tracks the migrated `agent-front` frontend. It was created by
migrating frontend-relevant state from the parent
`enterprise-agent-platform/.ai_state`.

## Latest Update: 2026-06-25

Active sprint remains `2026-06-19-contract-tender-review-mock`. The frontend
shell now includes local system-management data and user-controlled sidebar menu
visibility, while tender-review score display issues from live testing were
repaired.

- Tender score summary now exposes deducted / unearned points and pending
  unscored points with the affected scoring item names, so report and analysis
  views show both "how many points" and "which items".
- Tender bidder score attribution was fixed for simultaneous reviews: each
  bidder tab resolves its own score/result by request/task/claim identity
  instead of leaking the first bidder score into another tab.
- Tender ranking now sorts by descending comprehensive score, preserving stable
  tie behavior.
- Header settings were moved into the avatar menu. The left sidebar footer user
  row now uses the same avatar dropdown, so the whole user row opens theme,
  layout, personal profile, system-management entries, and logout.
- System-management entries under the avatar menu are backed by local route
  definitions instead of `/system/menu/getRouters`.
- `菜单管理` now has a front-end sidebar visibility panel. It can hide/show a
  whole business menu group and individual menu items, persisted in browser
  localStorage.
- `用户管理` / `角色管理` / `菜单管理` / `部门管理` / `字典管理` / `文件管理`
  now use local JSON/local no-op data paths. They no longer call missing
  `/system/*` backend APIs.
- Verification for this state: `bun run lint`, `bun run test` (43 pass),
  `bun run build`, HTTP checks for `/system/menu`, `/system/user`,
  `/system/role`, `/system/dept`, `/system/dict`, and `/system/file`, and
  `git diff --check -- agent-front` passed. Build still emits only the known
  large-chunk warning.

## Previous Update: 2026-06-24

Active sprint remains `2026-06-19-contract-tender-review-mock`, but the tender
review frontend has moved past the original mock route shape and now reflects
the backend-connected review flow.

- Commit `6b84ca3 fix(front): polish tender report flow` was pushed to
  `origin/main`.
- Current tender routes:
  - `/contracts` redirects to `/contracts/tender/list`.
  - `/contracts/tender/list` is the sidebar entry `智能招投标审核 > 评审列表`.
  - `/contracts/tender/detail?view=analysis` is the detail analysis center.
  - `/contracts/tender/detail?view=report` opens the report view directly.
  - `/contracts/tender/history` remains `历史评审`.
- The old `/contracts/tender-review` route shape was removed. Do not preserve it
  in future route work unless a compatibility requirement is explicitly added.
- Report entry behavior was repaired: `查看报告` from both detail analysis and
  history opens the report screen instead of being hijacked by an in-progress
  analysis state, and report navigation carries `view=report`.
- Tender analysis polish now includes equal-height compact scoring rows and
  evidence navigation that scrolls the right evidence panel into view when a
  center item is selected.
- Tender display conventions are enterprise-name first. Credit-code-like claim
  identifiers must not be used as visible bidder names when an enterprise name
  is available.
- Frontend cleanup removed unused components/assets/forms and unused
  dependencies: `date-fns` and `react-day-picker`. `knip` now reports no unused
  files or dependencies; remaining findings are unused exports/types and are
  intentionally kept as API/model surfaces unless a later cleanup proves they
  are safe to remove.
- Verification for this state: `bun run lint`, `bun run test` (39 pass),
  `bun run build`, and `git diff --check -- agent-front` passed. Build still
  emits only the known large-chunk warning.

## Previous Update: 2026-06-19

Active sprint: `2026-06-19-contract-tender-review-mock`.

- User refined the tender domain: the sidebar exposes `项目管理` and `历史评审`
  under `智能招投标审核`. Prototype detail screens may exist only as
  button-driven internal mock flows.
- Navigation is now:
  - `智能报销审核` group with `报销审核`.
  - `智能 OCR` group with `OCR 识别`.
  - `智能招投标审核` group with `项目管理` and `历史评审`.
- Sidebar child menu items are indented by `4ch` under each group label.
- Old `合同审查清单` menu/page is removed. `/contracts` is retained only as a
  compatibility redirect to `/contracts/tender-review`.
- `TenderReviewScreen` is now `dashboard | create | history | analysis |
  report`. `create` is opened by the `创建评审` button and remains mock-only;
  `analysis` covers `分析中心` and `评分对比`; `report` covers `审核报告`. These
  internal screens are not sidebar entries.
- Mock data remains local in `features/contract/tender-review/mock-data.ts`;
  dashboard/history derivation is isolated in `model.ts` for later API
  replacement.
- `项目管理` and `报销审核` now use the shared `DataTableToolbar` /
  `DataTablePagination` design language for query, status, and pagination.
  The reimbursement page no longer renders the refresh / clear-summary action
  block. Tender UI no longer renders the English `AI` label.
- 2026-06-19 UI refinement pass: remaining native `<select>` controls were
  replaced with shared Select components; source scan shows no native select
  markup. `历史评审` table headers are centered and row actions now expose only
  `分析中心` and `审核报告`. OCR upload actions place `开始识别` and `加载示例`
  on opposite sides. `项目管理` stats are shorter and the project query input is
  widened. `创建评审` stepper is centered/wider, and tender/bidder file actions
  now select real files (PDF, images, Office/text document formats) instead of
  appending generated mock filenames.
- Follow-up history refinement: `历史评审` no longer renders status filter chips
  for `已完成` / `已归档`; history records are normalized to `已完成` only.
- Vite proxy now bypasses HTML navigations for `/audit*` and `/ocr*`, so SPA
  routes can load directly while API requests still proxy to the audit service.
- Verification on 2026-06-19: `bun run lint`, `bun run test` (24 pass), and
  `bun run build` passed. Dev server is running at
  `http://127.0.0.1:5174/`; Edge/Playwright text/DOM verification confirmed
  `/contracts/tender-review`, `创建评审`, and `/audit` query/status/pagination
  behavior without saving screenshots.

## Earlier Update: 2026-06-19

The migrated frontend is now the active app shell on `main`.

- Product name is `晓数智能云平台`.
- Login uses configured PIN -> tenant key mapping from `VITE_TENANT_PIN_KEYS`;
  a correct PIN enters the app without waiting for backend task validation.
- Environment files are normalized to `.env.dev` and `.env.prod`; `.env.local`
  is intentionally removed.
- Old account/password, register, forgot-password, dashboard, and password
  settings routes were removed from the frontend route tree.
- Sidebar is static and business-oriented:
  - group `发票审核` with entry `发票审核清单`
  - group `OCR 识别` with entry `OCR 识别`
  - group `合同审查` with entry `合同审查清单`
- The header shows the existing layout/theme configuration drawer so users can
  switch system/default, light, and dark modes.
- User-facing frontend messages were simplified to avoid backend/proxy/HTTP
  implementation wording.
- Verification passed on 2026-06-19: `bun run lint`, `bun run build`, and
  `bun run test`.

## Current Scope

The framework migration is complete enough that `agent-front` is the active
frontend shell on `main`.

- current stack: Vite 8 + React 19 + TanStack Router/Query + shadcn/Radix +
  Tailwind 4
- required preservation: `/audit/*`, `/ocr/*`, `/health`, tenant token handling,
  local submission summaries, existing audit/OCR view behavior
- current tender surface: backend-connected `智能招投标审核` routes under
  `/contracts/tender/*`
- current maintenance rule: keep future tender route changes aligned with
  `/contracts/tender/list`, `/contracts/tender/detail`, and
  `/contracts/tender/history`; do not resurrect the old
  `/contracts/tender-review` route family.

## Migrated Material

### Primary Frontend References

- `docs/前端审核服务对接文档.md`
  - audit async flow: `POST /audit/submit` -> poll `GET /audit/tasks/{id}` -> `GET /audit/tasks/{id}/result`
  - OCR flow: `POST /ocr/extract`, `POST /ocr/fill`
  - auth, upload, CORS, health, and error shape notes
- `sprints/legacy-2026-06-02-v962-merge/handoff-ui-rewrite.md`
  - old UI rewrite plan and service connection checklist
  - important compatibility constraints for `client.ts`, `SubmitFormData`, and `enterprise-audit:submission-summaries:v1`

### API And Display Contract History

- `sprints/2026-03-31-async-audit-submit-serve/`
  - async audit submit and task polling model used by the frontend
- `sprints/2026-03-31-audit-result-and-directory-input/`
  - structured result fields required for UI display
- `sprints/2026-03-31-audit-result-chinese-display/`
  - `result`, `conclusion`, `explanation`, and Chinese display contract
- `sprints/2026-03-31-audit-serve-hardening/`
  - frontend-facing service hardening and response behavior
- `sprints/2026-04-01-serve-lifespan-and-task-store/`
  - task lifecycle and store behavior behind frontend polling

### OCR Frontend Integration

- `sprints/2026-06-17-ocr-http-api/`
  - `/ocr/extract` and `/ocr/fill`
  - OCR frontend page scope and verification history
  - OCR follow-ups and production validation notes

### Packaging And Operational Notes

- `sprints/2026-06-09-audit-agent-docker-repack/ship.md`
  - deployment/package history; relevant because frontend build artifacts must not be stale when repacking
- `compound/2026-06-17-learning-classify-fix-exposes-latent-bug.md`
  - OCR routing lesson relevant to OCR page expectations
- `compound/2026-06-17-learning-cross-review-and-soft-timeout.md`
  - OCR timeout/review lesson relevant to frontend timeout and retry design

## Frontend Migration Notes

- Treat the target `quantum-front` as the new app shell and design language.
- Port existing audit/OCR business capability into the target shell, not the old `Layout`.
- Authentication is intentionally frontend-configured for now:
  - target shell admin username/password auth is not used
  - OTP/PIN login resolves a tenant key from `VITE_TENANT_PIN_KEYS`
  - the resolved tenant key is persisted as the local session credential
- Keep current backend endpoint contracts stable unless backend changes are explicitly requested.
- Run build verification after implementation and inspect UI render behavior in browser.


## 历史
- `2026-06-25 15:20:19`: stage=ship sprint=2026-06-19-contract-tender-review-mock turn-end
