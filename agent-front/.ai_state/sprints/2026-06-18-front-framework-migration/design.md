# Front Framework Migration Design

## Goal

Replace `agent-front` with the `quantum-front` UI framework while preserving the
existing enterprise audit and OCR frontend integrations.

## Source And Target

- Current frontend: Vite + React 18 + React Router + Tailwind 3.
- Target framework source: `/Users/mi_manchi/workspace/quantum/quantum-front`.
- Target frontend: Vite + React 19 + TanStack Router/Query + shadcn/Radix + Tailwind 4.

## Preserved Business Surface

- Audit task list backed by `GET /audit/tasks`.
- Audit submission backed by `POST /audit/submit`.
- Audit task detail backed by `GET /audit/tasks/{id}` and `GET /audit/tasks/{id}/result`.
- Retry and delete backed by `POST /audit/tasks/{id}/retry` and `DELETE /audit/tasks/{id}`.
- OCR page backed by `POST /ocr/fill`, with sample data fallback.
- Health probe backed by `GET /health`.
- Tenant-token auth via `VITE_TENANT_TOKEN`, with `VITE_API_KEY` as legacy fallback.
- Local submission summary key `enterprise-audit:submission-summaries:v1`.

## Auth Decision

Keep the audit/OCR API client separate from the target shell's admin login
axios client. The target framework's `apiClient` is tied to `/api` and backend
session auth; the audit service currently expects tenant bearer tokens on
`/audit` and `/ocr`. Merging those two auth models would require backend changes
outside this frontend migration.

## Framework Integration

- Use the target `AuthenticatedLayout`, route tree, providers, theme, sidebar,
  shadcn/Radix components, and TanStack Query patterns.
- Add local file routes for:
  - `/audit`
  - `/audit/submit`
  - `/audit/tasks/$taskId`
  - `/ocr`
- Add static navigation items for audit and OCR so the frontend remains usable
  even when the target admin backend navigation API is unavailable.
- Keep the target admin/system feature code only where it supports the shell.

## Vite And Environment

- Preserve target Tailwind 4 and TanStack Router plugins.
- Add `/audit`, `/ocr`, and `/health` dev proxies using the current frontend
  proxy target semantics:
  - `VITE_API_PROXY_TARGET`
  - `API_PROXY_TARGET`
  - `APP_SERVER_HOST` / `APP_SERVER_PORT`
  - default `http://127.0.0.1:8000`
- Keep `/api` proxy behavior for the imported target shell.

## Verification

- Run package install if needed.
- Run TypeScript/Vite build.
- Start a local dev server and inspect routes with browser automation or an
  equivalent rendered smoke check.
- Do not mark complete unless audit/OCR routes are present and build succeeds.
