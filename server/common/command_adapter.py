"""Shared adapters for invoking Claude-side slash commands from Python entrypoints."""

from __future__ import annotations

import json
from typing import Any

from server.common.agent_bridge import run_agent_full
from server.common.json_bridge import run_agent_json

def _serialize_command_argument(argument: str) -> str:
    normalized = str(argument).strip()
    if not normalized:
        return ""
    if any(char.isspace() for char in normalized) or any(char in normalized for char in {'"', "\\"}):
        return json.dumps(normalized, ensure_ascii=False)
    return normalized


def build_command_prompt(command_name: str, *arguments: str) -> str:
    """Render a Claude slash command invocation from a command name and raw arguments."""
    suffix = " ".join(
        serialized
        for arg in arguments
        if (serialized := _serialize_command_argument(arg))
    )
    return f"/{command_name} {suffix}".strip()


async def run_command_full(
    command_name: str,
    *arguments: str,
    **opts: Any,
) -> str:
    """Invoke a Claude slash command and return text output."""
    return await run_agent_full(build_command_prompt(command_name, *arguments), **opts)


async def run_command_json(
    command_name: str,
    *arguments: str,
    schema_name: str,
    **opts: Any,
):
    """Invoke a Claude slash command and return structured JSON output."""
    return await run_agent_json(
        build_command_prompt(command_name, *arguments),
        schema_name=schema_name,
        **opts,
    )
