"""Bug 2（2026-08-14 生产事故）：确定性失败不得进契约重试环。

事故里 "Prompt is too long" 被当成可重试错误，同一个过长 prompt 在 700ms 内原样重发 3 次——
纯浪费，且把真因（上下文爆窗）埋在三条一模一样的重试日志后面。
"""

from __future__ import annotations

import asyncio

import pytest

from server.common.agent_bridge import AgentRunMeta
from server.common.contract import JSONContractError
from server.tender import doc_layer

# 事故日志原文（内网网关把 SDK ResultMessage.result 原样透出 → JSONContractError）
PROMPT_TOO_LONG = "API Error: 400 {'error': {'message': 'Prompt is too long: 78000 tokens > 65536'}}"


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


def _stub_context(monkeypatch, runner) -> None:
    monkeypatch.setattr(doc_layer, "load_doc_layer_context", lambda *_a, **_kw: None)
    monkeypatch.setattr(doc_layer, "load_doc_layer_context_slim", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: "底稿")
    monkeypatch.setattr(runner, "resolve_project_criteria", lambda *_a, **_kw: (None, None))


def _run_with_failure(monkeypatch, runner, exc: Exception) -> list[str]:
    attempts: list[str] = []

    async def failing_run_command_json(command_name, *arguments, schema_name, **opts):
        attempts.append(opts["request_id"])
        raise exc

    _stub_context(monkeypatch, runner)
    monkeypatch.setattr(runner, "run_command_json", failing_run_command_json)
    with pytest.raises(type(exc)):
        asyncio.run(
            runner.run_tender_evaluation(
                request_id="rid-retry",
                tenant="acme",
                directory_path="/fake/dir",
                project_id="tp-test",
            )
        )
    return attempts


def test_prompt_too_long_raises_on_first_attempt(monkeypatch):
    from server.tender import runner

    attempts = _run_with_failure(monkeypatch, runner, JSONContractError(PROMPT_TOO_LONG))

    assert len(attempts) == 1


def test_other_contract_errors_still_exhaust_retries(monkeypatch):
    """对照：其余契约失败（deepseek 偶发不出 JSON）的重试行为逐字不变。"""
    from server.tender import runner

    attempts = _run_with_failure(
        monkeypatch,
        runner,
        JSONContractError("文本模式下未能从模型输出中解析出 JSON 对象"),
    )

    assert len(attempts) == runner.TENDER_CONTRACT_MAX_RETRY + 1


def test_non_retryable_marker_short_circuits_before_the_retry_log(monkeypatch, caplog):
    """确定性失败不得留下"retrying"日志——那正是当初掩盖真因的东西。"""
    from server.tender import runner

    _run_with_failure(monkeypatch, runner, JSONContractError(PROMPT_TOO_LONG))

    assert not [r for r in caplog.records if "retrying" in r.getMessage()]


def test_success_after_one_retryable_failure_is_unaffected(monkeypatch):
    """对照：可重试错误后成功的既有路径（含 meta.retry_count）不受影响。"""
    from server.tender import runner

    attempts: list[str] = []

    async def flaky(command_name, *arguments, schema_name, **opts):
        attempts.append(opts["request_id"])
        if len(attempts) == 1:
            raise JSONContractError("Claude returned no structured output.")
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    _stub_context(monkeypatch, runner)
    monkeypatch.setattr(runner, "run_command_json", flaky)
    _payload, meta = asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-retry-ok",
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-test",
        )
    )

    assert len(attempts) == 2
    assert meta.retry_count == 1
