"""Project path layout for local storage and runtime assets.

Two roots, cleanly separated:
- ``logs/``  仅运行日志（operational）: app/error + 进程 runtime，均按年月日目录分区。
- ``data/``  全部业务数据: SQLite 统一单库 ``platform.sqlite3``（多表）+ 文件 blob
             （上传原件 / 会话 event 流 / 记忆产物）。
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
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

# 文件 blob（放不进表的大数据）。结果/复核 payload 已折叠进 platform.sqlite3 列，
# 只有会话原始 event 流（大、append-only）和上传原件仍落文件。
SUBMISSION_ROOT_DIR = DATA_ROOT / "submissions"  # 上传原件（ephemeral）
SESSION_EVENT_DIR = DATA_ROOT / "sessions" / "events"  # 会话原始 event 流

_SAFE_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

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
    ]:
        path.mkdir(parents=True, exist_ok=True)


def dated_log_dir(base_dir: Path, timestamp: str | None = None) -> Path:
    """Return the year/month/day partition under a log base directory.

    Runtime logs use ``logs/<area>/<YYYY>/<MM>/<DD>/...`` so every log area under
    ``logs/`` follows the same date partitioning scheme.
    """
    moment = _coerce_timestamp(timestamp)
    return base_dir / moment.strftime("%Y") / moment.strftime("%m") / moment.strftime("%d")


def dated_log_path(base_dir: Path, filename: str, timestamp: str | None = None) -> Path:
    """Return ``filename`` under the year/month/day partition for ``base_dir``."""
    return dated_log_dir(base_dir, timestamp) / filename


def latest_dated_log_path(base_dir: Path, filename: str) -> Path:
    """Return the newest dated log path, with compatibility for old layouts.

    Preferred layout:
    ``<base>/<YYYY>/<MM>/<DD>/<filename>``.

    Compatibility layouts:
    ``<base>/<YYYYMMDD>/<filename>`` and ``<base>/<filename>``.
    """
    if base_dir.exists():
        day_dirs = sorted(
            (
                d
                for d in base_dir.glob("[0-9][0-9][0-9][0-9]/[0-9][0-9]/[0-9][0-9]")
                if d.is_dir()
            ),
            reverse=True,
        )
        for day_dir in day_dirs:
            candidate = day_dir / filename
            if candidate.exists():
                return candidate

        legacy_day_dirs = sorted(
            (
                d
                for d in base_dir.iterdir()
                if d.is_dir() and len(d.name) == 8 and d.name.isdigit()
            ),
            reverse=True,
        )
        for day_dir in legacy_day_dirs:
            candidate = day_dir / filename
            if candidate.exists():
                return candidate
    return base_dir / filename


def build_session_event_log_path(
    session_id: str,
    request_id: str,
    timestamp: str | None = None,
    tenant: str | None = None,
) -> Path:
    """Build the raw event log path for one Claude session run."""
    moment = _coerce_timestamp(timestamp)
    event_dir = (
        SESSION_EVENT_DIR
        / _safe_tenant_segment(tenant)
        / moment.strftime("%Y")
        / moment.strftime("%m")
        / moment.strftime("%d")
    )
    filename = f"{moment.strftime('%H%M%S')}_{request_id}_{session_id[:8]}.jsonl"
    return event_dir / filename


def _safe_tenant_segment(tenant: str | None) -> str:
    """Return a path-safe tenant segment without allowing traversal via TENANT_KEYS."""
    value = (tenant or "unknown").strip()
    if _SAFE_PATH_SEGMENT.match(value):
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"tenant-{digest}"


def app_server_log_path(stderr: bool = False) -> Path:
    """托管 app-server 进程 stdout/stderr 日志（按年月日目录分区）：
    ``<APP_SERVER_DIR>/<YYYY>/<MM>/<DD>/<stdout|stderr>.log``。"""
    name = "stderr.log" if stderr else "stdout.log"
    return dated_log_path(APP_SERVER_DIR, name)


def latest_app_server_log_path(stderr: bool = False) -> Path:
    """读取用：最新日期目录下的 app-server 日志；兼容旧 ``YYYYMMDD`` 和平铺路径。"""
    name = "stderr.log" if stderr else "stdout.log"
    return latest_dated_log_path(APP_SERVER_DIR, name)


def _coerce_timestamp(timestamp: str | None) -> datetime:
    if timestamp:
        return datetime.fromisoformat(timestamp)
    return datetime.now(UTC)
