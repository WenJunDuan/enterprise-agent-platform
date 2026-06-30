# S6 Scenario Split Notes

## Changed

- Backend `tender_projects` adds `scenario TEXT NOT NULL DEFAULT 'expert_assist'`.
- Existing SQLite tables are migrated with an idempotent `ALTER TABLE ... ADD COLUMN`.
- `POST /tender/projects` accepts `scenario`; project list/detail responses return it.
- `GET /tender/projects?scenario=` filters by `bidder_self_check`, `expert_assist`, or `post_eval_monitor`.
- Frontend API types include `TenderScenario`; `listTenderProjects` sends the scenario query param.
- Frontend adds three scene entries:
  - `expert_assist`: default expert-assist route, reusing S5 `buildIssueList` / `getAdvisoryLabel`.
  - `bidder_self_check`: self-check upload flow, single bidder, report action prints then explicitly confirms project destruction.
  - `post_eval_monitor`: read-only dashboard over completed `expert_assist` projects.
- Navigation visibility is controlled by `VITE_ENABLED_SCENARIOS`; unset defaults to `expert_assist`.
- Architecture note written in `architecture.md`.

## Gates

- `uv run pytest -q` -> 752 passed, 8 warnings.
- `uv run ruff check .` -> pass.
- `cd agent-front && bun test src/features/contract/tender-review/model.test.ts` -> 14 pass, 0 fail.
- `cd agent-front && bun run lint` -> pass.
- `cd agent-front && bun run build` -> pass; Vite emitted existing chunk-size warnings.
- Additional focused checks:
  - `uv run pytest tests/test_tender_scenario.py -q` -> 3 passed.
  - `cd agent-front && bun test src/features/contract/tender-review/api.test.ts src/app/navigation/registry.test.ts` -> 23 pass.

## Tradeoffs

- `scenario` is metadata on the project, not a new scoring or output contract dimension.
- The backend evaluation, OCR, compare, report, and S5 advisory logic remain shared.
- Existing project idempotency is preserved within the same scenario by
  `(tenant, scenario, tender_no)`; the same tender number can exist independently
  across scenarios to avoid self-check cleanup deleting an expert-assist project.
- `uv run pytest -q` initially failed only because the local venv lacked declared OCR extra dependency `pymupdf`; `uv sync --extra ocr` installed the declared extra and the same gate passed.

## Phase-1 Isolation Statement

- Phase 1 scenario isolation is UI-level only: routes, navigation visibility, and list filters.
- Users can bypass frontend routes and call backend APIs directly.
- Real permission isolation, tenant token partitioning, resource authorization, and deployment enforcement are deferred to RBAC/S8.
- Self-check "download then destroy" is a lifecycle cleanup path using project cascade delete; it is not a security boundary.

## User Decisions Pending

- Which deployments should enable `bidder_self_check` and `post_eval_monitor` via `VITE_ENABLED_SCENARIOS`.
- Whether S8 should split scenarios by tenant token, RBAC role, or physically separate deployments.
