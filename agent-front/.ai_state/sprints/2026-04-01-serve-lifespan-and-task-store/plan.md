# Serve Lifespan And Task Store Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace deprecated FastAPI startup hooks with lifespan-based startup recovery, and harden the audit task store against concurrent read-modify-write corruption.

**Architecture:** Move audit-task recovery from `@app.on_event("startup")` to a FastAPI lifespan function so startup behavior remains identical without deprecation warnings. For task storage, keep the existing `tasks.json` external shape for compatibility, but serialize updates through a lock file so concurrent upserts do not lose data.

**Tech Stack:** FastAPI lifespan, Python file locking, local JSON storage, pytest/TestClient, threading

---

### Task 1: Replace Startup Hook With Lifespan

**Files:**
- Modify: `server/api.py`
- Test: `tests/test_bootstrap.py`

- [ ] **Step 1: Write failing tests for lifespan startup recovery**

Add:

```python
def test_api_app_uses_lifespan_startup_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    monkeypatch.setattr(
        api_module,
        "get_app_settings",
        lambda: type("Settings", (), {"audit_task_running_timeout_seconds": 600})(),
    )
    monkeypatch.setattr(
        api_module,
        "recover_stale_audit_tasks",
        lambda timeout: calls.append(timeout) or [],
    )

    with TestClient(api_module.app):
        pass

    assert calls == [600]
    assert api_module.app.router.on_startup == []
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_bootstrap.py -k "lifespan_startup_recovery" -v
```

Expected:
- FAIL because `app.router.on_startup` still contains the startup handler

- [ ] **Step 3: Implement lifespan startup**

In `server/api.py`:

```python
from contextlib import asynccontextmanager
```

Add:

```python
@asynccontextmanager
async def app_lifespan(_: FastAPI):
    settings = get_app_settings()
    recover_stale_audit_tasks(settings.audit_task_running_timeout_seconds)
    yield
```

Replace:

```python
app = FastAPI(title="Enterprise Agent API", version="0.1.0")
```

with:

```python
app = FastAPI(title="Enterprise Agent API", version="0.1.0", lifespan=app_lifespan)
```

Remove:

```python
@app.on_event("startup")
async def recover_audit_tasks_on_startup() -> None:
    ...
```

- [ ] **Step 4: Re-run the focused test**

Run:

```bash
.venv/bin/python -m pytest tests/test_bootstrap.py -k "lifespan_startup_recovery" -v
```

Expected:
- PASS

### Task 2: Add Deterministic Task-Store Concurrency Protection

**Files:**
- Modify: `server/stores/audit_task_store.py`
- Test: `tests/test_bootstrap.py`

- [ ] **Step 1: Write failing concurrency test**

Add:

```python
def test_audit_task_store_concurrent_upserts_preserve_all_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading
    import time as _time
    from server.stores import audit_task_store as audit_task_store_module

    monkeypatch.setattr(audit_task_store_module, "AUDIT_TASK_FILE", tmp_path / "audit-tasks.json")

    original_load = audit_task_store_module._load_task_map

    def slow_load() -> dict[str, Any]:
        data = original_load()
        _time.sleep(0.02)
        return data

    monkeypatch.setattr(audit_task_store_module, "_load_task_map", slow_load)

    def write_task(index: int) -> None:
        audit_task_store_module.upsert_audit_task(
            {
                "request_id": f"req-{index}",
                "tenant": "demo",
                "status": "accepted",
                "mode": "directory",
                "source_mode": "directory",
                "case_path": f"data/case{index}",
                "claim_id": None,
                "result_file": None,
                "error_detail": None,
                "progress_message": "任务已提交",
                "submitted_at": "2026-04-01T00:00:00+00:00",
                "started_at": None,
                "finished_at": None,
                "updated_at": "2026-04-01T00:00:00+00:00",
            }
        )

    threads = [threading.Thread(target=write_task, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    records = audit_task_store_module.list_audit_tasks()
    assert len(records) == 8
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_bootstrap.py -k "concurrent_upserts_preserve_all_records" -v
```

Expected:
- FAIL intermittently or consistently because concurrent writes race on `tasks.json`

- [ ] **Step 3: Add lock-based update helper**

In `server/stores/audit_task_store.py`, add a lock file and wrap read-modify-write:

```python
AUDIT_TASK_LOCK_FILE = AUDIT_TASK_FILE.with_suffix(".lock")
```

Add:

```python
def _update_task_map(mutator: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    AUDIT_TASK_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_TASK_LOCK_FILE.open("a+", encoding="utf-8") as handle:
        _lock(handle)
        try:
            payload = _load_task_map()
            next_payload = mutator(payload)
            append_json_file(AUDIT_TASK_FILE, next_payload)
        finally:
            _unlock(handle)
```

Use local helpers:

```python
def _lock(handle: Any) -> None: ...
def _unlock(handle: Any) -> None: ...
```

Implement with `fcntl.flock` when available.

Then rewrite `upsert_audit_task()`:

```python
def upsert_audit_task(record: dict[str, Any]) -> None:
    def mutate(payload: dict[str, Any]) -> dict[str, Any]:
        existing = payload.get(record["request_id"], {})
        merged = {**existing, **record}
        ...
        payload[task_record.request_id] = asdict(task_record)
        return payload

    _update_task_map(mutate)
```

- [ ] **Step 4: Re-run the focused test**

Run:

```bash
.venv/bin/python -m pytest tests/test_bootstrap.py -k "concurrent_upserts_preserve_all_records" -v
```

Expected:
- PASS

### Task 3: Full Verification

**Files:**
- Verify only

- [ ] **Step 1: Run the full bootstrap suite**

Run:

```bash
.venv/bin/python -m pytest tests/test_bootstrap.py -v
```

Expected:
- all tests PASS

- [ ] **Step 2: Verify the deprecation warning is gone**

Expected:
- `server/api.py` no longer triggers the previous FastAPI `on_event("startup")` deprecation warning during test startup

- [ ] **Step 3: Verify app-server can still start**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run app-server start --port 8001
```

Then:

```bash
curl http://127.0.0.1:8001/ready
```

Expected:
- service starts successfully
- `/ready` returns `status: ok`
