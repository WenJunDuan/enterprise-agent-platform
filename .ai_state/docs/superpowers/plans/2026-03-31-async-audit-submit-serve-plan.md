# Async Audit Submit Serve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an async serve-side audit submission flow that supports both test-stage directory-path submissions and production-style file uploads, then expose task-status polling so the frontend can submit once, poll by `request_id`, and fetch the final audit result.

**Architecture:** Keep the existing synchronous `/audit` and result archive flow intact, but add a new async submit entrypoint that accepts either JSON directory input or multipart upload input. Normalize both modes into a single case directory model, persist lightweight task status separately from request/result archives, and execute the existing audit capability in the background. The frontend polls a dedicated task-status endpoint and reads the final structured result from the existing result-detail endpoint.

**Tech Stack:** FastAPI, Pydantic, Python dataclasses, local JSON/JSONL storage, Claude Agent SDK adapter layer, pytest/TestClient

---

### Task 1: Add Task Status Storage And Path Layout

**Files:**
- Modify: `server/platform/paths.py`
- Create: `server/stores/audit_task_store.py`
- Test: `tests/test_bootstrap.py`

- [ ] **Step 1: Write failing tests for audit-task storage contract**

Add tests that describe the new task-record shape and storage usage:

```python
def test_audit_task_store_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("server.stores.audit_task_store.AUDIT_TASK_FILE", tmp_path / "audit-tasks.json")
    from server.stores.audit_task_store import upsert_audit_task, get_audit_task

    upsert_audit_task(
        {
            "request_id": "req-1",
            "status": "accepted",
            "mode": "directory",
            "case_path": "data/case1",
            "claim_id": None,
            "result_file": None,
            "error_detail": None,
            "updated_at": "2026-03-31T00:00:00+00:00",
        }
    )

    record = get_audit_task("req-1")
    assert record is not None
    assert record["status"] == "accepted"
    assert record["case_path"] == "data/case1"
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "audit_task_store" -v
```

Expected:
- FAIL because `server.stores.audit_task_store` does not exist yet

- [ ] **Step 3: Add audit-task path constants**

Update `server/platform/paths.py` to include:

```python
AUDIT_TASK_DIR = SERVICE_LOG_DIR / "audit-tasks"
AUDIT_TASK_FILE = AUDIT_TASK_DIR / "tasks.json"
SUBMISSION_ROOT_DIR = PROJECT_ROOT / "data" / "submissions"
```

And ensure they are created in `ensure_local_layout()`:

```python
        AUDIT_TASK_DIR,
        SUBMISSION_ROOT_DIR,
```

- [ ] **Step 4: Implement the audit-task store**

Create `server/stores/audit_task_store.py` with a minimal JSON-file-backed store:

```python
@dataclass(slots=True)
class AuditTaskRecord:
    request_id: str
    status: str
    mode: str
    case_path: str
    claim_id: str | None = None
    result_file: str | None = None
    error_detail: str | None = None
    updated_at: str = ""
```

Include helpers:

```python
def upsert_audit_task(record: dict[str, Any]) -> None: ...
def get_audit_task(request_id: str) -> dict[str, Any] | None: ...
```

- [ ] **Step 5: Re-run the focused tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "audit_task_store" -v
```

Expected:
- PASS

### Task 2: Add Async Submit Models And Endpoints

**Files:**
- Modify: `server/api.py`
- Modify: `tests/test_bootstrap.py`
- Test: `tests/test_bootstrap.py`

- [ ] **Step 1: Write failing API tests for async submit and task lookup**

Add tests for both JSON directory mode and task polling:

```python
def test_audit_submit_directory_returns_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    api_module.TENANT_KEYS = _load_tenant_keys()

    async def fake_submit(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "request_id": "req-submit-1",
            "status": "accepted",
            "mode": "directory",
            "task_status_url": "/audit/tasks/req-submit-1",
            "result_url": "/results/req-submit-1",
        }

    monkeypatch.setattr(api_module, "_submit_audit_directory", fake_submit)
    client = TestClient(api_module.app)
    response = client.post(
        "/audit/submit",
        headers={"Authorization": "Bearer sk-demo"},
        json={"mode": "directory", "directory_path": "data/case1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["mode"] == "directory"
```

```python
def test_audit_task_status_endpoint_returns_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    api_module.TENANT_KEYS = _load_tenant_keys()
    monkeypatch.setattr(
        api_module,
        "get_audit_task",
        lambda request_id: {
            "request_id": request_id,
            "status": "running",
            "mode": "directory",
            "case_path": "data/case1",
            "claim_id": None,
            "result_file": None,
            "error_detail": None,
            "updated_at": "2026-03-31T00:00:00+00:00",
        },
    )
    client = TestClient(api_module.app)
    response = client.get("/audit/tasks/req-submit-1", headers={"Authorization": "Bearer sk-demo"})
    assert response.status_code == 200
    assert response.json()["status"] == "running"
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "audit_submit_directory or audit_task_status_endpoint" -v
```

Expected:
- FAIL because `/audit/submit` and `/audit/tasks/{request_id}` do not exist yet

- [ ] **Step 3: Add request/response models and endpoints**

In `server/api.py`, add:

```python
class DirectoryAuditSubmitRequest(BaseModel):
    mode: Literal["directory"]
    directory_path: str


class AuditSubmitAcceptedResponse(BaseModel):
    request_id: str
    status: str
    mode: str
    task_status_url: str
    result_url: str
```

Add endpoint:

```python
@app.post("/audit/submit", response_model=AuditSubmitAcceptedResponse)
async def audit_submit(...):
    ...
```

Add endpoint:

```python
@app.get("/audit/tasks/{request_id}")
async def audit_task_status(...):
    ...
```

- [ ] **Step 4: Re-run focused tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "audit_submit_directory or audit_task_status_endpoint" -v
```

Expected:
- PASS

### Task 3: Implement Background Execution For Directory Mode

**Files:**
- Modify: `server/api.py`
- Modify: `server/command_adapter.py`
- Modify: `tests/test_bootstrap.py`

- [ ] **Step 1: Write failing tests for async background execution state transitions**

Add a unit-style test that patches the background runner path:

```python
def test_audit_submit_directory_marks_task_running_then_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    updates: list[dict[str, Any]] = []

    monkeypatch.setattr(api_module, "upsert_audit_task", lambda record: updates.append(record.copy()))

    async def fake_run_command_json(*args: Any, **kwargs: Any):
        return (
            {
                "claim_id": "CASE-001",
                "verdict": "manual_review",
                "result": False,
                "conclusion": "待人工复核",
                "explanation": "根据《费用报销管理制度》相关条款，现有材料不足以自动判断。",
                "reasons": ["缺少关键材料"],
                "policy_refs": ["expense.travel.001"],
                "risk_score": 70,
                "extracted_data": {},
                "evidence_chain": [],
                "reviewed_by": "expense-auditor",
                "timestamp": "2026-03-31T00:00:00+00:00",
            },
            AgentRunMeta(
                request_id="req-submit-1",
                conversation_id="conv-1",
                claude_session_id="sess-1",
                resume_session_id=None,
                fork_from_session_id=None,
                schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
                log_file="logs/sessions/events/audit.jsonl",
                result_file="results/by-request/req-submit-1.json",
                result_subtype="success",
                cost_usd=0.2,
                finished_at="2026-03-31T00:00:00+00:00",
            ),
        )

    monkeypatch.setattr(api_module, "_run_directory_audit", fake_run_command_json)
    asyncio.run(api_module._execute_directory_audit_task(request_id="req-submit-1", tenant="demo", directory_path="data/case1"))

    assert updates[0]["status"] == "running"
    assert updates[-1]["status"] == "completed"
    assert updates[-1]["claim_id"] == "CASE-001"
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "marks_task_running_then_completed" -v
```

Expected:
- FAIL because `_execute_directory_audit_task` does not exist yet

- [ ] **Step 3: Implement the background task runner**

In `server/api.py`, add:

```python
async def _run_directory_audit(*, request_id: str, tenant: str, directory_path: str):
    return await run_command_json(
        "audit",
        directory_path,
        schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
        request_id=request_id,
        tenant=tenant,
    )
```

And:

```python
async def _execute_directory_audit_task(*, request_id: str, tenant: str, directory_path: str) -> None:
    upsert_audit_task({... "status": "running" ...})
    try:
        payload, meta = await _run_directory_audit(...)
        upsert_audit_task({... "status": "completed", "claim_id": payload.get("claim_id"), "result_file": meta.result_file ...})
    except Exception as exc:
        upsert_audit_task({... "status": "failed", "error_detail": str(exc) ...})
```

The submit endpoint should schedule it with:

```python
asyncio.create_task(_execute_directory_audit_task(...))
```

- [ ] **Step 4: Re-run focused tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "marks_task_running_then_completed" -v
```

Expected:
- PASS

### Task 4: Add Upload Mode And Submission Directory Materialization

**Files:**
- Modify: `server/api.py`
- Modify: `server/platform/paths.py`
- Modify: `tests/test_bootstrap.py`

- [ ] **Step 1: Write failing tests for upload mode**

Add a multipart upload test:

```python
def test_audit_submit_upload_writes_submission_case(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    api_module.TENANT_KEYS = _load_tenant_keys()
    monkeypatch.setattr(api_module, "SUBMISSION_ROOT_DIR", tmp_path)

    client = TestClient(api_module.app)
    response = client.post(
        "/audit/submit",
        headers={"Authorization": "Bearer sk-demo"},
        files={"files": ("invoice.pdf", b"pdf-bytes", "application/pdf")},
        data={
            "mode": "upload",
            "form_json": json.dumps({"case_id": "case1", "expense_type": "业务招待"}, ensure_ascii=False),
        },
    )

    assert response.status_code == 200
    request_id = response.json()["request_id"]
    case_dir = tmp_path / request_id
    assert (case_dir / "audit-request.json").is_file()
    assert (case_dir / "invoice.pdf").is_file()
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "submit_upload_writes_submission_case" -v
```

Expected:
- FAIL because upload mode is not implemented

- [ ] **Step 3: Implement upload parsing and materialization**

In `server/api.py`, update `POST /audit/submit` to accept multipart:

```python
@app.post("/audit/submit", response_model=AuditSubmitAcceptedResponse)
async def audit_submit(
    authorization: str = Header(...),
    mode: str | None = Form(None),
    directory_request: DirectoryAuditSubmitRequest | None = None,
    form_json: str | None = Form(None),
    files: list[UploadFile] | None = File(None),
):
    ...
```

For upload mode:

```python
case_dir = SUBMISSION_ROOT_DIR / request_id
case_dir.mkdir(parents=True, exist_ok=True)
```

Write each uploaded file to `case_dir`, then write `audit-request.json` with:

```python
{
    "form": parsed_form_json,
    "attachments": [
        {
            "type": "uploaded",
            "name": safe_name,
            "path": str(saved_path.relative_to(PROJECT_ROOT)),
        }
    ],
}
```

Then schedule the same background task using `case_dir` as the directory to audit.

- [ ] **Step 4: Re-run focused tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -k "submit_upload_writes_submission_case" -v
```

Expected:
- PASS

### Task 5: End-To-End Verification For Directory Mode

**Files:**
- Verify only: `data/case1/`

- [ ] **Step 1: Run the full bootstrap suite**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_bootstrap.py -v
```

Expected:
- all tests PASS

- [ ] **Step 2: Run a real async directory submission**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run app-server start
```

Then:

```bash
curl -X POST http://127.0.0.1:8000/audit/submit \
  -H "Authorization: Bearer sk-default" \
  -H "Content-Type: application/json" \
  -d '{"mode":"directory","directory_path":"data/case1"}'
```

Expected:
- returns `status: accepted`
- includes `request_id`

- [ ] **Step 3: Poll task status**

Run:

```bash
curl -H "Authorization: Bearer sk-default" \
  http://127.0.0.1:8000/audit/tasks/<request_id>
```

Expected:
- eventually returns `status: completed`

- [ ] **Step 4: Fetch final result**

Run:

```bash
curl -H "Authorization: Bearer sk-default" \
  http://127.0.0.1:8000/results/<request_id>
```

Expected:
- payload contains structured result with `result`, `conclusion`, `explanation`, `extracted_data`, `policy_refs`, and `evidence_chain`

- [ ] **Step 5: Commit the implementation**

```bash
git add server/api.py server/platform/paths.py server/stores/audit_task_store.py server/command_adapter.py tests/test_bootstrap.py .ai_state/docs/superpowers/specs/2026-03-31-async-audit-submit-serve-design.md .ai_state/docs/superpowers/plans/2026-03-31-async-audit-submit-serve-plan.md data/case1/audit-request.json
git commit -m "feat: add async audit submit serve flow"
```
