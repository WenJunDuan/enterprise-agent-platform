# Sprint 2 Ship Handoff

## Current State

- Stage: `ship`
- Sprint: `2`
- Gate: PASS
- Commit/PR: pending explicit user instruction

## Verified Commands

- `bash .ai_state/init.sh`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .`
- `UV_CACHE_DIR=/tmp/uv-cache uv build`
- `cd ui && npm run build`
- `git diff --check`

## Safe Commit Scope

Include tracked modifications/deletions and untracked source/state/test/UI files reported by:

```bash
git diff --name-status
git ls-files --others --exclude-standard
```

Do not force-add ignored local artifacts:

- `ui/.env.local`
- `ui/node_modules/`
- `ui/dist/`
- `dist/`

## Suggested Commit Message

```text
feat: add React audit UI and tighten HTTP contract
```

## Notes

- HTTP public surface is `/health`, `/audit/submit`, `/audit/tasks`, `/audit/tasks/{request_id}`, `/audit/tasks/{request_id}/result`.
- CLI keeps query/governance surfaces.
- Upload mode requires at least one `files` attachment.
- Frontend uses `VITE_API_BASE` and `VITE_TENANT_TOKEN` (`VITE_API_KEY` is legacy local alias only).
