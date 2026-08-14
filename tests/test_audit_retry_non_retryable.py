"""audit 侧同型重试环（2026-08-14 事故 Bug 2 的第二个消费者）：确定性失败不得进重试环。

tender 侧语义已由 ``tests/test_tender_retry_non_retryable.py`` 锁住；audit 还有两处同型循环
——``server/audit/runner.py`` 的 CLI 路径与 ``server/audit/direct.py`` 的直连路径——同样把
"Prompt is too long" 当可重试错误。三处共用 ``server.common.contract`` 的单一判定。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from server.common.contract import JSONContractError, is_non_retryable

# 事故日志原文（内网网关把 SDK ResultMessage.result 原样透出 → JSONContractError）
PROMPT_TOO_LONG = "API Error: 400 {'error': {'message': 'Prompt is too long: 78000 tokens > 65536'}}"
# 对照：真·偶发契约失败（同 prompt 重跑可成功）
RETRYABLE_CONTRACT_FAILURE = "Claude returned no structured output."
CONTRACT_MAX_RETRY = 2


def test_shared_decision_matches_the_gateway_message_case_insensitively():
    """判定上提到 common 后，仍按消息子串识别、大小写不敏感（tender 侧原语义逐字保留）。"""
    assert is_non_retryable(JSONContractError(PROMPT_TOO_LONG))
    assert is_non_retryable(RuntimeError("gateway said: PROMPT IS TOO LONG"))
    assert not is_non_retryable(JSONContractError(RETRYABLE_CONTRACT_FAILURE))


def _run_cli_with_failure(monkeypatch, tmp_path, exc: Exception) -> list[str]:
    """跑一次 CLI 路径审核（模型调用必失败），返回实际发起的尝试列表。"""
    from server.audit import runner

    attempts: list[str] = []

    async def failing_run_agent_json(prompt, *, schema_name, request_id, tenant, **opts):
        attempts.append(request_id)
        raise exc

    monkeypatch.setenv("AUDIT_CONTRACT_MAX_RETRY", str(CONTRACT_MAX_RETRY))
    monkeypatch.delenv("AUDIT_DIRECT_CONNECT", raising=False)
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runner, "EXPENSE_RULES_DIR", tmp_path / "no-rules")
    monkeypatch.setattr(runner, "run_agent_json", failing_run_agent_json)
    with pytest.raises(type(exc)):
        asyncio.run(
            runner.run_inline_directory_audit(
                "no/such/dir", request_id="rid-audit-cli", tenant="acme"
            )
        )
    return attempts


def test_cli_path_raises_prompt_too_long_on_first_attempt(monkeypatch, tmp_path, caplog):
    attempts = _run_cli_with_failure(monkeypatch, tmp_path, JSONContractError(PROMPT_TOO_LONG))

    assert len(attempts) == 1
    # 确定性失败不得留下 "retrying" 日志——那正是当初掩盖真因的东西
    assert not [r for r in caplog.records if "retrying" in r.getMessage()]


def test_cli_path_other_contract_errors_still_exhaust_retries(monkeypatch, tmp_path):
    """对照：其余契约失败的重试行为逐字不变。"""
    attempts = _run_cli_with_failure(
        monkeypatch, tmp_path, JSONContractError(RETRYABLE_CONTRACT_FAILURE)
    )

    assert len(attempts) == CONTRACT_MAX_RETRY + 1


class _TextBlock:
    """anthropic SDK 响应内容块的最小替身（只需 type/text 两个属性）。"""

    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    def __init__(self) -> None:
        self.content = [_TextBlock('{"verdict": "manual_review"}')]
        self.usage = None


class _FakeMessages:
    def __init__(self, attempts: list[str]) -> None:
        self._attempts = attempts

    async def create(self, **kwargs: Any) -> _FakeResponse:
        self._attempts.append(kwargs["model"])
        return _FakeResponse()


class _FakeClient:
    def __init__(self, attempts: list[str]) -> None:
        self.messages = _FakeMessages(attempts)


def _run_direct_with_failure(monkeypatch, exc: Exception) -> list[str]:
    """跑一次直连路径的契约重试环（网关每次都答，但契约段必失败）。"""
    from server.audit import direct

    attempts: list[str] = []

    def failing_semantics(schema_name, parsed, **kwargs):
        raise exc

    monkeypatch.setattr(direct, "apply_schema_semantics", failing_semantics)
    with pytest.raises(direct.DirectContractError):
        asyncio.run(
            direct._run_contract_retry_loop(
                _FakeClient(attempts),
                "model-test",
                1024,
                "prompt",
                request_id="rid-audit-direct",
                tenant="acme",
                schema_name="common/audit-result.schema.json",
                contract_max_retry=CONTRACT_MAX_RETRY,
                project_id=None,
                archive_to_results=False,
            )
        )
    return attempts


def test_direct_path_raises_prompt_too_long_on_first_attempt(monkeypatch, caplog):
    attempts = _run_direct_with_failure(monkeypatch, JSONContractError(PROMPT_TOO_LONG))

    assert len(attempts) == 1
    assert not [r for r in caplog.records if "retrying" in r.getMessage()]


def test_direct_path_other_contract_errors_still_exhaust_retries(monkeypatch):
    """对照：直连路径其余契约失败仍重试满额并以 DirectContractError 收口。"""
    attempts = _run_direct_with_failure(
        monkeypatch, JSONContractError(RETRYABLE_CONTRACT_FAILURE)
    )

    assert len(attempts) == CONTRACT_MAX_RETRY + 1
