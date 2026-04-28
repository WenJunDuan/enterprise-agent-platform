# Sprint 4 Review — 前端联调自测收口

**Reviewer:** Codex mainline self-review  
**Date:** 2026-04-27  
**Path:** Quick  
**Scope:** React frontend integration readiness + docs/state sync

## Verdict

PASS（local gate）

## Review Findings

| Area | Finding | Result |
|---|---|---|
| API config | `ui/src/api/client.ts` exposes API runtime config, reads tenant token from `VITE_TENANT_TOKEN` with legacy `VITE_API_KEY` alias, and adds `/health` client | PASS |
| Connection UI | `ConnectionStatus` renders backend reachability, API base, tenant-token source, and manual retry in the global layout | PASS |
| Submit self-test | `SubmitExpense` adds new case id, reset sample, copy `form_json`, success notices, and unrestricted file chooser | PASS |
| Result detail | `TaskDetail` renders `result/conclusion/explanation/reasons/risk_dimensions/evidence_chain/extracted_data` in addition to legacy fields | PASS |
| List fallback | `TaskList` can clear local submission summaries to verify backend-only fallback display | PASS |
| Docs/state | README, frontend integration doc, design, tasks, progress, session, and lessons are synced | PASS |

## Validation

- `cd ui && npm run build` → passed
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q` → 97 passed
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` → All checks passed
- `git diff --check` → passed

## Known Limits

- No browser automation was added; final UI behavior should still be manually verified in the browser against a real running backend.
- The connection strip only checks `/health`; it does not prove Claude runtime credentials are sufficient for a completed audit.
- Tenant token remains an API caller credential: local React UI reads it from env, while external systems pass `Authorization: Bearer <tenant-token>` directly.
