"""Project path layout for local storage and runtime assets."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_ROOT = PROJECT_ROOT / "logs"

SERVICE_LOG_DIR = LOGS_ROOT / "service"
SERVICE_REQUEST_SHARD_DIR = SERVICE_LOG_DIR / "requests"

SESSION_LOG_DIR = LOGS_ROOT / "sessions"
SESSION_INDEX_SHARD_DIR = SESSION_LOG_DIR / "index"
SESSION_EVENT_DIR = SESSION_LOG_DIR / "events"

RESULT_LOG_DIR = LOGS_ROOT / "results"
RESULT_INDEX_SHARD_DIR = RESULT_LOG_DIR / "index"
RESULT_BY_REQUEST_DIR = RESULT_LOG_DIR / "by-request"

RUNTIME_LOG_DIR = LOGS_ROOT / "runtime"
APP_SERVER_DIR = RUNTIME_LOG_DIR / "app-server"
APP_SERVER_PID_FILE = APP_SERVER_DIR / "server.pid"
APP_SERVER_STATUS_FILE = APP_SERVER_DIR / "server.status.json"
APP_SERVER_STDOUT_LOG = APP_SERVER_DIR / "stdout.log"
APP_SERVER_STDERR_LOG = APP_SERVER_DIR / "stderr.log"


def ensure_local_layout() -> None:
    """Create all local storage directories required by the serve layer."""
    for path in [
        LOGS_ROOT,
        SERVICE_LOG_DIR,
        SERVICE_REQUEST_SHARD_DIR,
        SESSION_LOG_DIR,
        SESSION_INDEX_SHARD_DIR,
        SESSION_EVENT_DIR,
        RESULT_LOG_DIR,
        RESULT_INDEX_SHARD_DIR,
        RESULT_BY_REQUEST_DIR,
        RUNTIME_LOG_DIR,
        APP_SERVER_DIR,
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


def _coerce_timestamp(timestamp: str | None) -> datetime:
    if timestamp:
        return datetime.fromisoformat(timestamp)
    return datetime.now(timezone.utc)
