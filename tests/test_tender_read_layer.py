"""Tests for the tender evaluation read layer in tender_worker._run_evaluation.

TDD: tests written before implementation.

The read layer: if TENDER_READ_DOC_LAYER=1 (default), _run_evaluation should
try to pull ocr_text from tender_doc_store before calling ocr_preprocess_block.

Cases:
1. tender_project_doc ready + all bid docs ready → use doc layer text, skip ocr_preprocess_block.
2. tender_project_doc missing/not-ready → fall back to ocr_preprocess_block.
3. TENDER_READ_DOC_LAYER=0 → always fall back to ocr_preprocess_block.
"""

from __future__ import annotations

import asyncio

from server.common.agent_bridge import AgentRunMeta


def _fake_meta(request_id: str) -> AgentRunMeta:
    return AgentRunMeta(
        request_id=request_id,
        conversation_id="conv-test",
        claude_session_id="sess-test",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="common/audit-result.schema.json",
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def _make_fake_run_command(calls: dict):
    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        calls["context"] = opts.get("context")
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    return fake_run_command_json


def test_read_layer_uses_doc_store_when_ready(monkeypatch):
    """When doc layer is enabled and docs are ready, ocr_preprocess_block is NOT called."""
    import server.routes.tender_worker as worker

    calls: dict = {}

    monkeypatch.setattr(worker, "run_command_json", _make_fake_run_command(calls))

    # Provide ready doc store data
    monkeypatch.setattr(
        worker,
        "_load_doc_layer_context",
        lambda project_id, tenant: "=== DOC LAYER TEXT ===",
    )
    # ocr_preprocess_block should NOT be called
    preprocess_called = []
    monkeypatch.setattr(
        worker,
        "ocr_preprocess_block",
        lambda *a, **kw: preprocess_called.append(True) or "fallback",
    )
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "1")

    asyncio.run(
        worker._run_evaluation(
            request_id="rid-layer-ready",
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-test",
        )
    )

    assert not preprocess_called, "ocr_preprocess_block must not be called when doc layer is ready"
    assert calls["context"] is not None
    assert "DOC LAYER TEXT" in calls["context"]


def test_read_layer_fallback_when_doc_missing(monkeypatch):
    """When doc layer returns None (missing/not-ready), ocr_preprocess_block is called."""
    import server.routes.tender_worker as worker

    calls: dict = {}
    monkeypatch.setattr(worker, "run_command_json", _make_fake_run_command(calls))

    # Doc layer returns None (no data available)
    monkeypatch.setattr(
        worker,
        "_load_doc_layer_context",
        lambda project_id, tenant: None,
    )

    preprocess_called = []

    def fake_preprocess(directory_path, *, purpose=None):
        preprocess_called.append(directory_path)
        return "fallback OCR text"

    monkeypatch.setattr(worker, "ocr_preprocess_block", fake_preprocess)
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "1")

    asyncio.run(
        worker._run_evaluation(
            request_id="rid-layer-missing",
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-missing",
        )
    )

    assert preprocess_called, "ocr_preprocess_block must be called when doc layer has no data"


def test_read_layer_disabled_always_falls_back(monkeypatch):
    """When TENDER_READ_DOC_LAYER=0, ocr_preprocess_block is always called."""
    import server.routes.tender_worker as worker

    calls: dict = {}
    monkeypatch.setattr(worker, "run_command_json", _make_fake_run_command(calls))

    load_called = []
    monkeypatch.setattr(
        worker,
        "_load_doc_layer_context",
        lambda project_id, tenant: load_called.append(True) or "doc layer",
    )

    preprocess_called = []

    def fake_preprocess(directory_path, *, purpose=None):
        preprocess_called.append(directory_path)
        return "fallback OCR text"

    monkeypatch.setattr(worker, "ocr_preprocess_block", fake_preprocess)
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "0")

    asyncio.run(
        worker._run_evaluation(
            request_id="rid-layer-disabled",
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-disabled",
        )
    )

    # When disabled, doc layer load must NOT be called, fallback must be called
    assert not load_called, "_load_doc_layer_context must not be called when layer disabled"
    assert preprocess_called, "ocr_preprocess_block must be called when layer disabled"


def test_read_layer_no_project_id_falls_back(monkeypatch):
    """When project_id is None, doc layer is skipped, ocr_preprocess_block is called."""
    import server.routes.tender_worker as worker

    calls: dict = {}
    monkeypatch.setattr(worker, "run_command_json", _make_fake_run_command(calls))

    load_called = []
    monkeypatch.setattr(
        worker,
        "_load_doc_layer_context",
        lambda project_id, tenant: load_called.append(True) or "doc layer",
    )

    preprocess_called = []

    def fake_preprocess(directory_path, *, purpose=None):
        preprocess_called.append(directory_path)
        return "fallback OCR text"

    monkeypatch.setattr(worker, "ocr_preprocess_block", fake_preprocess)
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "1")

    asyncio.run(
        worker._run_evaluation(
            request_id="rid-no-project",
            tenant="acme",
            directory_path="/fake/dir",
            project_id=None,  # no project_id → skip doc layer
        )
    )

    assert not load_called, "_load_doc_layer_context must not be called when project_id is None"
    assert preprocess_called


def test_load_doc_layer_context_ready(monkeypatch):
    """_load_doc_layer_context returns text when project_doc is ready + at least one bid ready."""
    import server.routes.tender_worker as worker

    monkeypatch.setattr(
        worker,
        "get_project_doc",
        lambda pid, tenant: {"ocr_status": "ready", "ocr_text": "招标底稿"},
    )
    monkeypatch.setattr(
        worker,
        "list_bid_docs",
        lambda pid, tenant: [
            {"bid_id": "b1", "ocr_status": "ready", "ocr_text": "投标底稿A"},
        ],
    )

    result = worker._load_doc_layer_context("tp-ready", "acme")
    assert result is not None
    assert "招标底稿" in result
    assert "投标底稿A" in result


def test_load_doc_layer_context_project_not_ready(monkeypatch):
    """_load_doc_layer_context returns None when project_doc is not ready."""
    import server.routes.tender_worker as worker

    monkeypatch.setattr(
        worker,
        "get_project_doc",
        lambda pid, tenant: {"ocr_status": "running", "ocr_text": None},
    )
    monkeypatch.setattr(worker, "list_bid_docs", lambda pid, tenant: [])

    result = worker._load_doc_layer_context("tp-not-ready", "acme")
    assert result is None


def test_load_doc_layer_context_missing(monkeypatch):
    """_load_doc_layer_context returns None when project_doc row doesn't exist."""
    import server.routes.tender_worker as worker

    monkeypatch.setattr(worker, "get_project_doc", lambda pid, tenant: None)
    monkeypatch.setattr(worker, "list_bid_docs", lambda pid, tenant: [])

    result = worker._load_doc_layer_context("tp-none", "acme")
    assert result is None


def test_load_doc_layer_context_exception_returns_none(monkeypatch):
    """_load_doc_layer_context swallows exceptions and returns None (fallback safety)."""
    import server.routes.tender_worker as worker

    def explode(pid, tenant):
        raise RuntimeError("DB gone")

    monkeypatch.setattr(worker, "get_project_doc", explode)

    result = worker._load_doc_layer_context("tp-explode", "acme")
    assert result is None
