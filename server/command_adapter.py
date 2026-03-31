"""Shared adapters for invoking Claude-side slash commands from Python entrypoints."""

from __future__ import annotations

from typing import Any

from server.core import run_agent_full, run_agent_json


def build_command_prompt(command_name: str, *arguments: str) -> str:
    """Render a Claude slash command invocation from a command name and raw arguments."""
    suffix = " ".join(str(arg).strip() for arg in arguments if str(arg).strip())
    return f"/{command_name} {suffix}".strip()


def build_audit_prompt(path: str) -> str:
    """Build a stable direct prompt for audit flows without relying on slash-command execution."""
    normalized_path = str(path).strip()
    return (
        "你正在企业智能审核平台中执行一次报销审核。\n\n"
        f"输入路径：`{normalized_path}`。\n"
        "该路径可能是单个文件，也可能是一个目录。\n\n"
        "执行要求：\n"
        "1. 如果输入是目录，先枚举目录下文件，再综合申请单、报销单、发票、行程单、酒店单据等相关材料一起审核，不要只看第一个文件，也不要只读取目录本身。\n"
        "2. 如果输入是单个文件，直接读取该文件，并结合仓库中的本地规则、skills、agents 和制度文件完成审核。\n"
        "3. 审核时只使用当前仓库本地规则，不要使用训练记忆中的制度，不要编造缺失规则。\n"
        "4. 最终结果必须符合 `.claude/contracts/common/audit-result.schema.json`。\n"
        "5. 最终结果必须同时包含完整结构化字段以及 `result`、`conclusion`、`explanation`。\n"
        "6. `conclusion`、`explanation`、`reasons`、`evidence_chain` 必须使用中文。\n"
        "7. `manual_review` 时，`conclusion` 必须固定为 `待人工复核`，并在 `explanation` 中明确写出不能自动放行的原因、缺少什么材料，或哪条规则无法闭合。\n"
        "8. 优先直接返回完整审核结果给调用方，不要手工写入重复的 `logs/results/by-request/...` 文件。\n"
        "9. 只返回一个 JSON 对象，且该 JSON 对象必须直接符合 `.claude/contracts/common/audit-result.schema.json`。\n"
        "10. 不要输出 Markdown、表格、解释性前言、分节标题或任何 JSON 之外的文字。\n"
    )


async def run_command_full(
    command_name: str,
    *arguments: str,
    **opts: Any,
) -> str:
    """Invoke a Claude slash command and return text output."""
    if command_name == "audit" and arguments:
        return await run_agent_full(build_audit_prompt(arguments[0]), **opts)
    return await run_agent_full(build_command_prompt(command_name, *arguments), **opts)


async def run_command_json(
    command_name: str,
    *arguments: str,
    schema_name: str,
    **opts: Any,
):
    """Invoke a Claude slash command and return structured JSON output."""
    if command_name == "audit" and arguments:
        return await run_agent_json(
            build_audit_prompt(arguments[0]),
            schema_name=schema_name,
            **opts,
        )
    return await run_agent_json(
        build_command_prompt(command_name, *arguments),
        schema_name=schema_name,
        **opts,
    )
