"""Unified SDK bridge and local persistence for Claude runs."""

from __future__ import annotations

import json
import logging
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
from server.platform.config import configure_claude_runtime_env, get_claude_runtime_snapshot
from server.platform.logging_setup import logging_context
from server.platform.paths import PROJECT_ROOT, build_session_event_log_path, ensure_local_layout
from server.platform.storage import append_jsonl_record
from server.stores.result_store import archive_result_payload
from server.stores.session_store import (
    SessionRecord,
    append_session_record,
    new_conversation_id,
    resolve_latest_session_id,
    resolve_latest_session_id_admin,
    utc_now,
)

ensure_local_layout()
configure_claude_runtime_env()
CONTRACTS_DIR = PROJECT_ROOT / ".claude" / "contracts"
DEFAULT_OUTPUT_SCHEMA_NAME = "common/audit-result.schema.json"
INIT_RULES_REPORT_SCHEMA_NAME = "system/init-rules-report.schema.json"
StructuredJSON = dict[str, Any] | list[Any]
logger = logging.getLogger(__name__)

# `verdict` is the single source of truth; `result` (bool) and `conclusion` (label)
# are derived from it server-side so the model never has to keep three fields in sync.
AUDIT_DECISION_DERIVATION: dict[str, tuple[bool, str]] = {
    "approved": (True, "合规"),
    "rejected": (False, "不合规"),
    "manual_review": (False, "待人工复核"),
}


def enrich_audit_decision(structured_output: StructuredJSON) -> StructuredJSON:
    """Inject `result`/`conclusion` derived from `verdict` for backward-compatible payloads."""
    if isinstance(structured_output, dict):
        derived = AUDIT_DECISION_DERIVATION.get(str(structured_output.get("verdict")))
        if derived is not None:
            structured_output["result"], structured_output["conclusion"] = derived
    return structured_output


class JSONContractError(ValueError):
    """Raised when a Claude response does not satisfy the JSON contract."""


class ClaudeRuntimeError(RuntimeError):
    """Raised when a Claude request never produces a terminal result."""


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


def validate_structured_output_semantics(
    schema_name: str,
    structured_output: StructuredJSON,
) -> None:
    """Apply semantic validation rules that JSON Schema alone cannot express."""
    if schema_name == DEFAULT_OUTPUT_SCHEMA_NAME:
        if not isinstance(structured_output, dict):
            raise JSONContractError("audit result structured output must be a JSON object.")

        verdict = structured_output.get("verdict")
        if verdict not in AUDIT_DECISION_DERIVATION:
            raise JSONContractError("audit result returned an unknown verdict.")

        if not str(structured_output.get("explanation") or "").strip():
            raise JSONContractError("audit result field `explanation` must be non-empty.")

        if verdict == "manual_review":
            reason = structured_output.get("manual_review_reason")
            valid_reasons = {
                "missing_approval",
                "rule_gap",
                "data_conflict",
                "insufficient_evidence",
                "budget_exceeded",
                "invoice_invalid",
                "pre_approval_mismatch",
            }
            if reason not in valid_reasons:
                raise JSONContractError(
                    "audit result with verdict=manual_review must include a valid manual_review_reason."
                )

        dimensions = structured_output.get("risk_dimensions")
        if dimensions is not None:
            if not isinstance(dimensions, list):
                raise JSONContractError("audit result field `risk_dimensions` must be a list.")
            valid_dim_names = {"invoice", "amount", "approval", "budget", "anomaly"}
            for dim in dimensions:
                if not isinstance(dim, dict):
                    raise JSONContractError("each risk dimension must be an object.")
                name = dim.get("name")
                score = dim.get("score")
                if name not in valid_dim_names:
                    raise JSONContractError(
                        f"risk dimension name `{name}` is not in the allowed set."
                    )
                if not isinstance(score, int) or isinstance(score, bool) or score < 0 or score > 10:
                    raise JSONContractError(
                        "risk dimension score must be an integer between 0 and 10."
                    )

        return

    if schema_name != INIT_RULES_REPORT_SCHEMA_NAME:
        return

    if not isinstance(structured_output, dict):
        raise JSONContractError("init-rules structured output must be a JSON object.")

    source_path = str(structured_output.get("source_path") or "").strip()
    if not source_path:
        raise JSONContractError("init-rules result must include a non-empty source_path.")

    status = structured_output.get("status")
    if status != "initialized":
        return

    written_files = structured_output.get("written_files")
    categories = structured_output.get("categories")
    extracted_rule_count = structured_output.get("extracted_rule_count")

    if not isinstance(written_files, list) or not written_files:
        raise JSONContractError(
            "init-rules cannot return status=initialized with empty written_files."
        )
    if not isinstance(categories, list) or not categories:
        raise JSONContractError("init-rules cannot return status=initialized with empty categories.")
    if not isinstance(extracted_rule_count, int) or extracted_rule_count <= 0:
        raise JSONContractError(
            "init-rules cannot return status=initialized with extracted_rule_count <= 0."
        )


def build_options(**overrides: Any) -> ClaudeAgentOptions:
    """Create a shared SDK options object for all entrypoints."""
    runtime = get_claude_runtime_snapshot()
    defaults: dict[str, Any] = {
        "cwd": str(PROJECT_ROOT),
        "setting_sources": ["project"],
        "allowed_tools": ["Read", "Glob", "Grep", "Write", "Skill", "Task"],
        "permission_mode": "bypassPermissions",
        "max_turns": int(os.getenv("AUDIT_MAX_TURNS", "30")),
        "max_budget_usd": float(os.getenv("MAX_BUDGET_USD", "1.0")),
        "model": runtime["anthropic_model"],
    }
    defaults.update(overrides)
    return ClaudeAgentOptions(**defaults)


class SessionLogger:
    """Persist the raw SDK event stream as JSONL."""

    def __init__(
        self,
        session_id: str,
        request_id: str,
        prompt: str,
        started_at: str,
        tenant: str | None,
    ) -> None:
        self.session_id = session_id
        self.request_id = request_id
        self.tenant = tenant
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
                "tenant": tenant,
                "prompt": prompt,
                "timestamp": started_at,
            }
        )

    def log_message(self, message: Any) -> dict[str, Any] | None:
        """Capture a stream message and return an event suitable for callers."""
        event: dict[str, Any] | None = None

        if isinstance(message, SystemMessage):
            session_id = getattr(message, "session_id", None) or getattr(
                getattr(message, "data", {}),
                "get",
                lambda *_: None,
            )("session_id")
            if session_id:
                self.session_id = str(session_id)
            self._write(
                {
                    "event": "system",
                    "subtype": getattr(message, "subtype", ""),
                    "session_id": self.session_id,
                    "timestamp": self._now(),
                }
            )
            if session_id:
                event = {"type": "session", "session_id": session_id}

        elif isinstance(message, AssistantMessage):
            message_session_id = getattr(message, "session_id", None)
            if message_session_id:
                self.session_id = str(message_session_id)
            for block in getattr(message, "content", []):
                if isinstance(block, TextBlock):
                    event = {"type": "text", "content": block.text}
                    self._write(
                        {
                            "event": "assistant_text",
                            "content": block.text,
                            "session_id": self.session_id,
                            "timestamp": self._now(),
                        }
                    )
                elif isinstance(block, ToolUseBlock):
                    self._write(
                        {
                            "event": "tool_call",
                            "tool": block.name,
                            "input": str(block.input)[:1000],
                            "session_id": self.session_id,
                            "timestamp": self._now(),
                        }
                    )
                elif isinstance(block, ToolResultBlock):
                    self._write(
                        {
                            "event": "tool_result",
                            "content": str(getattr(block, "content", ""))[:1000],
                            "session_id": self.session_id,
                            "timestamp": self._now(),
                        }
                    )

        elif isinstance(message, ResultMessage):
            if getattr(message, "session_id", None):
                self.session_id = str(message.session_id)
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
                    "is_error": bool(getattr(message, "is_error", False)),
                    "result": (message.result or "")[:2000],
                    "duration_sec": round(elapsed, 2),
                    "cost_usd": event["cost"],
                    "structured_output": getattr(message, "structured_output", None),
                    "session_id": self.session_id,
                    "timestamp": self._now(),
                }
            )

        return event

    def _write(self, record: dict[str, Any]) -> None:
        enriched = {
            "request_id": self.request_id,
            "tenant": self.tenant,
            "session_id": self.session_id,
            **record,
        }
        append_jsonl_record(self.log_file, enriched)
        if record.get("event") in {"session_start", "session_end"}:
            logger.info(
                "session_event",
                extra={
                    "event_name": record.get("event"),
                    "request_id": self.request_id,
                    "tenant": self.tenant,
                    "session_id": self.session_id,
                    "result_subtype": record.get("subtype"),
                },
            )

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
        (
            resolve_latest_session_id(conversation_id, tenant=tenant)
            if tenant
            else resolve_latest_session_id_admin(conversation_id)
        )
        if not fork_from_session_id and not continue_recent
        else None
    )
    current_session_id = resolved_resume_session_id or fork_from_session_id or str(uuid.uuid4())
    session_logger = SessionLogger(current_session_id, request_id, prompt, started_at, tenant)
    options = build_options(**opts)

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
        saw_terminal_result = False
        saw_assistant_text = False

        try:
            async for message in query(prompt=prompt, options=options):
                event = session_logger.log_message(message)
                if isinstance(message, ResultMessage):
                    saw_terminal_result = True
                    final_claude_session_id = getattr(message, "session_id", None) or final_claude_session_id
                    final_subtype = getattr(message, "subtype", "")
                    final_cost = float(getattr(message, "total_cost_usd", 0.0) or 0.0)
                    if getattr(message, "is_error", False):
                        final_status = "error"
                elif isinstance(message, SystemMessage):
                    final_claude_session_id = (
                        getattr(message, "session_id", None)
                        or getattr(getattr(message, "data", {}), "get", lambda *_: None)("session_id")
                        or final_claude_session_id
                    )

                if event:
                    if event["type"] == "text":
                        saw_assistant_text = True
                    yield event

            if not saw_terminal_result and not saw_assistant_text:
                final_status = "error"
                raise ClaudeRuntimeError(
                    "Claude request ended without any assistant result. "
                    "Recent session logs show only API retries; check gateway base URL, auth, or model id."
                )
        except Exception as exc:
            final_status = "error"
            logger.exception(
                "claude_bridge_failed",
                extra={"request_id": request_id, "tenant": tenant, "session_id": current_session_id},
            )
            session_logger.log_error(exc)
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
                    log_file=str(session_logger.log_file),
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
        (
            resolve_latest_session_id(conversation_id, tenant=tenant)
            if tenant
            else resolve_latest_session_id_admin(conversation_id)
        )
        if not fork_from_session_id and not continue_recent
        else None
    )
    current_session_id = resolved_resume_session_id or fork_from_session_id or str(uuid.uuid4())
    session_logger = SessionLogger(current_session_id, request_id, prompt, started_at, tenant)
    options = build_options(output_format=build_output_format(schema_name), **opts)

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

        try:
            async for message in query(prompt=prompt, options=options):
                session_logger.log_message(message)

                if isinstance(message, SystemMessage):
                    final_claude_session_id = (
                        getattr(message, "session_id", None)
                        or getattr(getattr(message, "data", {}), "get", lambda *_: None)("session_id")
                        or final_claude_session_id
                    )
                    continue

                if not isinstance(message, ResultMessage):
                    continue

                final_claude_session_id = getattr(message, "session_id", None) or final_claude_session_id
                final_subtype = getattr(message, "subtype", "")
                final_cost = float(getattr(message, "total_cost_usd", 0.0) or 0.0)
                structured_output = getattr(message, "structured_output", None)

                if structured_output is not None and final_structured_output is None:
                    if not isinstance(structured_output, (dict, list)):
                        final_status = "error"
                        raise JSONContractError("Claude returned a non-object structured output.")
                    validate_structured_output_semantics(schema_name, structured_output)
                    if schema_name == DEFAULT_OUTPUT_SCHEMA_NAME:
                        structured_output = enrich_audit_decision(structured_output)
                    final_structured_output = structured_output
                    finished_at = utc_now()
                    continue

                if final_subtype == "error_max_structured_output_retries":
                    final_status = "error"
                    raise JSONContractError(
                        f"Claude failed to satisfy structured output schema after retries: {schema_name}"
                    )

                if getattr(message, "is_error", False):
                    final_status = "error"
                    raise JSONContractError(message.result or "Claude returned an error result.")

            if final_structured_output is None:
                final_status = "error"
                raise JSONContractError("Claude returned no structured output.")

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
            logger.exception(
                "claude_bridge_failed",
                extra={"request_id": request_id, "tenant": tenant, "session_id": current_session_id},
            )
            session_logger.log_error(exc)
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
