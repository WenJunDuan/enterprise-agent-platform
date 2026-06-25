# Fix Note

## Scope

User requested two checks/fixes:

1. All runtime logs under `logs/` should support year/month/day partitioning, not only
   `logs/app`.
2. Tenant data separation needed a serious review.

## Logging Changes

- Added shared helpers in `server/platform/paths.py`:
  - `dated_log_dir(base_dir, timestamp=None)`
  - `dated_log_path(base_dir, filename, timestamp=None)`
  - `latest_dated_log_path(base_dir, filename)`
- Updated `server/platform/logging_setup.py` app/error file handlers to use
  `logs/app/<YYYY>/<MM>/<DD>/{app,error}.log`.
- Updated app-server stdout/stderr paths to use
  `logs/runtime/app-server/<YYYY>/<MM>/<DD>/{stdout,stderr}.log`.
- Kept read compatibility for old `logs/runtime/app-server/<YYYYMMDD>/...` and flat
  `logs/runtime/app-server/stdout.log` / `stderr.log`.

## Tenant Separation Review

HTTP routes checked:

- `audit`, `ocr`, and `tender` business endpoints call `verify_tenant()` first.
- `health` is intentionally public.

Storage checked:

- Request/result/session/task/tender project/tender doc/tender compare stores all have
  tenant-scoped public read/write paths.
- Unscoped read helpers are named `*_admin` and used by CLI/maintenance/admin paths.
- Upload directories are under `data/submissions/<tenant>/<domain>/...`, and directory
  mode validates the requested path stays inside the current tenant subtree.

Improvement made:

- Raw SDK session event files now include tenant in the physical path:
  `data/sessions/events/<tenant>/<YYYY>/<MM>/<DD>/...`.
- Invalid tenant names are mapped to a safe `tenant-<hash>` path segment to prevent
  traversal if `TENANT_KEYS` is misconfigured.

## Verification

```bash
uv run pytest -q tests/test_logging.py tests/test_log_paths.py tests/test_maintenance.py
uv run pytest -q tests/test_maintenance.py tests/test_audit_task_store.py tests/test_tender_p3_backend.py tests/test_tender_compare.py tests/test_session_store_char.py tests/test_log_paths.py tests/test_logging.py
uv run pytest -q tests/test_task_store.py tests/test_api_auth.py tests/test_upload_helpers.py tests/test_ocr_routes.py tests/test_tender_routes.py tests/test_tender_upload_routes.py tests/test_tender_doc_store.py tests/test_log_paths.py tests/test_logging.py
uv run ruff check server/platform/paths.py server/platform/logging_setup.py server/app_server.py server/ops/maintenance.py server/common/session_logging.py tests/test_logging.py tests/test_log_paths.py
```

Results:

```text
15 passed
72 passed, 1 warning
126 passed, 1 warning
All checks passed
```

## Residual Notes

- Managed app-server stdout/stderr are opened by the parent process at start time, so a
  long-running child process keeps writing to its start-day file until restart. The API's
  own `app.log/error.log` handlers switch date directories on emit.
- Existing historical session event files without tenant path remain readable/maintainable
  because maintenance uses recursive globbing.
