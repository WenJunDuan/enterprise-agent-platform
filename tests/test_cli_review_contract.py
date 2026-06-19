"""CLI 测试：review-contract / review-contract-json（镜像 tender-evaluate-bid + 落库持久化）。

验证命令注册 + 转发到 command_adapter（命令名 review-contract、schema=audit-result），
以及 -json 变体在 run 后调 persist_contract_from_result 落库，不触发真实 Claude。
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

import server.cli as cli
from server.common.agent_bridge import AgentRunMeta

runner = CliRunner()

EVAL_SCHEMA = "common/audit-result.schema.json"


def _runtime_ok() -> dict:
    return {"status": "ok"}


def _make_meta(request_id: str = "req-review-1") -> AgentRunMeta:
    return AgentRunMeta(
        request_id=request_id,
        conversation_id="conv-contract",
        claude_session_id="sess-contract",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=EVAL_SCHEMA,
        log_file="logs/service/contract.log",
        result_file="logs/service/contract-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def test_review_contract_commands_registered() -> None:
    assert runner.invoke(cli.app, ["review-contract", "--help"]).exit_code == 0
    assert runner.invoke(cli.app, ["review-contract-json", "--help"]).exit_code == 0


def test_review_contract_forwards_to_command_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    async def fake_full(command_name: str, *arguments: str, **opts) -> str:
        calls.append((command_name, arguments))
        return "REVIEW_TEXT_OK"

    monkeypatch.setattr(cli, "get_claude_runtime_report", _runtime_ok)
    monkeypatch.setattr(cli, "run_command_full", fake_full)

    result = runner.invoke(cli.app, ["review-contract", "data/contracts/x"])
    assert result.exit_code == 0, result.output
    assert "REVIEW_TEXT_OK" in result.output
    assert calls == [("review-contract", ("data/contracts/x",))]


def test_review_contract_json_persists_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"verdict": "approved", "extracted_data": {"contract": {"contract_meta": {}}}}
    persist_calls: list[dict] = []

    async def fake_json(command_name: str, *arguments: str, schema_name: str, **opts):
        assert command_name == "review-contract"
        assert schema_name == EVAL_SCHEMA
        return payload, _make_meta()

    def fake_persist(result_payload, *, request_id, tenant, source_path):
        persist_calls.append(
            {"payload": result_payload, "request_id": request_id, "source_path": source_path}
        )
        return "contract-xyz"

    monkeypatch.setattr(cli, "get_claude_runtime_report", _runtime_ok)
    monkeypatch.setattr(cli, "run_command_json", fake_json)
    monkeypatch.setattr(cli, "persist_contract_from_result", fake_persist)

    result = runner.invoke(cli.app, ["review-contract-json", "data/contracts/x"])
    assert result.exit_code == 0, result.output
    assert len(persist_calls) == 1
    assert persist_calls[0]["request_id"] == "req-review-1"
    assert persist_calls[0]["source_path"] == "data/contracts/x"
    assert persist_calls[0]["payload"] is payload
