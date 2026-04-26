# Sprint 1 Code Review

**Reviewer:** CC self-review (internal)
**Date:** 2026-04-24
**Path:** Refactor
**Files changed:** api.py, cli.py, stores/audit_task_store.py, stores/result_store.py, pyproject.toml

---

## Changes Reviewed

### 1. `pyproject.toml` — Missing dependency declarations
- Added `jsonschema>=4.23.0` (imported at module level in `asset_validation.py`)
- Added `python-multipart>=0.0.9` (root cause of multipart upload failures)
- Added `httpx>=0.27.0` (dev dep, required for FastAPI TestClient)
- Added `pytest-asyncio>=0.24.0` (dev dep, required for async test support)
- **Assessment:** Correct. All four were real missing deps causing runtime/test failures.

### 2. `server/api.py` — Security and completeness fixes

#### S1: `_sanitize_upload_name` — Empty filename guard
- Now raises HTTP 400 instead of returning `"upload-N"` with no extension
- **Assessment:** Correct. The old fallback caused misleading "Unsupported file type" errors.

#### S2: `_materialize_upload_submission` — Empty files guard
- Raises HTTP 400 when `files` list is empty
- **Assessment:** Correct. Prevents silent audit submissions with no attachments.

#### S3: `verify_tenant` — Default tenant key enforcement
- Blocks auth with 503 when `TENANT_KEYS` is not configured unless `ALLOW_INSECURE_DEFAULT_TENANT_KEY=true`
- **Concern (minor):** 503 is semantically "service unavailable". An argument exists for 500 (misconfiguration), but 503 is acceptable and signals to callers that it's a transient/config issue rather than their credentials being wrong. Consistent with the advisory approach.
- **Assessment:** Correct. Prevents accidental public exposure of the API with the hardcoded default key.

#### S4: `_public_runtime_status` — Internal path leakage
- Filters `app_server` to only `{ok, running}`, suppresses absolute paths
- **Assessment:** Correct. `/health` should not expose server filesystem layout.

#### U1: `GET /audit/tasks` — List endpoint
- Accepts `Authorization`, `status`, `limit` (1-100), `offset` (≥0)
- Delegates to `list_audit_tasks(tenant, ...)` in store
- Returns `list[AuditTaskStatusResponse]`
- Route is registered before `GET /audit/tasks/{request_id}` to avoid shadowing
- **Assessment:** Correct. Query param bounds (`ge=1, le=100`) prevent abuse.

### 3. `server/cli.py` — Maintenance command + init-rules fix

#### U4: `maintenance` command
- Added `@app.command()` that calls `run_maintenance()` and echoes JSON
- **Assessment:** Correct. The function was fully implemented but unreachable.

#### U5: `init_rules` — PDF proxy path
- Was: `canonical_source, _ = prepare_text_proxy(source, ...)` → passed original path to Claude
- Now: `canonical_source, proxy_path = ...` → passes `proxy_path if proxy_path else canonical_source`
- **Assessment:** Correct. For non-PDF sources `proxy_path` is `None`, so fallback to original is safe.

### 4. `server/stores/audit_task_store.py` — List function completeness

#### U1 (store side): `list_audit_tasks`
- Added `status` filter, reverse-chronological sort by `submitted_at`, `offset`/`limit` pagination
- **Assessment:** Correct. Sort key uses `submitted_at or updated_at or ""` which handles missing fields gracefully.

### 5. `server/stores/result_store.py` — Dead code removal + Protocol fix

#### U2: `JSONLResultStore` removal
- Removed 124 lines of JSONL-backed implementation never instantiated after SQLiteResultStore was added
- Removed unused imports: `append_jsonl_record`, `warn_if_store_capacity_exceeded`
- Removed `_month_key` helper only used by the removed class
- `load_jsonl_records_from_paths` retained — still used by `SQLiteResultStore._backfill_legacy_records`
- **Assessment:** Correct. `RESULT_STORE` is always `SQLiteResultStore`. No callers of `JSONLResultStore` anywhere.

#### U3: `ResultStore` Protocol admin methods
- Added `list_records_admin`, `get_record_by_request_id_admin`, `get_payload_by_request_id_admin` to Protocol
- These were called via `RESULT_STORE.*_admin(...)` but missing from the Protocol, causing type-checking gaps
- **Assessment:** Correct. `SQLiteResultStore` already implements all three, so no runtime breakage.

---

## Risk Assessment

| Change | Risk | Notes |
|--------|------|-------|
| verify_tenant 503 on default keys | Medium | Breaks existing dev setups without `ALLOW_INSECURE_DEFAULT_TENANT_KEY=true`. Documented behavior change. |
| JSONLResultStore removal | Low | Dead code confirmed by grep; `RESULT_STORE` always SQLite |
| GET /audit/tasks | Low | Read-only endpoint, tenant-isolated |
| init_rules proxy path | Low | Non-PDF sources unaffected (proxy_path=None → fallback) |
| pyproject.toml deps | Low | Additive only |

## Issues Found

None blocking. One item to document:

- **Dev setup change (S3):** Developers using the default key (`sk-default`) must now set `ALLOW_INSECURE_DEFAULT_TENANT_KEY=true` in their `.env`. Should be noted in README or `.env.example`.

## Verdict

**PASS** — All changes are correct, scoped, and the security improvements are net positives. The dev-key breaking change is acceptable and intentional.
