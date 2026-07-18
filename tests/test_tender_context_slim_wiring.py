"""Tests for D8 slimming dispatch and runner fallback behavior."""

from __future__ import annotations

import asyncio
import json

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


def _run_evaluation(monkeypatch, runner, *, request_id: str):
    calls: dict = {}

    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        calls["context"] = opts.get("context")
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(runner, "run_command_json", fake_run_command_json)
    monkeypatch.setattr(runner, "get_project_doc", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: "fallback")
    asyncio.run(
        runner.run_tender_evaluation(
            request_id=request_id,
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-test",
        )
    )
    return calls["context"]


def test_flag_off_dispatches_original_loader(monkeypatch):
    import server.tender.runner as runner

    monkeypatch.delenv("TENDER_SLIM_CONTEXT", raising=False)
    monkeypatch.setattr(runner, "_load_doc_layer_context", lambda *_a, **_kw: "full sentinel")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("slim loader must not run when the flag is off")

    monkeypatch.setattr(runner, "_load_doc_layer_context_slim", fail_if_called)

    context = _run_evaluation(monkeypatch, runner, request_id="rid-slim-off")

    assert "full sentinel" in context


def test_flag_on_dispatches_slim_loader(monkeypatch):
    import server.tender.runner as runner

    monkeypatch.setenv("TENDER_SLIM_CONTEXT", "1")
    monkeypatch.setattr(runner, "_load_doc_layer_context_slim", lambda *_a, **_kw: "slim sentinel")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("full loader must not run when the flag is on")

    monkeypatch.setattr(runner, "_load_doc_layer_context", fail_if_called)

    context = _run_evaluation(monkeypatch, runner, request_id="rid-slim-on")

    assert "slim sentinel" in context


def _ready_docs(*, criteria, tender_text="complete tender text"):
    project_doc = {
        "ocr_status": "ready",
        "ocr_text": tender_text,
        "criteria": criteria,
    }
    bid = {
        "ocr_status": "ready",
        "ocr_text": "complete bid text",
        "bid_id": "bid-1",
        "bidder_name": "Acme",
    }
    return project_doc, bid


def test_load_doc_layer_context_slim_falls_back_to_full_when_criteria_missing(monkeypatch):
    import server.tender.runner as runner

    project_doc, bid = _ready_docs(criteria=None)
    monkeypatch.setattr(runner, "get_project_doc", lambda *_a, **_kw: project_doc)
    monkeypatch.setattr(runner, "get_bid_doc", lambda *_a, **_kw: bid)

    result = runner._load_doc_layer_context_slim("tp-test", "bid-1", "acme")

    assert result is not None
    assert "=== 招标文件底稿 ===\ncomplete tender text" in result
    assert "=== 投标文件（Acme）底稿 ===\ncomplete bid text" in result


def test_load_doc_layer_context_slim_falls_back_to_full_when_slim_builder_returns_none(
    monkeypatch,
):
    import server.tender.runner as runner

    project_doc, bid = _ready_docs(criteria=json.dumps({"items": [{"item": "missing"}]}))
    monkeypatch.setattr(runner, "get_project_doc", lambda *_a, **_kw: project_doc)
    monkeypatch.setattr(runner, "get_bid_doc", lambda *_a, **_kw: bid)
    monkeypatch.setattr(runner, "build_slim_tender_context", lambda *a, **kw: None)

    result = runner._load_doc_layer_context_slim("tp-test", "bid-1", "acme")

    assert result is not None
    assert "=== 招标文件底稿 ===\ncomplete tender text" in result
    assert "=== 投标文件（Acme）底稿 ===\ncomplete bid text" in result


def test_load_doc_layer_context_slim_uses_slim_text_when_criteria_present(monkeypatch):
    import server.tender.runner as runner

    tender_text = """
    ### 文件: tender.pdf (kind=pdf_text, route=native)
    【第 1 页】
    # 第一章 评标办法
    技术方案评分章节内容。
    # 第二章 资格审查
    营业执照资格章节内容。
    # 第三章 商务条款
    商务条款章节独有内容。
    """.strip()
    criteria = json.dumps(
        {
            "eligibility_rules": [{"check": "营业执照"}],
            "items": [{"item": "技术方案"}],
        },
        ensure_ascii=False,
    )
    project_doc, bid = _ready_docs(criteria=criteria, tender_text=tender_text)
    monkeypatch.setattr(runner, "get_project_doc", lambda *_a, **_kw: project_doc)
    monkeypatch.setattr(runner, "get_bid_doc", lambda *_a, **_kw: bid)

    result = runner._load_doc_layer_context_slim("tp-test", "bid-1", "acme")

    assert result is not None
    tender_block, bid_block = result.split("\n\n=== 投标文件", maxsplit=1)
    assert len(tender_block) < len("=== 招标文件底稿 ===\n" + tender_text)
    assert "商务条款章节独有内容" not in tender_block
    assert bid_block.endswith("complete bid text")
