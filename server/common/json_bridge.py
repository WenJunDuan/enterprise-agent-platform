"""JSON structured-output bridge: run_agent_json and its message-processing helpers.

Split from agent_bridge.py to keep each module ≤ 300 lines.
Import run_agent_json from server.core (the public facade).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    query,
)
from server.common.agent_bridge import (
    AgentRunMeta,
    _extract_system_session_id,
    _resolve_session_ids,
    build_options,
)
from server.audit.contract import (
    DEFAULT_OUTPUT_SCHEMA_NAME,
    JSONContractError,
    StructuredJSON,
    _extract_json_object,
    build_output_format,
    enrich_audit_decision,
    validate_structured_output_semantics,
)
from server.platform.logging_setup import logging_context
from server.common.session_logging import SessionLogger, _log_bridge_failure
from server.stores.result_store import archive_result_payload
from server.stores.session_store import (
    SessionRecord,
    append_session_record,
    new_conversation_id,
    utc_now,
)

logger = logging.getLogger(__name__)


def _apply_result_message_structured(
    message: ResultMessage,
    *,
    schema_name: str,
    final_structured_output: StructuredJSON | None,
    final_subtype: str,
) -> tuple[StructuredJSON | None, str | None]:
    """Try to extract validated structured output from a ResultMessage (structured mode).

    Returns (extracted_output_or_None, finished_at_or_None).
    Raises JSONContractError on contract violations.
    """
    structured_output = getattr(message, "structured_output", None)
    if structured_output is not None and final_structured_output is None:
        if not isinstance(structured_output, (dict, list)):
            raise JSONContractError("Claude returned a non-object structured output.")
        validate_structured_output_semantics(schema_name, structured_output)
        if schema_name == DEFAULT_OUTPUT_SCHEMA_NAME:
            structured_output = enrich_audit_decision(structured_output)
        return structured_output, utc_now()
    if final_subtype == "error_max_structured_output_retries":
        raise JSONContractError(
            f"Claude failed to satisfy structured output schema after retries: {schema_name}"
        )
    return None, None


def _apply_result_message_text(
    message: ResultMessage,
    *,
    schema_name: str,
    final_structured_output: StructuredJSON | None,
    text_accum: list[str],
) -> tuple[StructuredJSON | None, str | None]:
    """Try to extract validated structured output from a ResultMessage (text mode).

    Returns (extracted_output_or_None, finished_at_or_None).
    Raises JSONContractError on contract violations.
    """
    if final_structured_output is not None:
        return None, None
    # 文本模式：模型把 JSON 当文本输出，这里抽取 + 语义校验。
    raw_text = (getattr(message, "result", "") or "") or "".join(text_accum)
    parsed = _extract_json_object(raw_text)
    if parsed is not None:
        validate_structured_output_semantics(schema_name, parsed)
        if schema_name == DEFAULT_OUTPUT_SCHEMA_NAME:
            parsed = enrich_audit_decision(parsed)
        return parsed, utc_now()
    return None, None


async def run_agent_json(
    prompt: str,
    conversation_id: str | None = None,
    resume_session_id: str | None = None,
    fork_from_session_id: str | None = None,
    continue_recent: bool = False,
    schema_name: str = DEFAULT_OUTPUT_SCHEMA_NAME,
    structured: bool = True,
    request_id: str | None = None,
    tenant: str | None = None,
    **opts: Any,
) -> tuple[StructuredJSON, AgentRunMeta]:
    """Run Claude and return the parsed JSON object.

    structured=True 用 SDK 的 output_format 强制结构化输出（需模型支持 function
    calling）；structured=False 走文本模式：模型直接输出 JSON 文本，服务端自己抽取解析。
    """
    conversation_id = conversation_id or new_conversation_id()
    request_id = request_id or str(uuid.uuid4())
    started_at = utc_now()
    resolved_resume_session_id, current_session_id = _resolve_session_ids(
        conversation_id, resume_session_id, fork_from_session_id, continue_recent, tenant
    )
    session_logger = SessionLogger(current_session_id, request_id, prompt, started_at, tenant)
    output_opts = {"output_format": build_output_format(schema_name)} if structured else {}
    options = build_options(**output_opts, **opts)
    cli_stderr: list[str] = []
    options.stderr = cli_stderr.append

    with logging_context(request_id=request_id, tenant=tenant, session_id=current_session_id):
        if fork_from_session_id:
            options.resume = fork_from_session_id
            options.fork_session = True
        elif resolved_resume_session_id:
            options.resume = resolved_resume_session_id
        elif continue_recent:
            options.continue_conversation = True

        final_claude_session_id: str | None = None
        final_subtype = ""
        final_cost = 0.0
        final_status = "success"
        result_file: str | None = None
        finished_at: str | None = None
        final_structured_output: StructuredJSON | None = None
        text_accum: list[str] = []

        try:
            async for message in query(prompt=prompt, options=options):
                session_logger.log_message(message)

                if isinstance(message, SystemMessage):
                    final_claude_session_id = _extract_system_session_id(
                        message, final_claude_session_id
                    )
                    continue

                if isinstance(message, AssistantMessage):
                    for block in getattr(message, "content", []):
                        if isinstance(block, TextBlock):
                            text_accum.append(block.text)
                    continue

                if not isinstance(message, ResultMessage):
                    continue

                final_claude_session_id = (
                    getattr(message, "session_id", None) or final_claude_session_id
                )
                final_subtype = getattr(message, "subtype", "")
                final_cost = float(getattr(message, "total_cost_usd", 0.0) or 0.0)

                if structured:
                    extracted, ts = _apply_result_message_structured(
                        message,
                        schema_name=schema_name,
                        final_structured_output=final_structured_output,
                        final_subtype=final_subtype,
                    )
                else:
                    extracted, ts = _apply_result_message_text(
                        message,
                        schema_name=schema_name,
                        final_structured_output=final_structured_output,
                        text_accum=text_accum,
                    )

                if extracted is not None:
                    final_structured_output = extracted
                    finished_at = ts
                    continue

                if getattr(message, "is_error", False):
                    final_status = "error"
                    raise JSONContractError(message.result or "Claude returned an error result.")

            if final_structured_output is None:
                final_status = "error"
                if structured:
                    raise JSONContractError("Claude returned no structured output.")
                raise JSONContractError(
                    "文本模式下未能从模型输出中解析出 JSON 对象（模型可能没按要求只输出 JSON）。"
                )

            result_record = archive_result_payload(
                request_id=request_id,
                tenant=tenant,
                conversation_id=conversation_id,
                claude_session_id=final_claude_session_id,
                resume_session_id=resolved_resume_session_id,
                fork_from_session_id=fork_from_session_id,
                schema_name=schema_name,
                request_mode="structured" if structured else "text",
                result_subtype=final_subtype or None,
                cost_usd=final_cost,
                prompt_preview=prompt[:200],
                response=final_structured_output,
                created_at=finished_at or utc_now(),
            )
            result_file = result_record.result_file
            return final_structured_output, AgentRunMeta(
                request_id=request_id,
                conversation_id=conversation_id,
                claude_session_id=final_claude_session_id,
                resume_session_id=resolved_resume_session_id,
                fork_from_session_id=fork_from_session_id,
                schema_name=schema_name,
                log_file=str(session_logger.log_file),
                result_file=result_file,
                result_subtype=final_subtype or None,
                cost_usd=final_cost,
                finished_at=finished_at,
            )
        except Exception as exc:
            final_status = "error"
            _log_bridge_failure(
                exc,
                request_id=request_id,
                tenant=tenant,
                current_session_id=current_session_id,
                cli_stderr=cli_stderr,
                session_logger=session_logger,
            )
            raise
        finally:
            append_session_record(
                SessionRecord(
                    request_id=request_id,
                    conversation_id=conversation_id,
                    claude_session_id=final_claude_session_id,
                    resume_session_id=resolved_resume_session_id,
                    fork_from_session_id=fork_from_session_id,
                    schema_name=schema_name,
                    request_mode="structured" if structured else "text",
                    prompt_preview=prompt[:200],
                    log_file=str(session_logger.log_file),
                    status=final_status,
                    result_subtype=final_subtype or None,
                    cost_usd=final_cost,
                    started_at=started_at,
                    finished_at=finished_at or utc_now(),
                    tenant=tenant,
                    result_file=result_file,
                )
            )
