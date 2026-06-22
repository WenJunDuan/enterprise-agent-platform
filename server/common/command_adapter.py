"""Shared adapters for invoking Claude-side slash commands from Python entrypoints."""

from __future__ import annotations

import json
from typing import Any, Callable

from server.common.agent_bridge import run_agent_full
from server.common.json_bridge import run_agent_json

def _serialize_command_argument(argument: str) -> str:
    normalized = str(argument).strip()
    if not normalized:
        return ""
    if any(char.isspace() for char in normalized) or any(char in normalized for char in {'"', "\\"}):
        return json.dumps(normalized, ensure_ascii=False)
    return normalized


def build_command_prompt(command_name: str, *arguments: str, context: str | None = None) -> str:
    """Render a Claude slash command invocation from a command name and raw arguments.

    ``context`` 非空时附在命令后（P4：注入确定性 OCR 底稿，模型无需再 Read 文件）。
    """
    suffix = " ".join(
        serialized
        for arg in arguments
        if (serialized := _serialize_command_argument(arg))
    )
    command = f"/{command_name} {suffix}".strip()
    return f"{command}\n\n{context}" if context else command


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
    schema_name: str | None,
    project_id: str | None = None,
    archive_to_results: bool = True,
    context: str | None = None,
    on_progress: Callable[[str], None] | None = None,
    evidence_source: str | None = None,
    **opts: Any,
):
    """Invoke a Claude slash command and return structured JSON output.

    ``project_id`` 显式透传到归档（tender 招标项目分组键）；显式参数而非 ``**opts``，
    避免被下游 ``build_options`` 当成 SDK 选项（codex P1.3）。
    ``archive_to_results=False`` 时结论不进 ``results`` 表（compare 用，codex P1.1）。
    ``context`` 附在命令后（P4：注入确定性 OCR 底稿，**喂模型**）。
    ``evidence_source`` 透传给 evidence-resolution 闸（R1，**喂校验**，不进 prompt）；显式命名
    参数而非 ``**opts``，避免漂进 ``build_options``（codex P2）。
    """
    return await run_agent_json(
        build_command_prompt(command_name, *arguments, context=context),
        schema_name=schema_name,
        project_id=project_id,
        archive_to_results=archive_to_results,
        on_progress=on_progress,
        evidence_source=evidence_source,
        **opts,
    )
