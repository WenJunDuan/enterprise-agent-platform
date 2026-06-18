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
- `/contracts` -> contract review entry page

## Auth And Navigation

Default mode uses PIN authorization instead of the target admin username/password
login service. The frontend reads `VITE_TENANT_PIN_KEYS` as a JSON mapping from
PIN to tenant key and persists the resolved tenant key as the local session
credential. A correct PIN should enter the app even when the backend is not
responding; business pages surface data request failures in context.

Legacy account auth routes were removed from the route tree:

- `/sign-in`
- `/sign-up`
- `/forgot-password`

The settings password route was also removed. Static sidebar navigation now
contains three business domain groups:

- `发票审核` -> `发票审核清单`
- `OCR 识别` -> `OCR 识别`
- `合同审查` -> `合同审查清单`

Dashboard navigation is removed. The expense submission entry remains available
inside the audit workbench.

The shared header exposes the existing layout/theme configuration drawer so
users can switch system/default, light, and dark modes.

## Verification

- `bun install --frozen-lockfile` passed.
- `bun run lint` passed.
- `bun run build` passed (`tsc -b && vite build`).
- Production preview smoke passed on `http://127.0.0.1:4173/`:
  - login page title and brand render as `晓数智能云平台`
  - PIN slots render as masked `*` characters
  - configured PIN resolves to the frontend tenant key and enters the app
  - `/sign-in`, `/sign-up`, and `/forgot-password` return 404
  - sidebar links exclude dashboard and direct `新建报销`
- `bun run lint`, `bun run build`, and `bun run test` passed again after the
  2026-06-19 navigation, header, and copy updates.
- Browser smoke checks passed for:
  - `/` rendering the audit workbench without redirecting to login
  - `/audit/submit` rendering the migrated stepped submission form
  - `/ocr` rendering the OCR page and loading the sample fill result

## Notes

Direct browser navigation to some nested local paths was intermittently blocked
by the in-app browser environment, so nested route proof also used generated
`routeTree.gen.ts` and successful full build output. The app route itself is
present and type-checked.
