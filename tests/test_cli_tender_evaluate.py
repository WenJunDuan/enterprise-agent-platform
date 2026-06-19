"""CLI 测试：tender-evaluate / tender-evaluate-json 子命令（镜像 audit / audit-json）。

只验证命令注册 + 正确转发到 command_adapter（命令名、schema），不触发真实 Claude 运行。
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

import server.cli as cli
from server.common.agent_bridge import AgentRunMeta

runner = CliRunner()

EVAL_SCHEMA = "common/audit-result.schema.json"


def _runtime_ok() -> dict:
    return {"status": "ok"}


def _make_meta(conversation_id: str) -> AgentRunMeta:
    return AgentRunMeta(
        request_id="req-eval-1",
        conversation_id=conversation_id,
        claude_session_id="sess-eval-1",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=EVAL_SCHEMA,
        log_file="logs/service/eval.log",
        result_file="logs/service/eval-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def test_evaluate_bid_commands_registered() -> None:
    assert runner.invoke(cli.app, ["tender-evaluate", "--help"]).exit_code == 0
    assert runner.invoke(cli.app, ["tender-evaluate-json", "--help"]).exit_code == 0


def test_evaluate_bid_forwards_to_command_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    async def fake_full(command_name: str, *arguments: str, **opts) -> str:
        calls.append((command_name, arguments, opts))
        return "EVAL_TEXT_OK"

    monkeypatch.setattr(cli, "get_claude_runtime_report", _runtime_ok)
    monkeypatch.setattr(cli, "run_command_full", fake_full)

    result = runner.invoke(
        cli.app, ["tender-evaluate", "cases/r2024007", "--conversation-id", "conv-eval"]
    )

    assert result.exit_code == 0, result.output
    assert "EVAL_TEXT_OK" in result.output
    assert len(calls) == 1
    command_name, arguments, opts = calls[0]
    assert command_name == "tender-evaluate"
    assert arguments == ("cases/r2024007",)
    assert opts["conversation_id"] == "conv-eval"


def test_evaluate_bid_json_uses_audit_result_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    async def fake_json(command_name: str, *arguments: str, schema_name: str, **opts):
        calls.append((command_name, arguments, schema_name, opts))
        return {"verdict": "manual_review"}, _make_meta(opts.get("conversation_id", ""))

    monkeypatch.setattr(cli, "get_claude_runtime_report", _runtime_ok)
    monkeypatch.setattr(cli, "run_command_json", fake_json)

    result = runner.invoke(
        cli.app,
        ["tender-evaluate-json", "cases/r2024007", "--conversation-id", "conv-eval-json"],
    )

    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    command_name, arguments, schema_name, opts = calls[0]
    assert command_name == "tender-evaluate"
    assert arguments == ("cases/r2024007",)
    assert schema_name == EVAL_SCHEMA
    assert opts["conversation_id"] == "conv-eval-json"

    payload = json.loads(result.output)
    assert payload["schema_name"] == EVAL_SCHEMA
    assert payload["response"] == {"verdict": "manual_review"}
    assert payload["request_id"] == "req-eval-1"
