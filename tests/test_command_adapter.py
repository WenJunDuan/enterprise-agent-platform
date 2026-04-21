from __future__ import annotations

import asyncio

from server import command_adapter as command_adapter_module


def test_build_command_prompt_joins_audit_path() -> None:
    rendered = command_adapter_module.build_command_prompt("audit", "data/case1")

    assert rendered == "/audit data/case1"


def test_build_command_prompt_quotes_arguments_with_whitespace() -> None:
    rendered = command_adapter_module.build_command_prompt(
        "init-rules",
        "knowledge/external/expense policy.pdf",
        "expense",
    )

    assert rendered == '/init-rules "knowledge/external/expense policy.pdf" expense'


def test_run_command_json_uses_slash_command_prompt(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def fake_run_agent_json(prompt: str, *, schema_name: str, **_: object):
        captured["prompt"] = prompt
        captured["schema_name"] = schema_name
        return {"ok": True}, object()

    monkeypatch.setattr(command_adapter_module, "run_agent_json", fake_run_agent_json)

    asyncio.run(
        command_adapter_module.run_command_json(
            "audit",
            "data/case1",
            schema_name="common/audit-result.schema.json",
        )
    )

    assert captured == {
        "prompt": "/audit data/case1",
        "schema_name": "common/audit-result.schema.json",
    }


def test_run_command_full_uses_slash_command_prompt(monkeypatch) -> None:
    captured: dict[str, str] = {}

    async def fake_run_agent_full(prompt: str, **_: object) -> str:
        captured["prompt"] = prompt
        return "ok"

    monkeypatch.setattr(command_adapter_module, "run_agent_full", fake_run_agent_full)

    result = asyncio.run(
        command_adapter_module.run_command_full(
            "init-rules",
            "knowledge/external/expense policy.pdf",
            "expense",
        )
    )

    assert result == "ok"
    assert captured == {
        "prompt": '/init-rules "knowledge/external/expense policy.pdf" expense',
    }
