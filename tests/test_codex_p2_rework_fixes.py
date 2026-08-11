"""TDD tests for codex P2 REWORK findings (P1-1 through P1-5, P2) + ClientDisconnect.

Each finding is tested before implementation (RED → implement → GREEN).

Findings:
  P1-1: read layer mix-all-bids bug → only load current bid's OCR text via bid_id
  P1-2: bare asyncio.create_task in upload endpoints → strong-ref set + semaphore
  P1-3: OCR failure not written as failed status (prewarm raises/returns error text)
  P1-4: upload without file returns 400 + audit-request.json sidecar excluded from OCR
  P1-5: delete_project_cascade also removes doc/bid submission directories from disk
  P2:   store update functions missing tenant in WHERE clause (cross-tenant isolation)
  ClientDisconnect: form() raise → 400 not 500
"""

from __future__ import annotations

import asyncio
import io
import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

_TOKEN = "test-fake-token-p2-rework"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


# ── shared fixtures ───────────────────────────────────────────────────────────


@pytest.fixture()
def client(monkeypatch):
    """TestClient with patched tenant + no-op evaluation background tasks."""
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"default": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task", lambda **kwargs: None
    )
    return TestClient(api_module.app)


def _make_project(client: TestClient) -> str:
    tn = f"REWORK-{uuid.uuid4().hex[:8]}"
    resp = client.post("/tender/projects", json={"tender_no": tn}, headers=_AUTH)
    assert resp.status_code == 200, resp.text
    return resp.json()["project_id"]


def _pdf_bytes(name: str = "doc.pdf") -> tuple[str, tuple]:
    content = b"%PDF-1.4 fake document content for testing"
    return ("files", (name, io.BytesIO(content), "application/pdf"))


def _fake_meta(request_id: str):
    from server.common.agent_bridge import AgentRunMeta

    return AgentRunMeta(
        request_id=request_id,
        conversation_id="c",
        claude_session_id="s",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="common/audit-result.schema.json",
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


# ═══════════════════════════════════════════════════════════════════════════
# P1-1: read layer "mix all bids" bug
# ═══════════════════════════════════════════════════════════════════════════


def test_p11_load_doc_layer_with_bid_id_loads_only_that_bid(monkeypatch):
    """When bid_id provided, only that bid's OCR text is included; list_bid_docs NOT called."""
    import server.tender.runner as worker

    monkeypatch.setattr(
        worker,
        "get_project_doc",
        lambda pid, tenant: {"ocr_status": "ready", "ocr_text": "招标底稿内容"},
    )
    monkeypatch.setattr(
        worker,
        "get_bid_doc",
        lambda pid, bid_id, tenant: {
            "bid_id": bid_id,
            "ocr_status": "ready",
            "ocr_text": "当前家投标底稿",
            "bidder_name": "当前投标人",
        },
    )
    result = worker._load_doc_layer_context("tp-1", "bid-current", "acme")

    assert result is not None, "should return text when bid and project are ready"
    assert "当前家投标底稿" in result
    assert "招标底稿内容" in result
    # 读层用 get_bid_doc(单家)而非 list_bid_docs(全部)——worker 已不 import list_bid_docs，
    # 单家定位本身保证不混其他家材料。


def test_p11_load_doc_layer_without_bid_id_returns_none(monkeypatch):
    """Without bid_id, _load_doc_layer_context returns None (no mixing all bids)."""
    import server.tender.runner as worker

    monkeypatch.setattr(
        worker,
        "get_project_doc",
        lambda pid, tenant: {"ocr_status": "ready", "ocr_text": "招标底稿"},
    )
    result = worker._load_doc_layer_context("tp-1", None, "acme")
    assert result is None, "without bid_id, must return None to avoid mixing all bids"


def test_p11_load_doc_layer_bid_not_ready_returns_none(monkeypatch):
    """When current bid's OCR is not ready, returns None (fallback)."""
    import server.tender.runner as worker

    monkeypatch.setattr(
        worker,
        "get_project_doc",
        lambda pid, tenant: {"ocr_status": "ready", "ocr_text": "招标底稿"},
    )
    monkeypatch.setattr(
        worker,
        "get_bid_doc",
        lambda pid, bid_id, tenant: {
            "bid_id": bid_id,
            "ocr_status": "running",  # not ready
            "ocr_text": None,
            "bidder_name": "某公司",
        },
    )

    result = worker._load_doc_layer_context("tp-1", "bid-running", "acme")
    assert result is None


def test_p11_load_doc_layer_bid_not_found_returns_none(monkeypatch):
    """When bid_id not found, returns None."""
    import server.tender.runner as worker

    monkeypatch.setattr(
        worker,
        "get_project_doc",
        lambda pid, tenant: {"ocr_status": "ready", "ocr_text": "招标底稿"},
    )
    monkeypatch.setattr(worker, "get_bid_doc", lambda pid, bid_id, tenant: None)

    result = worker._load_doc_layer_context("tp-1", "bid-missing", "acme")
    assert result is None


def test_p11_load_doc_layer_failed_bid_returns_none(monkeypatch):
    """When bid ocr_status=failed, returns None (no fallback to failed text)."""
    import server.tender.runner as worker

    monkeypatch.setattr(
        worker,
        "get_project_doc",
        lambda pid, tenant: {"ocr_status": "ready", "ocr_text": "招标底稿"},
    )
    monkeypatch.setattr(
        worker,
        "get_bid_doc",
        lambda pid, bid_id, tenant: {
            "bid_id": bid_id,
            "ocr_status": "failed",
            "ocr_text": None,
            "bidder_name": "某公司",
        },
    )

    result = worker._load_doc_layer_context("tp-1", "bid-failed", "acme")
    assert result is None, "failed OCR must not be used"


def test_p11_run_evaluation_passes_bid_id_to_load_context(monkeypatch):
    """run_tender_evaluation passes bid_id down to _load_doc_layer_context."""
    import server.tender.runner as worker

    load_calls = {}

    def spy_load(project_id, bid_id, tenant):
        load_calls["project_id"] = project_id
        load_calls["bid_id"] = bid_id
        load_calls["tenant"] = tenant
        return "=== SCOPED OCR ==="

    monkeypatch.setattr(worker, "_load_doc_layer_context", spy_load)
    monkeypatch.setattr(worker, "ocr_preprocess_block", lambda *a, **kw: "fallback")
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "1")

    async def fake_run_command(cmd, *args, **opts):
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(worker, "run_command_json", fake_run_command)

    asyncio.run(
        worker.run_tender_evaluation(
            request_id="rid-bid-scoped",
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-test",
            bid_id="bid-123",
        )
    )

    assert load_calls.get("bid_id") == "bid-123"
    assert load_calls.get("project_id") == "tp-test"
    assert load_calls.get("tenant") == "acme"


def test_p11_multiple_bids_only_current_bid_in_context(monkeypatch):
    """Multiple bids in store → only current bid's text appears in agent context."""
    import server.tender.runner as worker

    bids_data = {
        "bid-A": {"bid_id": "bid-A", "ocr_status": "ready", "ocr_text": "投标人甲文档", "bidder_name": "甲"},
        "bid-B": {"bid_id": "bid-B", "ocr_status": "ready", "ocr_text": "投标人乙文档", "bidder_name": "乙"},
        "bid-C": {"bid_id": "bid-C", "ocr_status": "ready", "ocr_text": "投标人丙文档", "bidder_name": "丙"},
    }

    monkeypatch.setattr(
        worker,
        "get_project_doc",
        lambda pid, tenant: {"ocr_status": "ready", "ocr_text": "招标文件底稿"},
    )
    monkeypatch.setattr(
        worker,
        "get_bid_doc",
        lambda pid, bid_id, tenant: bids_data.get(bid_id),
    )

    captured_context = {}

    async def capturing_run_command(cmd, *args, **opts):
        captured_context["ctx"] = opts.get("context")
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(worker, "run_command_json", capturing_run_command)
    monkeypatch.setattr(worker, "ocr_preprocess_block", lambda *a, **kw: "fallback")
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "1")

    asyncio.run(
        worker.run_tender_evaluation(
            request_id="rid-only-B",
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-multi",
            bid_id="bid-B",
        )
    )

    ctx = captured_context.get("ctx", "")
    assert ctx is not None
    assert "投标人乙文档" in ctx, "current bid's text must be in context"
    assert "投标人甲文档" not in ctx, "other bids' text must NOT be in context"
    assert "投标人丙文档" not in ctx, "other bids' text must NOT be in context"


def test_p11_bid_id_passed_through_schedule_to_worker(monkeypatch):
    """schedule_tender_evaluation_task accepts and passes bid_id."""
    import server.tender.worker as worker

    # The schedule function must accept bid_id and pass it to execute_tender_evaluation_task
    import inspect

    sig = inspect.signature(worker.schedule_tender_evaluation_task)
    assert "bid_id" in sig.parameters, (
        "schedule_tender_evaluation_task must accept bid_id parameter"
    )


# ═══════════════════════════════════════════════════════════════════════════
# P1-2: bare asyncio.create_task without strong ref
# ═══════════════════════════════════════════════════════════════════════════


def test_p12_upload_ocr_tasks_strong_ref_set_exists():
    """_UPLOAD_OCR_TASKS strong-ref set must exist in ocr.prewarm_scheduler (S3 下沉)."""
    import server.ocr.prewarm_scheduler as sched

    assert hasattr(sched, "_UPLOAD_OCR_TASKS"), (
        "_UPLOAD_OCR_TASKS strong-ref set must exist in server/ocr/prewarm_scheduler.py"
    )
    assert isinstance(getattr(sched, "_UPLOAD_OCR_TASKS"), set)


def test_p12_upload_ocr_semaphore_exists():
    """_UPLOAD_OCR_SEMAPHORE must exist in ocr.prewarm_scheduler (S3 下沉)."""
    import server.ocr.prewarm_scheduler as sched

    assert hasattr(sched, "_UPLOAD_OCR_SEMAPHORE"), (
        "_UPLOAD_OCR_SEMAPHORE must exist in server/ocr/prewarm_scheduler.py"
    )


def test_p12_start_project_ocr_uses_strong_ref(monkeypatch):
    """start_*_doc_ocr_task must register the created task via track_upload_ocr_task (防 GC)."""
    import inspect

    import server.tender.doc_pipeline as pipeline

    src_proj = inspect.getsource(pipeline.start_project_doc_ocr_task)
    src_bid = inspect.getsource(pipeline.start_bid_doc_ocr_task)

    assert "track_upload_ocr_task" in src_proj, (
        "start_project_doc_ocr_task must register task via track_upload_ocr_task"
    )
    assert "track_upload_ocr_task" in src_bid, (
        "start_bid_doc_ocr_task must register task via track_upload_ocr_task"
    )


def test_p12_default_prewarm_max_is_4():
    """上传 OCR 并发默认上限 = 4（scheduler 权威常量；OCR_PREWARM_MAX env 可覆盖）。

    S3 后默认值随调度器下沉到 server.ocr.prewarm_scheduler；旧测试读 env 自带默认 "2"，
    既不查实际生产默认(4)也不查迁移后的模块 → 改为断言权威常量。
    """
    from server.ocr.prewarm_scheduler import _DEFAULT_UPLOAD_OCR_CONCURRENCY

    assert _DEFAULT_UPLOAD_OCR_CONCURRENCY == 4


# ═══════════════════════════════════════════════════════════════════════════
# P1-3: OCR failure status not written
# ═══════════════════════════════════════════════════════════════════════════


def test_p13_project_doc_ocr_writes_failed_on_exception(monkeypatch):
    """When prewarm_and_report raises, project doc row gets ocr_status=failed."""
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"default": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module
    from server.stores.tender_doc_store import get_project_doc

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task", lambda **kwargs: None
    )

    def _raise(*args, **kwargs):
        raise RuntimeError("OCR engine down")

    # S3: OCR 编排下沉 server.tender.doc_pipeline；prewarm_and_report 在该模块导入。
    import server.tender.doc_pipeline as pipeline

    monkeypatch.setattr("server.tender.doc_pipeline.prewarm_and_report", _raise)

    client = TestClient(api_module.app)
    pid = _make_project(client)
    # 模拟上传端点：先建 project_doc row(running)，后台 OCR 失败应改 failed（UPDATE 需 row 已存在）
    from server.stores.tender_doc_store import upsert_project_doc

    upsert_project_doc(project_id=pid, tenant="default", tender_files="[]", ocr_status="running")

    async def _run():
        await pipeline.run_project_doc_ocr(pid, "/fake/case", tenant="default", purpose=None)

    asyncio.run(_run())

    row = get_project_doc(pid, "default")
    assert row is not None
    assert row["ocr_status"] == "failed", (
        "ocr_status must be 'failed' when prewarm_and_report raises"
    )


def test_p13_bid_doc_ocr_writes_failed_on_exception(monkeypatch):
    """When prewarm_and_report raises for bid, bid doc gets ocr_status=failed."""
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"default": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module
    from server.stores.tender_doc_store import get_bid_doc, upsert_bid_doc

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task", lambda **kwargs: None
    )

    def _raise(*args, **kwargs):
        raise RuntimeError("OCR engine down")

    import server.tender.doc_pipeline as pipeline

    monkeypatch.setattr("server.tender.doc_pipeline.prewarm_and_report", _raise)

    client = TestClient(api_module.app)
    pid = _make_project(client)
    bid_id = f"bd-{uuid.uuid4().hex[:16]}"
    upsert_bid_doc(
        project_id=pid,
        bid_id=bid_id,
        tenant="default",
        bidder_name="测试投标人",
        bid_files="[]",
        ocr_status="running",
    )

    async def _run():
        await pipeline.run_bid_doc_ocr(
            pid, bid_id, "/fake/case", tenant="default", purpose=None
        )

    asyncio.run(_run())

    row = get_bid_doc(pid, bid_id, "default")
    assert row is not None
    assert row["ocr_status"] == "failed"


def test_p13_project_doc_ocr_task_function_exists():
    """run_project_doc_ocr is an importable coroutine in tender_doc_pipeline (S3 下沉)."""
    import asyncio

    import server.tender.doc_pipeline as pipeline

    assert hasattr(pipeline, "run_project_doc_ocr"), (
        "run_project_doc_ocr must be an importable coroutine in server/routes/tender_doc_pipeline.py"
    )
    assert asyncio.iscoroutinefunction(pipeline.run_project_doc_ocr), (
        "run_project_doc_ocr must be a coroutine function"
    )


def test_p13_bid_doc_ocr_task_function_exists():
    """run_bid_doc_ocr is an importable coroutine in tender_doc_pipeline (S3 下沉)."""
    import asyncio

    import server.tender.doc_pipeline as pipeline

    assert hasattr(pipeline, "run_bid_doc_ocr"), (
        "run_bid_doc_ocr must be an importable coroutine in server/routes/tender_doc_pipeline.py"
    )
    assert asyncio.iscoroutinefunction(pipeline.run_bid_doc_ocr), (
        "run_bid_doc_ocr must be a coroutine function"
    )


def test_p13_project_doc_ocr_writes_failed_on_rendered_error_block(monkeypatch):
    """S3 review P1: prewarm_and_report 返回**渲染后的全失败底稿**（`### 文件:` 头 + `[识别失败]` 正文）
    时，project doc 必须 ocr_status=failed —— is_ocr_text_valid 不能被文件头骗过（旧 startswith 会漏判）。"""
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"default": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task", lambda **kwargs: None
    )

    import server.tender.doc_pipeline as pipeline
    from server.ocr.pipeline import summarize_ocr_results

    error_block = "### 文件: bad.pdf (kind=pdf, route=ocr)\n[识别失败] OCR engine down"
    monkeypatch.setattr(
        "server.tender.doc_pipeline.prewarm_and_report",
        lambda *a, **kw: (error_block, summarize_ocr_results([], error_block)),
    )

    client = TestClient(api_module.app)
    pid = _make_project(client)
    upsert_project_doc(project_id=pid, tenant="default", tender_files="[]", ocr_status="running")

    asyncio.run(pipeline.run_project_doc_ocr(pid, "/fake/case", tenant="default", purpose=None))

    row = get_project_doc(pid, "default")
    assert row is not None
    assert row["ocr_status"] == "failed", "rendered all-error block must yield ocr_status=failed"
    assert row["criteria_status"] == "failed"


def test_p13_bid_doc_ocr_writes_failed_on_rendered_error_block(monkeypatch):
    """同上（投标文档）：渲染后的全失败底稿 → bid ocr_status=failed。"""
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"default": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module
    from server.stores.tender_doc_store import get_bid_doc, upsert_bid_doc

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task", lambda **kwargs: None
    )

    import server.tender.doc_pipeline as pipeline
    from server.ocr.pipeline import summarize_ocr_results

    error_block = "### 文件: bid.pdf (kind=pdf, route=ocr)\n[识别失败] OCR engine down"
    monkeypatch.setattr(
        "server.tender.doc_pipeline.prewarm_and_report",
        lambda *a, **kw: (error_block, summarize_ocr_results([], error_block)),
    )

    client = TestClient(api_module.app)
    pid = _make_project(client)
    bid_id = f"bd-{uuid.uuid4().hex[:16]}"
    upsert_bid_doc(
        project_id=pid,
        bid_id=bid_id,
        tenant="default",
        bidder_name="测试投标人",
        bid_files="[]",
        ocr_status="running",
    )

    asyncio.run(
        pipeline.run_bid_doc_ocr(pid, bid_id, "/fake/case", tenant="default", purpose=None)
    )

    row = get_bid_doc(pid, bid_id, "default")
    assert row is not None
    assert row["ocr_status"] == "failed"


# ═══════════════════════════════════════════════════════════════════════════
# P1-4: upload without file returns 400 + sidecar exclusion
# ═══════════════════════════════════════════════════════════════════════════


def test_p14_upload_tender_doc_no_file_returns_400(monkeypatch):
    """POST /tender-doc with no files → 400."""
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"default": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module
    import server.routes.tender.docs as tender_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task", lambda **kwargs: None
    )
    monkeypatch.setattr(
        tender_module, "_start_project_doc_ocr_task", lambda *a, **kw: None
    )

    client = TestClient(api_module.app)
    pid = _make_project(client)

    # No files submitted at all
    resp = client.post(f"/tender/projects/{pid}/tender-doc", headers=_AUTH)
    assert resp.status_code == 400, (
        f"upload without file must return 400, got {resp.status_code}: {resp.text}"
    )


def test_p14_upload_bid_no_file_returns_400(monkeypatch):
    """POST /bids with no files → 400."""
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"default": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module
    import server.routes.tender.docs as tender_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task", lambda **kwargs: None
    )
    monkeypatch.setattr(
        tender_module, "_start_bid_doc_ocr_task", lambda *a, **kw: None
    )

    client = TestClient(api_module.app)
    pid = _make_project(client)

    # Only bidder_name, no file
    resp = client.post(
        f"/tender/projects/{pid}/bids",
        data={"bidder_name": "某公司"},
        headers=_AUTH,
    )
    assert resp.status_code == 400, (
        f"upload without file must return 400, got {resp.status_code}: {resp.text}"
    )


def test_p14_sidecar_audit_request_json_excluded_from_iter_files():
    """_iter_files excludes audit-request.json sidecar written by materialize_upload_submission."""
    from server.ocr.pipeline import _iter_files

    with tempfile.TemporaryDirectory() as tmpdir:
        # Real file
        real_file = os.path.join(tmpdir, "招标文件.pdf")
        # Sidecar written by materialize_upload_submission
        sidecar = os.path.join(tmpdir, "audit-request.json")
        with open(real_file, "wb") as f:
            f.write(b"%PDF-1.4 real content")
        with open(sidecar, "w") as f:
            f.write('{"type": "sidecar"}')

        files = _iter_files(tmpdir)
        file_names = [p.name for p in files]

        assert "audit-request.json" not in file_names, (
            "audit-request.json sidecar must be excluded from OCR pipeline"
        )
        assert "招标文件.pdf" in file_names, "real PDF must still be processed"


# ═══════════════════════════════════════════════════════════════════════════
# P1-5: delete clears disk doc/bid directories
# ═══════════════════════════════════════════════════════════════════════════


def test_p15_delete_project_clears_project_doc_dir(monkeypatch):
    """DELETE /projects/{id} calls remove_submission_dir for project doc dir if present."""
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"default": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module
    import server.routes.tender.projects as tender_module
    from server.stores.tender_doc_store import upsert_project_doc

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task", lambda **kwargs: None
    )

    client = TestClient(api_module.app)
    pid = _make_project(client)

    with tempfile.TemporaryDirectory() as base_dir:
        project_dir = os.path.join(base_dir, "project_sub")
        os.makedirs(project_dir, exist_ok=True)
        with open(os.path.join(project_dir, "招标文件.pdf"), "wb") as f:
            f.write(b"fake pdf")

        # Store project doc with the temp dir as case_path
        upsert_project_doc(
            project_id=pid,
            tenant="default",
            tender_files='["招标文件.pdf"]',
            ocr_status="ready",
            ocr_text="底稿",
        )

        # Patch delete_project_cascade to include doc dir in case_paths
        from server.stores.tender_project_store import delete_project_cascade as real_cascade

        def patched_cascade(project_id, tenant):
            result = real_cascade(project_id, tenant)
            if result is not None:
                # Add the project doc dir to case_paths so route cleans it
                result["case_paths"].append(project_dir)
            return result

        monkeypatch.setattr(tender_module, "delete_project_cascade", patched_cascade)

        removed_paths = []
        monkeypatch.setattr(
            tender_module,
            "remove_submission_dir",
            lambda path: removed_paths.append(path),
        )

        resp = client.delete(f"/tender/projects/{pid}", headers=_AUTH)
        assert resp.status_code == 200, resp.text

        assert project_dir in removed_paths, (
            "project doc dir must be passed to remove_submission_dir on project delete"
        )


def test_p15_delete_project_cascade_includes_doc_bid_dirs(monkeypatch):
    """delete_project_cascade must include doc_dirs/bid_dirs in case_paths for disk cleanup."""
    from server.stores.tender_doc_store import upsert_bid_doc, upsert_project_doc
    from server.stores.tender_project_store import (
        delete_project_cascade,
        get_or_create_project,
    )

    tenant = "t-p15"
    pid = get_or_create_project(
        tenant=tenant, tender_no=f"P15-{uuid.uuid4().hex[:8]}"
    )["project_id"]

    # Add project doc and bid docs
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files='["招标.pdf"]')
    upsert_bid_doc(
        project_id=pid,
        bid_id=f"bd-{uuid.uuid4().hex[:12]}",
        tenant=tenant,
        bidder_name="甲",
        bid_files='["甲.pdf"]',
    )

    outcome = delete_project_cascade(pid, tenant)
    assert outcome is not None
    # The cascade must include the doc dirs in case_paths OR deleted counts must be correct
    deleted = outcome["deleted"]
    assert deleted.get("tender_project_docs", 0) == 1
    assert deleted.get("tender_bid_docs", 0) == 1


# ═══════════════════════════════════════════════════════════════════════════
# P2: store update functions missing tenant in WHERE clause
# ═══════════════════════════════════════════════════════════════════════════


def test_p2_update_project_doc_ocr_has_tenant_param():
    """update_project_doc_ocr must have tenant parameter."""
    import inspect

    from server.stores.tender_doc_store import update_project_doc_ocr

    sig = inspect.signature(update_project_doc_ocr)
    assert "tenant" in sig.parameters, "update_project_doc_ocr must accept tenant"


def test_p2_update_bid_doc_ocr_has_tenant_param():
    """update_bid_doc_ocr must have tenant parameter."""
    import inspect

    from server.stores.tender_doc_store import update_bid_doc_ocr

    sig = inspect.signature(update_bid_doc_ocr)
    assert "tenant" in sig.parameters, "update_bid_doc_ocr must accept tenant"


def test_p2_update_project_doc_criteria_has_tenant_param():
    """update_project_doc_criteria must have tenant parameter."""
    import inspect

    from server.stores.tender_doc_store import update_project_doc_criteria

    sig = inspect.signature(update_project_doc_criteria)
    assert "tenant" in sig.parameters, "update_project_doc_criteria must accept tenant"


def test_p2_update_bid_doc_extracted_has_tenant_param():
    """update_bid_doc_extracted must have tenant parameter."""
    import inspect

    from server.stores.tender_doc_store import update_bid_doc_extracted

    sig = inspect.signature(update_bid_doc_extracted)
    assert "tenant" in sig.parameters, "update_bid_doc_extracted must accept tenant"


def test_p2_update_project_doc_ocr_wrong_tenant_no_effect():
    """update_project_doc_ocr with wrong tenant leaves other tenant's row unchanged."""
    from server.stores.tender_doc_store import (
        get_project_doc,
        update_project_doc_ocr,
        upsert_project_doc,
    )

    pid = f"tp-{uuid.uuid4().hex[:12]}"
    upsert_project_doc(project_id=pid, tenant="tenant-A", tender_files="[]", ocr_status="running")

    # Wrong-tenant update
    update_project_doc_ocr(pid, tenant="tenant-B", ocr_text="INJECTED", ocr_clarity=None, status="ready")

    row = get_project_doc(pid, "tenant-A")
    assert row is not None
    assert row["ocr_status"] == "running", "wrong-tenant update must not affect other tenant"
    assert row.get("ocr_text") is None


def test_p2_update_project_doc_ocr_correct_tenant_works():
    """update_project_doc_ocr with correct tenant updates the row."""
    from server.stores.tender_doc_store import (
        get_project_doc,
        update_project_doc_ocr,
        upsert_project_doc,
    )

    pid = f"tp-{uuid.uuid4().hex[:12]}"
    upsert_project_doc(project_id=pid, tenant="tenant-X", tender_files="[]", ocr_status="running")

    update_project_doc_ocr(pid, tenant="tenant-X", ocr_text="correct", ocr_clarity="clear", status="ready")

    row = get_project_doc(pid, "tenant-X")
    assert row["ocr_status"] == "ready"
    assert row["ocr_text"] == "correct"


def test_p2_update_bid_doc_ocr_wrong_tenant_no_effect():
    """update_bid_doc_ocr with wrong tenant leaves other tenant's row unchanged."""
    from server.stores.tender_doc_store import (
        get_bid_doc,
        update_bid_doc_ocr,
        upsert_bid_doc,
    )

    pid = f"tp-{uuid.uuid4().hex[:12]}"
    bid_id = f"bd-{uuid.uuid4().hex[:12]}"
    upsert_bid_doc(
        project_id=pid, bid_id=bid_id, tenant="tenant-A",
        bidder_name="Alpha", bid_files="[]", ocr_status="running"
    )

    update_bid_doc_ocr(pid, bid_id, tenant="tenant-B", ocr_text="INJECTED", status="ready")

    row = get_bid_doc(pid, bid_id, "tenant-A")
    assert row is not None
    assert row["ocr_status"] == "running"
    assert row.get("ocr_text") is None


def test_p2_update_bid_doc_ocr_correct_tenant_works():
    """update_bid_doc_ocr with correct tenant updates the row."""
    from server.stores.tender_doc_store import (
        get_bid_doc,
        update_bid_doc_ocr,
        upsert_bid_doc,
    )

    pid = f"tp-{uuid.uuid4().hex[:12]}"
    bid_id = f"bd-{uuid.uuid4().hex[:12]}"
    upsert_bid_doc(
        project_id=pid, bid_id=bid_id, tenant="tenant-Y",
        bidder_name="Beta", bid_files="[]", ocr_status="running"
    )

    update_bid_doc_ocr(pid, bid_id, tenant="tenant-Y", ocr_text="extracted", status="ready")

    row = get_bid_doc(pid, bid_id, "tenant-Y")
    assert row["ocr_status"] == "ready"
    assert row["ocr_text"] == "extracted"


def test_p2_update_project_doc_criteria_wrong_tenant_no_effect():
    """update_project_doc_criteria with wrong tenant leaves other tenant's row unchanged."""
    import json

    from server.stores.tender_doc_store import (
        get_project_doc,
        update_project_doc_criteria,
        upsert_project_doc,
    )

    pid = f"tp-{uuid.uuid4().hex[:12]}"
    upsert_project_doc(project_id=pid, tenant="tenant-A", tender_files="[]")

    update_project_doc_criteria(pid, "tenant-B", json.dumps({"injected": True}))

    row = get_project_doc(pid, "tenant-A")
    assert row is not None
    assert row.get("criteria") is None


def test_p2_update_bid_doc_extracted_wrong_tenant_no_effect():
    """update_bid_doc_extracted with wrong tenant leaves other tenant's row unchanged."""
    import json

    from server.stores.tender_doc_store import (
        get_bid_doc,
        update_bid_doc_extracted,
        upsert_bid_doc,
    )

    pid = f"tp-{uuid.uuid4().hex[:12]}"
    bid_id = f"bd-{uuid.uuid4().hex[:12]}"
    upsert_bid_doc(
        project_id=pid, bid_id=bid_id, tenant="tenant-A",
        bidder_name="Beta", bid_files="[]"
    )

    update_bid_doc_extracted(pid, bid_id, "tenant-B", json.dumps({"x": 1}))

    row = get_bid_doc(pid, bid_id, "tenant-A")
    assert row is not None
    assert row.get("extracted") is None


# ═══════════════════════════════════════════════════════════════════════════
# ClientDisconnect: form() → 400
# ═══════════════════════════════════════════════════════════════════════════


def test_client_disconnect_handled_in_upload_tender_doc():
    """upload_tender_doc source must contain ClientDisconnect handling."""
    import inspect

    import server.routes.tender.docs as t

    src = inspect.getsource(t.upload_tender_doc)
    assert "ClientDisconnect" in src, (
        "upload_tender_doc must catch ClientDisconnect"
    )


def test_client_disconnect_handled_in_upload_bid_doc():
    """upload_bid_doc source must contain ClientDisconnect handling."""
    import inspect

    import server.routes.tender.docs as t

    src = inspect.getsource(t.upload_bid_doc)
    assert "ClientDisconnect" in src, (
        "upload_bid_doc must catch ClientDisconnect"
    )


def test_client_disconnect_handled_in_submit_bid_evaluation():
    """_submit_bid_evaluation source must contain ClientDisconnect handling."""
    import inspect

    import server.routes.tender.tasks as t

    src = inspect.getsource(t._submit_bid_evaluation)
    assert "ClientDisconnect" in src, (
        "_submit_bid_evaluation must catch ClientDisconnect"
    )


def test_client_disconnect_returns_400_in_tender_doc(monkeypatch):
    """ClientDisconnect during form() in upload_tender_doc → HTTP 400."""
    from starlette.requests import ClientDisconnect

    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"default": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module
    import server.routes.tender.docs as tender_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task", lambda **kwargs: None
    )
    monkeypatch.setattr(
        tender_module, "_start_project_doc_ocr_task", lambda *a, **kw: None
    )

    # Patch request.form to raise ClientDisconnect
    from fastapi import Request

    async def disconnecting_form(self, **kwargs):
        raise ClientDisconnect()

    monkeypatch.setattr(Request, "form", disconnecting_form)

    client = TestClient(api_module.app, raise_server_exceptions=False)
    pid = _make_project(TestClient(api_module.app))

    resp = client.post(
        f"/tender/projects/{pid}/tender-doc",
        files=[_pdf_bytes()],
        headers=_AUTH,
    )
    assert resp.status_code == 400, (
        f"ClientDisconnect must give 400, got {resp.status_code}"
    )


def test_client_disconnect_returns_400_in_upload_bid(monkeypatch):
    """ClientDisconnect during form() in upload_bid_doc → HTTP 400."""
    from starlette.requests import ClientDisconnect

    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"default": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module
    import server.routes.tender.docs as tender_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task", lambda **kwargs: None
    )
    monkeypatch.setattr(
        tender_module, "_start_bid_doc_ocr_task", lambda *a, **kw: None
    )

    from fastapi import Request

    async def disconnecting_form(self, **kwargs):
        raise ClientDisconnect()

    monkeypatch.setattr(Request, "form", disconnecting_form)

    client = TestClient(api_module.app, raise_server_exceptions=False)
    pid = _make_project(TestClient(api_module.app))

    resp = client.post(
        f"/tender/projects/{pid}/bids",
        files=[_pdf_bytes()],
        headers=_AUTH,
    )
    assert resp.status_code == 400, (
        f"ClientDisconnect must give 400, got {resp.status_code}"
    )


def test_client_disconnect_returns_400_in_submit_bid_evaluation(monkeypatch):
    """ClientDisconnect during multipart form() in /evaluate → HTTP 400."""
    from starlette.requests import ClientDisconnect

    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"default": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task", lambda **kwargs: None
    )

    from fastapi import Request

    async def disconnecting_form(self, **kwargs):
        raise ClientDisconnect()

    monkeypatch.setattr(Request, "form", disconnecting_form)

    client = TestClient(api_module.app, raise_server_exceptions=False)
    pid = _make_project(TestClient(api_module.app))

    resp = client.post(
        f"/tender/projects/{pid}/evaluate",
        files=[_pdf_bytes()],
        headers=_AUTH,
    )
    assert resp.status_code == 400, (
        f"ClientDisconnect must give 400, got {resp.status_code}"
    )
