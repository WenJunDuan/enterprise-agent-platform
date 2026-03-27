"""Unified SDK bridge and local persistence for Claude runs."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    query,
)
from server.platform.config import configure_claude_runtime_env
from server.platform.paths import PROJECT_ROOT, build_session_event_log_path, ensure_local_layout
from server.platform.storage import append_jsonl_record
from server.stores.result_store import archive_result_payload
from server.stores.session_store import (
    SessionRecord,
    append_session_record,
    new_conversation_id,
    resolve_latest_session_id,
    utc_now,
)

ensure_local_layout()
configure_claude_runtime_env()
CONTRACTS_DIR = PROJECT_ROOT / ".claude" / "contracts"
DEFAULT_OUTPUT_SCHEMA_NAME = "common/audit-result.schema.json"
INIT_RULES_REPORT_SCHEMA_NAME = "system/init-rules-report.schema.json"
StructuredJSON = dict[str, Any] | list[Any]


class JSONContractError(ValueError):
    """Raised when a Claude response does not satisfy the JSON contract."""


@dataclass(slots=True)
class AgentRunMeta:
    request_id: str
    conversation_id: str
    claude_session_id: str | None
    resume_session_id: str | None
    fork_from_session_id: str | None
    schema_name: str | None
    log_file: str
    result_file: str | None
    result_subtype: str | None
    cost_usd: float
    finished_at: str | None


def resolve_output_schema_path(schema_name: str) -> Path:
    """Resolve a schema path under `.claude/contracts` without allowing path escape."""
    schema_path = (CONTRACTS_DIR / schema_name).resolve()
    contracts_root = CONTRACTS_DIR.resolve()
    if contracts_root not in schema_path.parents:
        raise JSONContractError(f"Schema path escapes contracts root: {schema_name}")
    if not schema_path.is_file():
        raise JSONContractError(f"Structured output schema not found: {schema_name}")
    return schema_path


def load_output_schema(schema_name: str = DEFAULT_OUTPUT_SCHEMA_NAME) -> dict[str, Any]:
    """Load a JSON schema from `.claude/contracts`."""
    schema_path = resolve_output_schema_path(schema_name)
    try:
        loaded = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - exact error text is incidental
        raise JSONContractError(f"Structured output schema is invalid JSON: {schema_name}") from exc

    if not isinstance(loaded, dict):
        raise JSONContractError(f"Structured output schema must be a JSON object: {schema_name}")
    return loaded


def build_output_format(schema_name: str = DEFAULT_OUTPUT_SCHEMA_NAME) -> dict[str, Any]:
    """Build the SDK `output_format` payload for structured outputs."""
    return {"type": "json_schema", "schema": load_output_schema(schema_name)}


def build_options(**overrides: Any) -> ClaudeAgentOptions:
    """Create a shared SDK options object for all entrypoints."""
    defaults: dict[str, Any] = {
        "cwd": str(PROJECT_ROOT),
        "setting_sources": ["project"],
        "allowed_tools": ["Read", "Glob", "Grep", "Write", "Skill", "Task"],
        "permission_mode": "bypassPermissions",
        "max_turns": 80,
        "max_budget_usd": float(os.getenv("MAX_BUDGET_USD", "1.0")),
        "model": os.getenv("ANTHROPIC_MODEL", "sonnet"),
    }
    defaults.update(overrides)
    return ClaudeAgentOptions(**defaults)


class SessionLogger:
    """Persist the raw SDK event stream as JSONL."""

    def __init__(self, session_id: str, request_id: str, prompt: str, started_at: str) -> None:
        self.session_id = session_id
        self.request_id = request_id
        self.start_time = time.time()
        self.started_at = started_at
        self.log_file = build_session_event_log_path(
            session_id=session_id,
            request_id=request_id,
            timestamp=started_at,
        )
        self._write(
            {
                "event": "session_start",
                "session_id": session_id,
                "request_id": request_id,
                "prompt": prompt,
                "timestamp": started_at,
            }
        )

    def log_message(self, message: Any) -> dict[str, Any] | None:
        """Capture a stream message and return an event suitable for callers."""
        event: dict[str, Any] | None = None

        if isinstance(message, SystemMessage):
            self._write(
                {
                    "event": "system",
                    "subtype": getattr(message, "subtype", ""),
                    "session_id": getattr(message, "session_id", ""),
                    "timestamp": self._now(),
                }
            )
            session_id = getattr(message, "session_id", None)
            if session_id:
                event = {"type": "session", "session_id": session_id}

        elif isinstance(message, AssistantMessage):
            for block in getattr(message, "content", []):
                if isinstance(block, TextBlock):
                    event = {"type": "text", "content": block.text}
                    self._write(
                        {
                            "event": "assistant_text",
                            "content": block.text,
                            "timestamp": self._now(),
                        }
                    )
                elif isinstance(block, ToolUseBlock):
                    self._write(
                        {
                            "event": "tool_call",
                            "tool": block.name,
                            "input": str(block.input)[:1000],
                            "timestamp": self._now(),
                        }
                    )
                elif isinstance(block, ToolResultBlock):
                    self._write(
                        {
                            "event": "tool_result",
                            "content": str(getattr(block, "content", ""))[:1000],
                            "timestamp": self._now(),
                        }
                    )

        elif isinstance(message, ResultMessage):
            elapsed = time.time() - self.start_time
            event = {
                "type": "result",
                "content": message.result or "",
                "cost": float(getattr(message, "total_cost_usd", 0.0) or 0.0),
                "structured_output": getattr(message, "structured_output", None),
                "subtype": getattr(message, "subtype", ""),
            }
            self._write(
                {
                    "event": "session_end",
                    "subtype": getattr(message, "subtype", ""),
                    "duration_sec": round(elapsed, 2),
                    "cost_usd": event["cost"],
                    "structured_output": getattr(message, "structured_output", None),
                    "timestamp": self._now(),
                }
            )

        return event

    def _write(self, record: dict[str, Any]) -> None:
        append_jsonl_record(self.log_file, record)

    def log_error(self, error: Exception) -> None:
        """Capture internal bridge errors that happen outside Claude result blocks."""
        self._write(
            {
                "event": "bridge_error",
                "error_type": error.__class__.__name__,
                "message": str(error),
                "timestamp": self._now(),
            }
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()


async def run_agent(
    prompt: str,
    conversation_id: str | None = None,
    resume_session_id: str | None = None,
    fork_from_session_id: str | None = None,
    continue_recent: bool = False,
    request_id: str | None = None,
    tenant: str | None = None,
    **opts: Any,
) -> AsyncIterator[dict[str, Any]]:
    """Run the SDK query stream and forward structured events."""
    conversation_id = conversation_id or new_conversation_id()
    request_id = request_id or str(uuid.uuid4())
    started_at = utc_now()
    resolved_resume_session_id = resume_session_id or (
        resolve_latest_session_id(conversation_id) if not fork_from_session_id and not continue_recent else None
    )
    current_session_id = resolved_resume_session_id or fork_from_session_id or str(uuid.uuid4())
    logger = SessionLogger(current_session_id, request_id, prompt, started_at)
    options = build_options(**opts)

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

    try:
        async for message in query(prompt=prompt, options=options):
            event = logger.log_message(message)
            if isinstance(message, ResultMessage):
                final_claude_session_id = getattr(message, "session_id", None) or final_claude_session_id
                final_subtype = getattr(message, "subtype", "")
                final_cost = float(getattr(message, "total_cost_usd", 0.0) or 0.0)
                if getattr(message, "is_error", False):
                    final_status = "error"
            elif isinstance(message, SystemMessage):
                final_claude_session_id = getattr(message, "session_id", None) or final_claude_session_id

            if event:
                yield event
    except Exception as exc:
        final_status = "error"
        logger.log_error(exc)
        raise
    finally:
        append_session_record(
            SessionRecord(
                request_id=request_id,
                conversation_id=conversation_id,
                claude_session_id=final_claude_session_id,
                resume_session_id=resolved_resume_session_id,
                fork_from_session_id=fork_from_session_id,
                schema_name=str(opts.get("schema_name")) if opts.get("schema_name") else None,
                request_mode="stream",
                prompt_preview=prompt[:200],
                log_file=str(logger.log_file),
                status=final_status,
                result_subtype=final_subtype or None,
                cost_usd=final_cost,
                started_at=started_at,
                finished_at=utc_now(),
                tenant=tenant,
                result_file=None,
            )
        )


async def run_agent_full(prompt: str, **opts: Any) -> str:
    """Collect a full text response from the event stream."""
    chunks: list[str] = []
    final_result = ""
    async for event in run_agent(prompt, **opts):
        if event["type"] == "text":
            chunks.append(event["content"])
        elif event["type"] == "result":
            final_result = event["content"]
    return final_result or "\n".join(chunk for chunk in chunks if chunk)


async def run_agent_json(
    prompt: str,
    conversation_id: str | None = None,
    resume_session_id: str | None = None,
    fork_from_session_id: str | None = None,
    continue_recent: bool = False,
    schema_name: str = DEFAULT_OUTPUT_SCHEMA_NAME,
    request_id: str | None = None,
    tenant: str | None = None,
    **opts: Any,
) -> tuple[StructuredJSON, AgentRunMeta]:
    """Run Claude with SDK structured outputs and return the parsed object."""
    conversation_id = conversation_id or new_conversation_id()
    request_id = request_id or str(uuid.uuid4())
    started_at = utc_now()
    resolved_resume_session_id = resume_session_id or (
        resolve_latest_session_id(conversation_id) if not fork_from_session_id and not continue_recent else None
    )
    current_session_id = resolved_resume_session_id or fork_from_session_id or str(uuid.uuid4())
    logger = SessionLogger(current_session_id, request_id, prompt, started_at)
    options = build_options(output_format=build_output_format(schema_name), **opts)

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

    try:
        async for message in query(prompt=prompt, options=options):
            logger.log_message(message)

            if isinstance(message, SystemMessage):
                final_claude_session_id = getattr(message, "session_id", None) or final_claude_session_id
                continue

            if not isinstance(message, ResultMessage):
                continue

            final_claude_session_id = getattr(message, "session_id", None) or final_claude_session_id
            final_subtype = getattr(message, "subtype", "")
            final_cost = float(getattr(message, "total_cost_usd", 0.0) or 0.0)
            structured_output = getattr(message, "structured_output", None)

            if structured_output is not None:
                if not isinstance(structured_output, (dict, list)):
                    final_status = "error"
                    raise JSONContractError("Claude returned a non-object structured output.")
                finished_at = utc_now()
                result_record = archive_result_payload(
                    request_id=request_id,
                    tenant=tenant,
                    conversation_id=conversation_id,
                    claude_session_id=final_claude_session_id,
                    resume_session_id=resolved_resume_session_id,
                    fork_from_session_id=fork_from_session_id,
                    schema_name=schema_name,
                    request_mode="structured",
                    result_subtype=final_subtype or None,
                    cost_usd=final_cost,
                    prompt_preview=prompt[:200],
                    response=structured_output,
                    created_at=finished_at,
                )
                result_file = result_record.result_file
                return structured_output, AgentRunMeta(
                    request_id=request_id,
                    conversation_id=conversation_id,
                    claude_session_id=final_claude_session_id,
                    resume_session_id=resolved_resume_session_id,
                    fork_from_session_id=fork_from_session_id,
                    schema_name=schema_name,
                    log_file=str(logger.log_file),
                    result_file=result_file,
                    result_subtype=final_subtype or None,
                    cost_usd=final_cost,
                    finished_at=finished_at,
                )

            if final_subtype == "error_max_structured_output_retries":
                final_status = "error"
                raise JSONContractError(
                    f"Claude failed to satisfy structured output schema after retries: {schema_name}"
                )

            if getattr(message, "is_error", False):
                final_status = "error"
                raise JSONContractError(message.result or "Claude returned an error result.")

        final_status = "error"
        raise JSONContractError("Claude returned no structured output.")
    except Exception as exc:
        final_status = "error"
        logger.log_error(exc)
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
                request_mode="structured",
                prompt_preview=prompt[:200],
                log_file=str(logger.log_file),
                status=final_status,
                result_subtype=final_subtype or None,
                cost_usd=final_cost,
                started_at=started_at,
                finished_at=finished_at or utc_now(),
                tenant=tenant,
                result_file=result_file,
            )
        )
