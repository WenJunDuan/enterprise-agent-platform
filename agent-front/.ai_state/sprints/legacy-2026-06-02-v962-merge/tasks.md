# Sprint 2 Tasks — React Frontend

## Checklist

- [x] T1: ui/ scaffold (package.json, vite.config.ts, tsconfig, tailwind, index.html)
- [x] T2: api/client.ts (fetch wrapper with Bearer auth)
- [x] T3: types/index.ts
- [x] T4: components/Layout.tsx + StatusBadge.tsx
- [x] T5: pages/TaskList.tsx
- [x] T6: pages/SubmitExpense.tsx
- [x] T7: pages/TaskDetail.tsx (with 3s polling for running tasks)
- [x] T8: App.tsx + main.tsx (React Router setup)
- [x] T9: server/api.py — add CORSMiddleware
- [x] T10: ui/.env.local + .gitignore

## Acceptance Criteria

- `cd ui && npm install && npm run dev` starts the dev server on :5173
- TaskList loads and displays tasks from GET /audit/tasks
- SubmitExpense POSTs multipart/form-data and redirects to TaskDetail on success
- TaskDetail polls every 3s while status is accepted/running, stops on completed/failed
- Result section renders verdict, risk_score, summary, policy_refs when completed
- All UI text is in Chinese
- UI implementation stays under `ui/`; backend contract regressions are covered by added/updated tests

## Sprint 2 Fix Checklist — Gate Recovery

- [x] S2-FIX-001: Align store capacity test with current SQLite result store
- [x] S2-FIX-002: Add Vite TypeScript env typing and pass frontend build
- [x] S2-FIX-003: Pass backend pytest and ruff checks
- [x] S2-FIX-004: Sync `.ai_state` review/progress with real gate result

## Sprint 2 Review Closure Checklist

- [x] S2-REV-001: Sync design snapshot with actual minimal HTTP surface and frontend list endpoint
- [x] S2-REV-002: Sync frontend integration docs with `VITE_API_BASE` / `VITE_API_KEY` and task-list API
- [x] S2-REV-003: Add `.ai_state/init.sh` so review/impl get-bearings no longer fails
- [x] S2-REV-004: Record final review closure, lessons, and stage transition to ship

# Sprint 3 Tasks — 真实报销填报与列表增强

## Checklist

- [x] S3-T0: Convert `/audit/submit` upload intake to business-agnostic form and attachment archiving
- [x] S3-T1: Expand `SubmitFormData` for realistic reimbursement template payload without backend-required business fields
- [x] S3-T2: Add local submission summary storage keyed by `request_id`
- [x] S3-T3: Rebuild `SubmitExpense` into multi-section reimbursement form with scenario flags and attachment categories
- [x] S3-T4: Enhance `TaskList` with statistics, search, business summary columns, and anomaly tags
- [x] S3-T5: Enhance `TaskDetail` with submitted form summary and attachment summary when available
- [x] S3-T6: Sync `.ai_state`/README/frontend docs with the richer UI contract
- [x] S3-T7: Validate backend and frontend quality gates

## Acceptance Criteria

- Submit form contains realistic invoice reimbursement sections and at least 30 business fields.
- Upload supports optional attachments, attachment categories, file size display, and removal.
- Extra fields are serialized into `form_json`; backend no longer requires `case_id`, `applicant_name`, or `expense_type`.
- Task list remains usable with only backend data, and becomes richer when local summaries are available.
- Task detail shows local submitted payload summary when available without depending on new backend APIs.
- `cd ui && npm run build`, `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`, and `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` pass.

# Sprint 4 Tasks — 前端联调自测收口

## Checklist

- [x] S4-T1: Add backend health/API config indicator for local self-test
- [x] S4-T2: Add submit-page self-test helpers for reset, new case id, and copy payload
- [x] S4-T3: Show full audit result fields including conclusion, explanation, reasons, evidence, and risk dimensions
- [x] S4-T4: Add local summary management and fallback-test controls
- [x] S4-T5: Sync docs/state and validate frontend/backend gates

## Acceptance Criteria

- UI clearly shows whether `/health` is reachable and which API base/tenant-token source is used.
- User can reset the form, generate a new case id, copy the exact `form_json`, and upload arbitrary file types.
- Result detail renders the current audit schema fields, not only `summary` / `verdict`.
- Task list can clear local summaries to test backend-only fallback.
- `cd ui && npm run build`, `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`, and `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` pass.
