"""Shared logging configuration and request-scoped context helpers."""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
import shutil
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path as _Path
from datetime import timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterator, Literal

from server.platform.config import _env_int
from server.platform.paths import APP_LOG_DIR

# 运行日志文件 appender 默认值（log4j2 RollingFile 等价）。环境变量可覆盖。
_DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 单文件 50MB 触发滚动
_DEFAULT_BACKUP_COUNT = 10  # 保留 10 个 gz 备份
_TRUTHY = {"1", "true", "yes", "on"}

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


# uvicorn access 行解析：取 exact path（去 query）+ status code，避免子串误伤（codex r4 P1）。
_ACCESS_LINE = re.compile(r'"\w+\s+(?P<path>[^\s?]+)[^"]*"\s+(?P<status>\d{3})')


class _AccessNoiseFilter(logging.Filter):
    """过滤 uvicorn access log 里的健康检查/轮询噪音（默认 GET /health），防 cloudflared 健康探测
    与前端轮询刷屏。env ACCESS_LOG_NOISE_PATHS（逗号分隔）可扩展。

    只过滤【exact path 命中 + 成功响应 2xx/3xx】的行：4xx/5xx 一律保留（便于排查），query 串里
    含噪音路径也不误伤（codex r4 P1：原子串匹配会吞掉 /tasks 的错误响应、误伤 ?redirect=/health）。
    """

    def __init__(self, noise_paths: tuple[str, ...]) -> None:
        super().__init__()
        self._noise = frozenset(noise_paths)

    def filter(self, record: logging.LogRecord) -> bool:
        match = _ACCESS_LINE.search(record.getMessage())
        if not match:
            return True  # 非标准 access 行（启动日志等），保留
        path, status = match.group("path"), int(match.group("status"))
        # exact 或带边界的前缀匹配（/tender/tasks 命中 /tender/tasks/{id} 轮询，但不误伤 /x?to=/health）。
        is_noise = any(path == p or path.startswith(p + "/") for p in self._noise)
        return not (is_noise and 200 <= status < 400)


def install_access_log_filter() -> None:
    """给 uvicorn.access logger 装噪音过滤。在 app lifespan startup 调用（uvicorn 此时已配好 access
    logger，filter 不被覆盖）。默认过滤 /health；env ACCESS_LOG_NOISE_PATHS 逗号分隔可扩展。"""
    raw = os.getenv("ACCESS_LOG_NOISE_PATHS", "/health")
    paths = tuple(p.strip() for p in raw.split(",") if p.strip())
    if paths:
        logging.getLogger("uvicorn.access").addFilter(_AccessNoiseFilter(paths))


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


def _gzip_rotator(source: str, dest: str) -> None:
    """Rollover rotator: gzip the closed log segment, then drop the plaintext source.

    `dest` already ends in `.gz` (see `_gzip_namer`), so the backup-shift logic in
    RotatingFileHandler.doRollover finds `app.log.{n}.gz` consistently.
    """
    with open(source, "rb") as src, gzip.open(dest, "wb") as gz:
        shutil.copyfileobj(src, gz)
    os.remove(source)


def _gzip_namer(name: str) -> str:
    return name + ".gz"


class _DateDirRotatingFileHandler(RotatingFileHandler):
    """按日期目录分区 + 日内按大小滚动 gzip 的文件 appender。

    写 ``<base_dir>/<YYYYMMDD>/<filename>``（如 logs/app/20260622/app.log）；跨天 emit 时自动切到新
    日期目录（便于按日滚动删除/归档整目录）。日内仍按 maxBytes 滚动并 gzip 旧段（app.log.1.gz 等留在
    当天目录内），避免单日文件无界增长。线程安全沿用父类 emit 的锁。
    """

    def __init__(
        self, base_dir: _Path, filename: str, *, maxBytes: int, backupCount: int
    ) -> None:
        self._base_dir = _Path(base_dir)
        self._log_name = filename
        self._current_date = self._today()
        dated = self._dated_path()
        dated.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(str(dated), maxBytes=maxBytes, backupCount=backupCount, encoding="utf-8")

    @staticmethod
    def _today() -> str:
        return datetime.now().strftime("%Y%m%d")

    def _dated_path(self) -> _Path:
        return self._base_dir / self._current_date / self._log_name

    def emit(self, record: logging.LogRecord) -> None:
        # 跨天 → 切到新日期目录（重开 stream 指向 <新日期>/<name>）。
        today = self._today()
        if today != self._current_date:
            self._current_date = today
            new_path = self._dated_path()
            new_path.parent.mkdir(parents=True, exist_ok=True)
            self.baseFilename = str(new_path.resolve())
            if self.stream:
                self.stream.close()
            self.stream = self._open()
        super().emit(record)


def _build_rotating_file_handler(
    base_dir: Path,
    filename: str,
    *,
    max_bytes: int,
    backup_count: int,
    context_filter: logging.Filter,
) -> RotatingFileHandler:
    """日期目录分区 + 日内 size-rolling + gzip 备份的文件 appender。

    写 ``<base_dir>/<YYYYMMDD>/<filename>``（按日滚动删除友好），日内 size 滚动 gzip（log4j2 RollingFile）。
    """
    handler = _DateDirRotatingFileHandler(
        base_dir, filename, maxBytes=max_bytes, backupCount=backup_count
    )
    handler.addFilter(context_filter)
    handler.setFormatter(_JSONFormatter())  # 文件始终 JSON：机器可解析
    handler.rotator = _gzip_rotator
    handler.namer = _gzip_namer
    return handler


def configure_logging(
    level: str,
    format: Literal["json", "kv"],
    *,
    to_files: bool | None = None,
    log_dir: Path | None = None,
    max_bytes: int | None = None,
    backup_count: int | None = None,
) -> None:
    """Configure root logging: a console appender plus optional leveled file appenders.

    The console appender is always installed (container stdout / dev). When file logging
    is enabled, two rolling file appenders are added under `log_dir` (default logs/app):
    `app.log` (everything at the configured level) and `error.log` (WARNING+ only),
    mirroring a log4j2 setup with a ThresholdFilter on the error appender.

    Args:
        level: Root log level name (e.g. "INFO").
        format: Console layout — "json" (structured) or "kv" (dev-friendly).
        to_files: Enable file appenders. Defaults to env LOG_TO_FILES (off ⇒ tests stay
            stdout-only and never write to disk).
        log_dir: Directory for the file appenders. Defaults to paths.APP_LOG_DIR.
        max_bytes: Rollover size threshold. Defaults to env LOG_MAX_BYTES or 50MB.
        backup_count: Number of gzipped backups to keep. Defaults to env LOG_BACKUP_COUNT or 10.
    """
    root = logging.getLogger()
    for existing in root.handlers[:]:
        existing.close()  # 关闭旧 handler，避免重配时泄漏文件句柄
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    context_filter = _ContextFilter()

    console = logging.StreamHandler(sys.stdout)
    console.addFilter(context_filter)
    console.setFormatter(_JSONFormatter() if format == "json" else _KVFormatter())
    root.addHandler(console)

    if to_files is None:
        to_files = os.getenv("LOG_TO_FILES", "").lower() in _TRUTHY
    if not to_files:
        return

    resolved_dir = Path(log_dir) if log_dir is not None else APP_LOG_DIR
    resolved_dir.mkdir(parents=True, exist_ok=True)
    resolved_max = max_bytes if max_bytes is not None else _env_int("LOG_MAX_BYTES", _DEFAULT_MAX_BYTES)
    resolved_backups = (
        backup_count if backup_count is not None else _env_int("LOG_BACKUP_COUNT", _DEFAULT_BACKUP_COUNT)
    )

    app_handler = _build_rotating_file_handler(
        resolved_dir,
        "app.log",
        max_bytes=resolved_max,
        backup_count=resolved_backups,
        context_filter=context_filter,
    )
    root.addHandler(app_handler)

    error_handler = _build_rotating_file_handler(
        resolved_dir,
        "error.log",
        max_bytes=resolved_max,
        backup_count=resolved_backups,
        context_filter=context_filter,
    )
    error_handler.setLevel(logging.WARNING)  # log4j2 ThresholdFilter: error.log 只收 WARN+
    root.addHandler(error_handler)


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
