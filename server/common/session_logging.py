"""SDK event stream logger and bridge-error capture.

Split from server/core.py — contains SessionLogger, _log_cli_stderr, and
_log_bridge_failure.  No circular imports: this module only needs SDK message
types and platform helpers.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from server.platform.paths import build_session_event_log_path
from server.platform.storage import append_jsonl_record

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _log_cli_stderr(line: str) -> None:
    """SDK 把 bundled CLI 的 stderr 逐行回调到这里。

    CLI 崩溃 (exit 1) 时真正的错误只写在它自己的 stderr，默认会被 SDK 吞成
    "Check stderr output for details"。在这里落到日志，崩溃后即可定位真因
    （如网关响应畸形、流式解析异常），不必再手动复现。
    """
    text = line.rstrip()
    if text:
        logger.warning("claude_cli_stderr: %s", text)


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
            tenant=tenant,
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


def _log_bridge_failure(
    exc: Exception,
    *,
    request_id: str,
    tenant: str | None,
    current_session_id: str,
    cli_stderr: list[str],
    session_logger: SessionLogger,
) -> None:
    """记录 SDK 调用失败：结构化日志 + CLI stderr 尾部 + session 错误事件。

    CLI exit 非零时真正的错误只在它自己的 stderr，这里把尾部打出来帮助定位崩溃真因
    （如网关响应畸形、流式解析异常），不必再手动复现。
    """
    logger.exception(
        "claude_bridge_failed",
        extra={"request_id": request_id, "tenant": tenant, "session_id": current_session_id},
    )
    captured_stderr = "".join(cli_stderr).strip()
    if captured_stderr:
        # CLI exit 非零时把它的 stderr 全文打出来，否则只有一句无用的
        # "Check stderr output for details"。这是定位 CLI 崩溃的关键。
        logger.error("claude_cli_stderr | %s", captured_stderr[-6000:])
    session_logger.log_error(exc)
