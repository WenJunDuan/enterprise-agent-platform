"""Project path layout for local storage and runtime assets."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_ROOT = PROJECT_ROOT / "logs"

# 运行日志（operational, log4j2 风格）：级别分流 app.log(INFO+) / error.log(WARN+)，
# 由 logging_setup.configure_logging 挂 RotatingFileHandler 写入。与下面的业务归档
# （service/sessions/results/…，按 request 分片的领域数据）是两类东西，刻意分目录。
APP_LOG_DIR = LOGS_ROOT / "app"

SERVICE_LOG_DIR = LOGS_ROOT / "service"
SERVICE_REQUEST_SHARD_DIR = SERVICE_LOG_DIR / "requests"
SERVICE_REQUEST_DB_FILE = SERVICE_REQUEST_SHARD_DIR / "index.sqlite3"
AUDIT_TASK_DIR = SERVICE_LOG_DIR / "audit-tasks"
AUDIT_TASK_FILE = AUDIT_TASK_DIR / "tasks.json"

SESSION_LOG_DIR = LOGS_ROOT / "sessions"
SESSION_INDEX_SHARD_DIR = SESSION_LOG_DIR / "index"
SESSION_INDEX_DB_FILE = SESSION_LOG_DIR / "index.sqlite3"
SESSION_EVENT_DIR = SESSION_LOG_DIR / "events"

RESULT_LOG_DIR = LOGS_ROOT / "results"
RESULT_INDEX_SHARD_DIR = RESULT_LOG_DIR / "index"
RESULT_INDEX_DB_FILE = RESULT_LOG_DIR / "index.sqlite3"
RESULT_BY_REQUEST_DIR = RESULT_LOG_DIR / "by-request"

REVIEW_LOG_DIR = LOGS_ROOT / "review-deltas"
REVIEW_DELTA_INDEX_DB_FILE = REVIEW_LOG_DIR / "index.sqlite3"
REVIEW_DELTA_BY_REQUEST_DIR = REVIEW_LOG_DIR / "by-request"

RUNTIME_LOG_DIR = LOGS_ROOT / "runtime"
APP_SERVER_DIR = RUNTIME_LOG_DIR / "app-server"
APP_SERVER_PID_FILE = APP_SERVER_DIR / "server.pid"
APP_SERVER_STATUS_FILE = APP_SERVER_DIR / "server.status.json"
APP_SERVER_STDOUT_LOG = APP_SERVER_DIR / "stdout.log"
APP_SERVER_STDERR_LOG = APP_SERVER_DIR / "stderr.log"

KNOWLEDGE_LOG_DIR = LOGS_ROOT / "knowledge"
MEMORY_INDEX_DB_FILE = KNOWLEDGE_LOG_DIR / "memory-index.sqlite3"

SUBMISSION_ROOT_DIR = PROJECT_ROOT / "data" / "submissions"


def ensure_local_layout() -> None:
    """Create all local storage directories required by the serve layer."""
    for path in [
        LOGS_ROOT,
        APP_LOG_DIR,
        SERVICE_LOG_DIR,
        SERVICE_REQUEST_SHARD_DIR,
        AUDIT_TASK_DIR,
        SESSION_LOG_DIR,
        SESSION_INDEX_SHARD_DIR,
        SESSION_EVENT_DIR,
        RESULT_LOG_DIR,
        RESULT_INDEX_SHARD_DIR,
        RESULT_BY_REQUEST_DIR,
        REVIEW_LOG_DIR,
        REVIEW_DELTA_BY_REQUEST_DIR,
        RUNTIME_LOG_DIR,
        APP_SERVER_DIR,
        KNOWLEDGE_LOG_DIR,
        SUBMISSION_ROOT_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def build_session_event_log_path(
    session_id: str,
    request_id: str,
    timestamp: str | None = None,
) -> Path:
    """Build the raw event log path for one Claude session run."""
    moment = _coerce_timestamp(timestamp)
    event_dir = SESSION_EVENT_DIR / moment.strftime("%Y") / moment.strftime("%m") / moment.strftime("%d")
    filename = f"{moment.strftime('%H%M%S')}_{request_id}_{session_id[:8]}.jsonl"
    return event_dir / filename


def build_result_archive_path(request_id: str, timestamp: str | None = None) -> Path:
    """Build the structured result archive path for one request."""
    moment = _coerce_timestamp(timestamp)
    archive_dir = RESULT_BY_REQUEST_DIR / moment.strftime("%Y") / moment.strftime("%m") / moment.strftime("%d")
    return archive_dir / f"{request_id}.json"


def build_review_delta_archive_path(request_id: str, timestamp: str | None = None) -> Path:
    """Build the review-delta archive path for one request."""
    moment = _coerce_timestamp(timestamp)
    archive_dir = REVIEW_DELTA_BY_REQUEST_DIR / moment.strftime("%Y") / moment.strftime("%m") / moment.strftime("%d")
    return archive_dir / f"{request_id}.json"


def _coerce_timestamp(timestamp: str | None) -> datetime:
    if timestamp:
        return datetime.fromisoformat(timestamp)
    return datetime.now(timezone.utc)
