---
version: "9.6.4-front"
scope: "agent-front"
path: "System"
stage: "plan"
current_sprint_slug: "2026-06-18-front-framework-migration"
current_roadmap_slug: ""
source_ai_state: "../.ai_state"
created_at: "2026-06-18"
next_action: "design_front_framework_migration"
---

# Agent Front State Index

This `.ai_state` was created for `agent-front` by migrating frontend-relevant
state from the parent `enterprise-agent-platform/.ai_state`.

## Current Scope

The active frontend task is a full UI framework migration:

- current app: Vite + React 18 + React Router + Tailwind 3
- target framework source: `/Users/mi_manchi/workspace/quantum/quantum-front`
- target stack: Vite + React 19 + TanStack Router/Query + shadcn/Radix + Tailwind 4
- required preservation: `/audit/*`, `/ocr/*`, `/health`, tenant token handling, local submission summaries, existing audit/OCR view behavior

This is a System-level frontend migration. Do not delete or replace the current
frontend implementation until the migration design is written and confirmed.

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
- Decide explicitly how authentication is handled:
  - target shell has login/session and axios interceptors
  - current audit UI uses `VITE_TENANT_TOKEN` and direct `/audit`/`/ocr` calls
- Keep current backend endpoint contracts stable unless backend changes are explicitly requested.
- Run build verification after implementation and inspect UI render behavior in browser.
