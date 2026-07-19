"""Live Claude CLI checks for the ocr-page Bash permission boundary.

These tests deliberately use the real SDK subprocess and gateway.  They skip
when the local environment cannot provide a real Claude CLI/gateway, but a
denied tool call that reaches the hook is never treated as an unavailable
environment.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from claude_agent_sdk import (
    ClaudeAgentOptions,
    CLIConnectionError,
    CLINotFoundError,
    HookMatcher,
    ProcessError,
    query,
)

from server.common.agent_bridge import build_options
from server.platform.config import validate_claude_runtime

pytestmark = pytest.mark.integration

_QUERY_TIMEOUT_SECONDS = 180


def _bash_prompt(command: str) -> str:
    """Strongly constrain the model to one observable Bash call."""
    return f"""You are running a security integration test.

You MUST call the Bash tool exactly once, and the command must be exactly:
{command}

Do not call Read, Glob, Grep, Write, Skill, Task, or any other tool. Do not
change the command, add quotes, retry it, or run any follow-up command. After
that one Bash call, stop immediately and return a short status message.
"""


def _runtime_unavailable() -> str | None:
    """Return a skip reason before spawning a CLI when no real runtime exists."""
    if (
        os.getenv("MODEL_BASE_URL") == "http://test-gateway:4000"
        and os.getenv("ANTHROPIC_API_KEY") == "test-fake-api-key-not-real"
    ):
        return "tests/conftest.py installed its fake gateway settings"
    errors = validate_claude_runtime()
    return "; ".join(errors) if errors else None


def _command_inputs(calls: list[dict[str, Any]]) -> list[str]:
    commands: list[str] = []
    for call in calls:
        tool_input = call.get("tool_input")
        if isinstance(tool_input, dict) and isinstance(tool_input.get("command"), str):
            commands.append(tool_input["command"])
    return commands


async def _run_query(
    prompt: str,
    options: ClaudeAgentOptions,
    calls: list[dict[str, Any]],
    marker: Path,
) -> None:
    """Run one real query, skipping only before any tool call on infra failure."""
    stderr: list[str] = []
    options.stderr = stderr.append
    try:
        async with asyncio.timeout(_QUERY_TIMEOUT_SECONDS):
            async for _message in query(prompt=prompt, options=options):
                pass
    except (CLIConnectionError, CLINotFoundError, ProcessError) as exc:
        if marker.exists():
            pytest.fail("P0: denied Bash query created the marker", pytrace=True)
        if not calls:
            pytest.skip(f"Claude CLI/gateway unavailable: {type(exc).__name__}")
        raise
    except TimeoutError as exc:
        if marker.exists():
            pytest.fail("P0: denied Bash query created the marker", pytrace=True)
        if not calls:
            pytest.skip("Claude CLI/gateway timed out before a Bash hook call")
        raise exc


def _assert_denied_call(calls: list[dict[str, Any]], command: str, marker: Path) -> None:
    """Require an actual target Bash call before asserting its denial."""
    if marker.exists():
        pytest.fail("P0: bypassPermissions allowed the denied Bash command")
    if not calls:
        pytest.skip("model did not emit Bash tool call")
    assert command in _command_inputs(calls), (
        "model emitted Bash, but not the requested exact command: "
        f"{_command_inputs(calls)!r}"
    )
    assert not marker.exists()


@pytest.mark.asyncio
async def test_bypass_permissions_pretooluse_deny_really_blocks_bash(tmp_path: Path):
    """Linchpin: a real deny hook must win even with bypassPermissions enabled."""
    if reason := _runtime_unavailable():
        pytest.skip(f"integration gateway unavailable: {reason}")

    marker = tmp_path / "bypass-denied-marker"
    command = f"touch {marker}"
    calls: list[dict[str, Any]] = []

    async def deny_bash(
        input_data: dict[str, Any], _tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        calls.append(input_data)
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "integration test denies every Bash call",
            }
        }

    options = ClaudeAgentOptions(
        tools=["Bash"],
        allowed_tools=["Bash"],
        permission_mode="bypassPermissions",
        hooks={"PreToolUse": [HookMatcher(matcher="Bash", hooks=[deny_bash])]},
        cwd=str(Path.cwd()),
        setting_sources=[],
        max_turns=3,
    )
    await _run_query(_bash_prompt(command), options, calls, marker)

    _assert_denied_call(calls, command, marker)
    print(f"Test A evidence: hook_calls={len(calls)}, marker_created={marker.exists()}")


@pytest.mark.asyncio
async def test_build_options_ocr_page_hook_denies_non_ocr_bash(tmp_path: Path):
    """Production-shaped options must deny a Bash command outside ocr-page."""
    if reason := _runtime_unavailable():
        pytest.skip(f"integration gateway unavailable: {reason}")

    case_root = tmp_path / "case"
    case_root.mkdir()
    marker = case_root / "production-denied-marker"
    command = f"touch {marker}"
    calls: list[dict[str, Any]] = []
    options = build_options(case_root=case_root, max_turns=3)

    assert options.hooks is not None
    matcher = options.hooks["PreToolUse"][0]
    assert matcher.matcher == "Bash"
    production_hook = matcher.hooks[0]

    async def recording_hook(
        input_data: dict[str, Any], tool_use_id: str | None, context: Any
    ) -> dict[str, Any]:
        calls.append(input_data)
        return await production_hook(input_data, tool_use_id, context)

    matcher.hooks = [recording_hook]
    await _run_query(_bash_prompt(command), options, calls, marker)

    _assert_denied_call(calls, command, marker)
    print(f"Test B evidence: hook_calls={len(calls)}, marker_created={marker.exists()}")
