# Audit Serve Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the async audit serve flow with task recovery, upload validation, richer task status, a frontend-friendly result endpoint, real HTTP integration tests, and submission cleanup.

**Architecture:** Build on the existing `/audit/submit` async flow and local JSON storage. Expand task records so they carry timeline and progress fields, recover stale `running` tasks on service startup, validate upload inputs at the API boundary, expose a lightweight `/audit/tasks/{request_id}/result` endpoint, add HTTP integration coverage for directory and upload flows, and clean up old submission directories without touching archived results.

**Tech Stack:** FastAPI, Pydantic, local JSON storage, pytest/TestClient, asyncio background tasks, maintenance helpers

---

### Task 1: Expand Audit Task State And Recovery

**Files:**
- Modify: `server/stores/audit_task_store.py`
- Modify: `server/platform/config.py`
- Modify: `server/api.py`
- Test: `tests/test_bootstrap.py`

- [ ] **Step 1: Write failing tests for enriched audit task records**

Add tests that expect new fields on stored records:

```python
def test_audit_task_store_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from server.stores import audit_task_store as audit_task_store_module

    monkeypatch.setattr(audit_task_store_module, "AUDIT_TASK_FILE", tmp_path / "audit-tasks.json")

    audit_task_store_module.upsert_audit_task(
        {
            "request_id": "req-1",
            "status": "accepted",
            "mode": "directory",
            "source_mode": "directory",
            "case_path": "data/case1",
            "claim_id": None,
            "result_file": None,
            "error_detail": None,
            "progress_message": "任务已提交",
            "submitted_at": "2026-03-31T00:00:00+00:00",
            "started_at": None,
            "finished_at": None,
            "updated_at": "2026-03-31T00:00:00+00:00",
        }
    )

    record = audit_task_store_module.get_audit_task("req-1")
    assert record is not None
    assert record["source_mode"] == "directory"
    assert record["progress_message"] == "任务已提交"
    assert record["submitted_at"] == "2026-03-31T00:00:00+00:00"
```

- [ ] **Step 2: Add failing tests for stale running-task recovery**

```python
def test_recover_stale_audit_tasks_marks_old_running_tasks_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from server.stores import audit_task_store as audit_task_store_module

    monkeypatch.setattr(audit_task_store_module, "AUDIT_TASK_FILE", tmp_path / "audit-tasks.json")
    audit_task_store_module.upsert_audit_task(
        {
            "request_id": "req-stale-1",
            "status": "running",
            "mode": "directory",
            "source_mode": "directory",
            "case_path": "data/case1",
            "claim_id": None,
            "result_file": None,
            "error_detail": None,
            "progress_message": "正在调用 Claude 审核",
            "submitted_at": "2026-03-31T00:00:00+00:00",
            "started_at": "2026-03-31T00:00:10+00:00",
            "finished_at": None,
            "updated_at": "2026-03-31T00:00:10+00:00",
        }
    )

    recovered = audit_task_store_module.recover_stale_audit_tasks(
        timeout_seconds=60,
        now="2026-03-31T00:05:00+00:00",
    )

    assert recovered == ["req-stale-1"]
    record = audit_task_store_module.get_audit_task("req-stale-1")
    assert record["status"] == "failed"
    assert "超时" in record["error_detail"]
```

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "audit_task_store_round_trip or recover_stale_audit_tasks" -v
```

Expected:
- FAIL because the store does not yet support `source_mode`, timeline fields, or stale recovery

- [ ] **Step 4: Implement richer task records and stale recovery**

Update `server/stores/audit_task_store.py`:

```python
@dataclass(slots=True)
class AuditTaskRecord:
    request_id: str
    status: str
    mode: str
    source_mode: str
    case_path: str
    claim_id: str | None = None
    result_file: str | None = None
    error_detail: str | None = None
    progress_message: str | None = None
    submitted_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str = ""
```

Make `upsert_audit_task()` merge with the existing record:

```python
existing = payload.get(request_id, {})
merged = {**existing, **record}
task_record = AuditTaskRecord(**merged)
```

Add:

```python
def list_audit_tasks() -> list[dict[str, Any]]: ...
def recover_stale_audit_tasks(timeout_seconds: int, now: str | None = None) -> list[str]: ...
```

Recovery rule:
- only touch tasks with `status == "running"`
- compare `started_at` or fallback `updated_at`
- mark stale tasks as:
  - `status = "failed"`
  - `error_detail = "任务在服务重启或超时后被标记为失败"`
  - `progress_message = "任务超时或服务重启后自动终止"`
  - `finished_at = now`
  - `updated_at = now`

- [ ] **Step 5: Add timeout setting**

Update `server/platform/config.py`:

```python
@dataclass(frozen=True, slots=True)
class AppSettings:
    ...
    audit_task_running_timeout_seconds: int
    submission_retention_days: int
```

And load:

```python
        audit_task_running_timeout_seconds=_env_int("AUDIT_TASK_RUNNING_TIMEOUT_SECONDS", 600),
        submission_retention_days=_env_int("SUBMISSION_RETENTION_DAYS", 7),
```

- [ ] **Step 6: Recover stale tasks on API startup**

In `server/api.py`, add a startup hook:

```python
@app.on_event("startup")
async def recover_audit_tasks_on_startup() -> None:
    settings = get_app_settings()
    recover_stale_audit_tasks(settings.audit_task_running_timeout_seconds)
```

- [ ] **Step 7: Re-run the focused tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "audit_task_store_round_trip or recover_stale_audit_tasks" -v
```

Expected:
- PASS

### Task 2: Add Upload Validation

**Files:**
- Modify: `server/api.py`
- Modify: `tests/test_bootstrap.py`
- Modify: `.env.example`

- [ ] **Step 1: Write failing tests for upload validation**

Add tests for:

```python
def test_audit_submit_upload_rejects_invalid_form_json(...) -> None: ...
def test_audit_submit_upload_rejects_missing_required_form_fields(...) -> None: ...
def test_audit_submit_upload_rejects_empty_file(...) -> None: ...
def test_audit_submit_upload_rejects_disallowed_extension(...) -> None: ...
```

Required `form_json` fields for this round:
- `case_id`
- `applicant_name`
- `expense_type`

Expected status:
- `400` for invalid JSON or missing form fields
- `400` for empty file
- `400` for unsupported file type

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "rejects_invalid_form_json or rejects_missing_required_form_fields or rejects_empty_file or rejects_disallowed_extension" -v
```

Expected:
- FAIL because validation is not implemented yet

- [ ] **Step 3: Implement upload validation**

In `server/api.py`, add:

```python
REQUIRED_FORM_FIELDS = {"case_id", "applicant_name", "expense_type"}
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
```

Helpers:

```python
def _validate_form_payload(payload: dict[str, Any]) -> None: ...
def _validate_upload_bytes(name: str, content: bytes) -> None: ...
```

Validation rules:
- `form_json` must decode to a dict
- required keys must be present and non-empty
- file content must be non-empty
- suffix must be in `ALLOWED_UPLOAD_EXTENSIONS`
- file size must be `<= get_app_settings().max_upload_file_bytes`

Add setting:

```python
max_upload_file_bytes=_env_int("MAX_UPLOAD_FILE_BYTES", 10 * 1024 * 1024)
```

and document it in `.env.example`

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "rejects_invalid_form_json or rejects_missing_required_form_fields or rejects_empty_file or rejects_disallowed_extension" -v
```

Expected:
- PASS

### Task 3: Expose Richer Task Status And Lightweight Result Endpoint

**Files:**
- Modify: `server/api.py`
- Modify: `tests/test_bootstrap.py`

- [ ] **Step 1: Write failing tests for detailed task status and lightweight result**

Add tests:

```python
def test_audit_task_status_endpoint_returns_timeline_fields(...) -> None: ...
def test_audit_task_result_endpoint_returns_response_payload(...) -> None: ...
def test_audit_task_result_endpoint_rejects_non_completed_task(...) -> None: ...
```

Expected task-status fields:
- `submitted_at`
- `started_at`
- `finished_at`
- `progress_message`
- `source_mode`

Lightweight result endpoint:
- `GET /audit/tasks/{request_id}/result`
- returns `payload.response`
- if task not `completed`, return `409`

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "timeline_fields or audit_task_result_endpoint" -v
```

Expected:
- FAIL because fields/endpoint do not exist yet

- [ ] **Step 3: Populate richer task fields through the audit lifecycle**

Update `server/api.py` task transitions:

Accepted:

```python
{
    "status": "accepted",
    "mode": mode,
    "source_mode": mode,
    "progress_message": "任务已提交",
    "submitted_at": now,
    "started_at": None,
    "finished_at": None,
    "updated_at": now,
}
```

Running:

```python
{
    "status": "running",
    "progress_message": "正在调用 Claude 审核",
    "started_at": now,
    "updated_at": now,
}
```

Completed:

```python
{
    "status": "completed",
    "progress_message": "审核完成",
    "finished_at": now,
    "updated_at": now,
}
```

Failed:

```python
{
    "status": "failed",
    "progress_message": "审核失败",
    "finished_at": now,
    "updated_at": now,
}
```

- [ ] **Step 4: Add lightweight result endpoint**

In `server/api.py`:

```python
@app.get("/audit/tasks/{request_id}/result")
async def audit_task_result(request_id: str, authorization: str = Header(...)) -> dict[str, Any]:
    tenant = verify_tenant(authorization)
    task = get_audit_task(request_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Audit task not found")
    if task.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Audit task is not completed yet")
    payload = get_result_payload_by_request_id(request_id=request_id, tenant=tenant)
    if payload is None or not isinstance(payload.get("response"), dict):
        raise HTTPException(status_code=404, detail="Audit result not found")
    return payload["response"]
```

- [ ] **Step 5: Re-run the focused tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "timeline_fields or audit_task_result_endpoint" -v
```

Expected:
- PASS

### Task 4: Add Real HTTP Integration Tests

**Files:**
- Modify: `tests/test_bootstrap.py`

- [ ] **Step 1: Write integration tests for directory and upload flows**

Add:

```python
def test_directory_submit_poll_result_flow(monkeypatch: pytest.MonkeyPatch) -> None: ...
def test_upload_submit_poll_result_flow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None: ...
```

Strategy:
- patch `_run_directory_audit` to return a deterministic audit payload and `AgentRunMeta`
- use real `/audit/submit`
- poll `/audit/tasks/{request_id}`
- fetch `/audit/tasks/{request_id}/result`

Directory flow should assert:
- submit returns `accepted`
- task eventually becomes `completed`
- result endpoint returns `result/conclusion/explanation`

Upload flow should assert:
- submit returns `accepted`
- task eventually becomes `completed`
- `data/submissions/{request_id}/audit-request.json` exists
- result endpoint returns structured payload

- [ ] **Step 2: Run the integration tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "submit_poll_result_flow" -v
```

Expected:
- FAIL until lifecycle fields and lightweight result endpoint are fully wired

- [ ] **Step 3: Make the integration tests pass**

Implement any missing glue in `server/api.py` or `server/stores/audit_task_store.py` without broadening scope.

- [ ] **Step 4: Re-run the integration tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "submit_poll_result_flow" -v
```

Expected:
- PASS

### Task 5: Add Submission Cleanup To Maintenance

**Files:**
- Modify: `server/platform/maintenance.py`
- Modify: `server/stores/audit_task_store.py`
- Modify: `tests/test_bootstrap.py`

- [ ] **Step 1: Write failing tests for submission cleanup**

Add a test:

```python
def test_cleanup_old_submission_directories_removes_finished_upload_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ...
```

Setup:
- one completed upload task older than cutoff
- one running upload task
- one completed directory task

Expected:
- only the old completed upload submission directory is removed
- result archives are untouched

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "cleanup_old_submission_directories" -v
```

Expected:
- FAIL because cleanup does not exist yet

- [ ] **Step 3: Implement cleanup helper**

In `server/platform/maintenance.py`, add:

```python
def cleanup_old_submission_directories(days: int) -> list[str]:
    ...
```

Rules:
- only touch tasks whose `source_mode == "upload"`
- only touch tasks whose `status in {"completed", "failed"}`
- use `finished_at` or fallback `updated_at`
- if older than cutoff, remove `case_path` directory when it exists
- keep task record and result archive intact

Add result to `run_maintenance()`:

```python
"removed_submission_dirs": removed_submission_dirs,
```

- [ ] **Step 4: Re-run the focused tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "cleanup_old_submission_directories" -v
```

Expected:
- PASS

### Task 6: Final Verification

**Files:**
- Verify only

- [ ] **Step 1: Run the full bootstrap suite**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -v
```

Expected:
- all tests PASS

- [ ] **Step 2: Verify real directory async flow**

Run:

```bash
curl -X POST http://127.0.0.1:8000/audit/submit \
  -H "Authorization: Bearer sk-default" \
  -H "Content-Type: application/json" \
  -d '{"mode":"directory","directory_path":"data/case1"}'
```

Then:

```bash
curl -H "Authorization: Bearer sk-default" \
  http://127.0.0.1:8000/audit/tasks/<request_id>
```

And:

```bash
curl -H "Authorization: Bearer sk-default" \
  http://127.0.0.1:8000/audit/tasks/<request_id>/result
```

Expected:
- task reaches `completed`
- result endpoint returns the lightweight `payload.response`

- [ ] **Step 3: Verify upload async flow**

Run:

```bash
curl -X POST http://127.0.0.1:8000/audit/submit \
  -H "Authorization: Bearer sk-default" \
  -F 'mode=upload' \
  -F 'form_json={"case_id":"case1","applicant_name":"张三","expense_type":"业务招待"}' \
  -F 'files=@data/case1/dzfp_26322000002323013701_南通烛照智能云平台有限公司_20260326133128.pdf'
```

Then:

```bash
curl -H "Authorization: Bearer sk-default" \
  http://127.0.0.1:8000/audit/tasks/<request_id>
```

Expected:
- task reaches `completed`
- `data/submissions/<request_id>/audit-request.json` exists

- [ ] **Step 4: Commit the implementation**

```bash
git add server/api.py server/platform/config.py server/platform/maintenance.py server/platform/paths.py server/stores/__init__.py server/stores/audit_task_store.py tests/test_bootstrap.py .env.example .ai_state/superpowers/plans/2026-03-31-audit-serve-hardening-plan.md
git commit -m "feat: harden async audit serve flow"
```
