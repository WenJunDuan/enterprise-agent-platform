# Front Framework Migration Ship Record

## Result

`agent-front` has been migrated onto the `quantum-front` framework baseline:

- Vite + React 19 + TanStack Router/Query
- shadcn/Radix component system
- Tailwind 4 via `@tailwindcss/vite`
- target shell providers, layout, sidebar, theme, and generated route tree

## Preserved Business Integrations

- Audit API client still calls `/audit/*` with `VITE_TENANT_TOKEN` and `VITE_API_KEY` fallback.
- OCR API client still calls `/ocr/fill` and keeps `/ocr/extract` available.
- `GET /health` remains unauthenticated.
- Local submission summary storage key remains `enterprise-audit:submission-summaries:v1`.

## New Routes

- `/` -> audit task list
- `/audit` -> audit task list
- `/audit/submit` -> new expense submission
- `/audit/tasks/$taskId` -> audit task detail
- `/ocr` -> OCR recognition and form-fill workbench

## Auth And Navigation

Default mode uses PIN authorization instead of the target admin username/password
login service. The frontend reads `VITE_TENANT_PIN_KEYS` as a JSON mapping from
PIN to tenant key, validates the resolved tenant key against the audit API, and
persists it as the local session credential. The legacy direct
`VITE_TENANT_TOKEN` / `VITE_API_KEY` fallback is still supported by the audit API
client.

Legacy account auth routes were removed from the route tree:

- `/sign-in`
- `/sign-up`
- `/forgot-password`

The settings password route was also removed. Static sidebar navigation now only
contains dashboard, audit workbench, and OCR entries; the expense submission
entry remains available inside the audit workbench.

## Verification

- `bun install --frozen-lockfile` passed.
- `bun run lint` passed.
- `bun run build` passed (`tsc -b && vite build`).
- Production preview smoke passed on `http://127.0.0.1:4173/`:
  - login page title and brand render as `晓数智能云平台`
  - PIN slots render as masked `*` characters
  - configured PIN resolves to the frontend tenant key and enters the app
  - `/sign-in`, `/sign-up`, and `/forgot-password` return 404
  - sidebar links exclude `新建报销`
- Browser smoke checks passed for:
  - `/` rendering the audit workbench without redirecting to login
  - `/audit/submit` rendering the migrated stepped submission form
  - `/ocr` rendering the OCR page and loading the sample fill result

## Notes

Direct browser navigation to some nested local paths was intermittently blocked
by the in-app browser environment, so nested route proof also used generated
`routeTree.gen.ts` and successful full build output. The app route itself is
present and type-checked.
