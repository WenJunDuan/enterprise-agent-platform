"""Shared logging configuration and request-scoped context helpers."""

from __future__ import annotations

import json
import logging
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Iterator, Literal

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
_correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_tenant_var: ContextVar[str | None] = ContextVar("tenant", default=None)
_session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)


def current_request_id() -> str | None:
    return _request_id_var.get()


def current_correlation_id() -> str | None:
    return _correlation_id_var.get()


def current_tenant() -> str | None:
    return _tenant_var.get()


def current_session_id() -> str | None:
    return _session_id_var.get()


@contextmanager
def logging_context(
    *,
    request_id: str | None = None,
    correlation_id: str | None = None,
    tenant: str | None = None,
    session_id: str | None = None,
) -> Iterator[None]:
    resets: list[tuple[ContextVar[str | None], Any]] = []
    if request_id is not None:
        resets.append((_request_id_var, _request_id_var.set(request_id)))
    if correlation_id is not None:
        resets.append((_correlation_id_var, _correlation_id_var.set(correlation_id)))
    if tenant is not None:
        resets.append((_tenant_var, _tenant_var.set(tenant)))
    if session_id is not None:
        resets.append((_session_id_var, _session_id_var.set(session_id)))

    try:
        yield
    finally:
        for context_var, token in reversed(resets):
            context_var.reset(token)


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = current_request_id()
        if not hasattr(record, "correlation_id"):
            record.correlation_id = current_correlation_id()
        if not hasattr(record, "tenant"):
            record.tenant = current_tenant()
        if not hasattr(record, "session_id"):
            record.session_id = current_session_id()
        return True


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "correlation_id": getattr(record, "correlation_id", None),
            "tenant": getattr(record, "tenant", None),
            "session_id": getattr(record, "session_id", None),
        }
        for key, value in _extra_fields(record).items():
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class _KVFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        parts = [
            f"timestamp={datetime.now(timezone.utc).isoformat()}",
            f"level={record.levelname}",
            f"logger={record.name}",
            f"message={json.dumps(record.getMessage(), ensure_ascii=False)}",
        ]
        for key in ["request_id", "correlation_id", "tenant", "session_id"]:
            value = getattr(record, key, None)
            if value:
                parts.append(f"{key}={value}")
        for key, value in _extra_fields(record).items():
            parts.append(f"{key}={json.dumps(value, ensure_ascii=False)}")
        if record.exc_info:
            parts.append(f"exception={json.dumps(self.formatException(record.exc_info), ensure_ascii=False)}")
        return " ".join(parts)


def configure_logging(level: str, format: Literal["json", "kv"]) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_ContextFilter())
    handler.setFormatter(_JSONFormatter() if format == "json" else _KVFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    standard = {
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "request_id",
        "correlation_id",
        "tenant",
        "session_id",
    }
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in standard and not key.startswith("_")
    }
