"""Project path layout for local storage and runtime assets.

Two roots, cleanly separated:
- ``logs/``  仅运行日志（operational）: app.log/error.log + 进程 runtime。
- ``data/``  全部业务数据: SQLite 统一单库 ``platform.sqlite3``（多表）+ 文件 blob
             （上传原件 / 会话 event 流 / 记忆产物）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_ROOT = PROJECT_ROOT / "logs"
DATA_ROOT = PROJECT_ROOT / "data"

# ── 运行日志（operational）— logs/ ─────────────────────────────────────────────
# app.log(INFO+) / error.log(WARN+)，由 logging_setup.configure_logging 写入。
APP_LOG_DIR = LOGS_ROOT / "app"
RUNTIME_LOG_DIR = LOGS_ROOT / "runtime"
APP_SERVER_DIR = RUNTIME_LOG_DIR / "app-server"
APP_SERVER_PID_FILE = APP_SERVER_DIR / "server.pid"
APP_SERVER_STATUS_FILE = APP_SERVER_DIR / "server.status.json"
APP_SERVER_STDOUT_LOG = APP_SERVER_DIR / "stdout.log"
APP_SERVER_STDERR_LOG = APP_SERVER_DIR / "stderr.log"

# ── 业务数据（data/）— SQLite 统一单库 + 文件 blob ────────────────────────────
# 所有结构化记录（results/requests/sessions/review_deltas/memory_assets/audit_tasks）
# 共用 platform.sqlite3：各 store 在同一库内建自己的表，单一备份/事务边界。
DB_DIR = DATA_ROOT / "db"
PLATFORM_DB_FILE = DB_DIR / "platform.sqlite3"

SERVICE_REQUEST_DB_FILE = PLATFORM_DB_FILE
SESSION_INDEX_DB_FILE = PLATFORM_DB_FILE
RESULT_INDEX_DB_FILE = PLATFORM_DB_FILE
REVIEW_DELTA_INDEX_DB_FILE = PLATFORM_DB_FILE
MEMORY_INDEX_DB_FILE = PLATFORM_DB_FILE

# 文件 blob（放不进表的大数据）。
SUBMISSION_ROOT_DIR = DATA_ROOT / "submissions"  # 上传原件（ephemeral）
SESSION_EVENT_DIR = DATA_ROOT / "sessions" / "events"  # 会话原始 event 流（大、append-only）
RESULT_BY_REQUEST_DIR = DATA_ROOT / "results" / "by-request"  # 结果归档（B1 折叠进库后弃用）
REVIEW_DELTA_BY_REQUEST_DIR = DATA_ROOT / "review-deltas" / "by-request"

# legacy shard 目录（早期 jsonl 后端遗留；保留供回填，后续清理）。
SERVICE_REQUEST_SHARD_DIR = DATA_ROOT / "service" / "requests"
SESSION_INDEX_SHARD_DIR = DATA_ROOT / "sessions" / "index"
RESULT_INDEX_SHARD_DIR = DATA_ROOT / "results" / "index"
AUDIT_TASK_DIR = DATA_ROOT / "service" / "audit-tasks"
AUDIT_TASK_FILE = AUDIT_TASK_DIR / "tasks.json"  # audit_tasks 上库后弃用（迁移读取）

# ── 迁移用：旧 logs/ 位置（一次性 migrate_storage 读取，迁完可删）─────────────
LEGACY_RESULT_DB_FILE = LOGS_ROOT / "results" / "index.sqlite3"
LEGACY_SESSION_DB_FILE = LOGS_ROOT / "sessions" / "index.sqlite3"
LEGACY_REQUEST_DB_FILE = LOGS_ROOT / "service" / "requests" / "index.sqlite3"
LEGACY_REVIEW_DB_FILE = LOGS_ROOT / "review-deltas" / "index.sqlite3"
LEGACY_MEMORY_DB_FILE = LOGS_ROOT / "knowledge" / "memory-index.sqlite3"
LEGACY_AUDIT_TASK_FILE = LOGS_ROOT / "service" / "audit-tasks" / "tasks.json"


def ensure_local_layout() -> None:
    """Create all local storage directories required by the serve layer."""
    for path in [
        # 运行日志
        LOGS_ROOT,
        APP_LOG_DIR,
        RUNTIME_LOG_DIR,
        APP_SERVER_DIR,
        # 业务数据
        DATA_ROOT,
        DB_DIR,
        SUBMISSION_ROOT_DIR,
        SESSION_EVENT_DIR,
        RESULT_BY_REQUEST_DIR,
        REVIEW_DELTA_BY_REQUEST_DIR,
        SERVICE_REQUEST_SHARD_DIR,
        SESSION_INDEX_SHARD_DIR,
        RESULT_INDEX_SHARD_DIR,
        AUDIT_TASK_DIR,
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
