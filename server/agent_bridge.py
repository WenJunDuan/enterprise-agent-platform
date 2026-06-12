"""SDK bridge: shared infrastructure, run_agent, and run_agent_full.

Provides ClaudeRuntimeError, AgentRunMeta, build_options, and the streaming
run_agent / run_agent_full entrypoints.  The JSON structured-output entrypoint
lives in server.json_bridge (to keep files ≤ 300 lines).

Import these symbols from server.core (the public facade) — do not import
from this module directly in application code.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ResultMessage,
    SystemMessage,
    query,
)
from server.platform.config import (
    configure_claude_runtime_env,
    get_claude_runtime_snapshot,
    offline_guard_error,
)
from server.platform.logging_setup import logging_context
from server.platform.paths import PROJECT_ROOT, ensure_local_layout
from server.session_logging import SessionLogger, _log_bridge_failure, _log_cli_stderr
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

logger = logging.getLogger(__name__)


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


def build_options(**overrides: Any) -> ClaudeAgentOptions:
    """Create a shared SDK options object for all entrypoints."""
    # 兜底进 env：这两项原本靠 setting_sources=["project"] 从 .claude/settings.json 加载；
    # 内联审核会改用 setting_sources=[] 精简系统提示，放进 env 才不会丢掉长超时与降噪。
    os.environ.setdefault("API_TIMEOUT_MS", "3000000")
    os.environ.setdefault("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")
    runtime = get_claude_runtime_snapshot()
    # 内网硬约束：base_url 为空或指向 api.anthropic.com 时直接拒绝运行，
    # 避免 CLI 去拨公网 anthropic、在物理隔离机上拖到 ConnectionRefused/超时。
    guard = offline_guard_error()
    if guard:
        raise ClaudeRuntimeError(guard)
    defaults: dict[str, Any] = {
        "cwd": str(PROJECT_ROOT),
        "setting_sources": ["project"],
        "allowed_tools": ["Read", "Glob", "Grep", "Write", "Skill", "Task"],
        "permission_mode": "bypassPermissions",
        "max_turns": int(os.getenv("AUDIT_MAX_TURNS", "30")),
        "max_budget_usd": float(os.getenv("MAX_BUDGET_USD", "1.0")),
        "model": runtime["anthropic_model"],
        # 捕获 bundled CLI 的 stderr，崩溃时把真因落日志（见 _log_cli_stderr）。
        "stderr": _log_cli_stderr,
    }
    defaults.update(overrides)
    return ClaudeAgentOptions(**defaults)


def _resolve_session_ids(
    conversation_id: str,
    resume_session_id: str | None,
    fork_from_session_id: str | None,
    continue_recent: bool,
    tenant: str | None,
) -> tuple[str | None, str]:
    """Resolve resume/fork/continue 三元逻辑，返回 (resolved_resume_session_id, current_session_id)。

    优先级（高到低）：
    1. 显式 resume_session_id — 直接用；
    2. 无 fork/continue_recent 时 — 按 tenant 查最新 session；
    3. 否则 — 不 resume（fork 或 continue 由调用方设 options）。
    current_session_id 取 resolved_resume / fork / 新 uuid。
    """
    resolved_resume = resume_session_id or (
        (
            resolve_latest_session_id(conversation_id, tenant=tenant)
            if tenant
            else resolve_latest_session_id_admin(conversation_id)
        )
        if not fork_from_session_id and not continue_recent
        else None
    )
    current = resolved_resume or fork_from_session_id or str(uuid.uuid4())
    return resolved_resume, current


def _extract_system_session_id(message: SystemMessage, current: str | None) -> str | None:
    """从 SystemMessage 里提取 claude session_id，不存在时返回 current 原值。"""
    return (
        getattr(message, "session_id", None)
        or getattr(getattr(message, "data", {}), "get", lambda *_: None)("session_id")
        or current
    )


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
    resolved_resume_session_id, current_session_id = _resolve_session_ids(
        conversation_id, resume_session_id, fork_from_session_id, continue_recent, tenant
    )
    session_logger = SessionLogger(current_session_id, request_id, prompt, started_at, tenant)
    options = build_options(**opts)
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
        saw_terminal_result = False
        saw_assistant_text = False

        try:
            async for message in query(prompt=prompt, options=options):
                event = session_logger.log_message(message)
                if isinstance(message, ResultMessage):
                    saw_terminal_result = True
                    final_claude_session_id = (
                        getattr(message, "session_id", None) or final_claude_session_id
                    )
                    final_subtype = getattr(message, "subtype", "")
                    final_cost = float(getattr(message, "total_cost_usd", 0.0) or 0.0)
                    if getattr(message, "is_error", False):
                        final_status = "error"
                elif isinstance(message, SystemMessage):
                    final_claude_session_id = _extract_system_session_id(
                        message, final_claude_session_id
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
