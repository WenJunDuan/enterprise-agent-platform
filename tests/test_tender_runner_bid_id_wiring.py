"""X2：runner.run_tender_evaluation 把 bid_id 透传给 run_command_json（结论落 results.bid_id）。

仿 test_tender_context_slim_wiring.py 的 monkeypatch 手法：不调真 query，patch
runner.run_command_json 捕获调用参数。
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
        schema_name="tender/audit-result.schema.json",
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def test_run_tender_evaluation_forwards_bid_id(monkeypatch):
    import server.tender.runner as runner

    calls: dict = {}

    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        calls.update(opts)
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(runner, "run_command_json", fake_run_command_json)
    monkeypatch.setattr(runner, "get_project_doc", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: "fallback")

    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-bid-wiring",
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-test",
            bid_id="bd-0007",
        )
    )
    assert calls.get("bid_id") == "bd-0007"


def test_run_tender_evaluation_without_bid_id_degrades_safely(monkeypatch):
    """散单 / 非 prewarm 场景 bid_id=None：不崩，透传 None。"""
    import server.tender.runner as runner

    calls: dict = {}

    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        calls.update(opts)
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(runner, "run_command_json", fake_run_command_json)
    monkeypatch.setattr(runner, "get_project_doc", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: "fallback")

    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-bid-none",
            tenant="acme",
            directory_path="/fake/dir",
        )
    )
    assert calls.get("bid_id") is None
