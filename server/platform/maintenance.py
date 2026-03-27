"""Local maintenance helpers for logs and runtime artifacts."""

from __future__ import annotations

import gzip
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from server.platform.config import get_app_settings
from server.platform.paths import (
    APP_SERVER_STDERR_LOG,
    APP_SERVER_STDOUT_LOG,
    LOGS_ROOT,
    RESULT_BY_REQUEST_DIR,
    RESULT_INDEX_SHARD_DIR,
    SERVICE_REQUEST_SHARD_DIR,
    SESSION_EVENT_DIR,
    SESSION_INDEX_SHARD_DIR,
)
from server.platform.storage import describe_storage_target


def rotate_log_file(path: Path, *, max_bytes: int, backups: int) -> bool:
    """Rotate one plain-text log file in place when it grows too large."""
    if not path.exists() or path.stat().st_size <= max_bytes:
        return False

    oldest = path.with_name(f"{path.name}.{backups}")
    if oldest.exists():
        oldest.unlink()

    for index in range(backups - 1, 0, -1):
        source = path.with_name(f"{path.name}.{index}")
        target = path.with_name(f"{path.name}.{index + 1}")
        if source.exists():
            source.replace(target)

    path.replace(path.with_name(f"{path.name}.1"))
    path.touch()
    return True


def archive_old_session_event_logs(days: int) -> list[str]:
    """Compress raw session event logs older than the retention threshold."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    archived: list[str] = []
    for path in sorted(SESSION_EVENT_DIR.rglob("*.jsonl")):
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if modified_at >= cutoff:
            continue
        target = path.with_suffix(path.suffix + ".gz")
        with path.open("rb") as source, gzip.open(target, "wb") as dest:
            shutil.copyfileobj(source, dest)
        path.unlink()
        archived.append(str(target))
    return archived


def storage_report() -> dict[str, Any]:
    """Summarize the local storage layout for diagnostics."""
    return {
        "logs_root": describe_storage_target(LOGS_ROOT),
        "session_index": describe_storage_target(SESSION_INDEX_SHARD_DIR),
        "session_events": describe_storage_target(SESSION_EVENT_DIR),
        "request_audits": describe_storage_target(SERVICE_REQUEST_SHARD_DIR),
        "result_index": describe_storage_target(RESULT_INDEX_SHARD_DIR),
        "result_archives": describe_storage_target(RESULT_BY_REQUEST_DIR),
        "runtime_stdout": describe_storage_target(APP_SERVER_STDOUT_LOG),
        "runtime_stderr": describe_storage_target(APP_SERVER_STDERR_LOG),
    }


def run_maintenance() -> dict[str, Any]:
    """Run lightweight local maintenance tasks for long-running single-node usage."""
    settings = get_app_settings()
    rotated = {
        str(APP_SERVER_STDOUT_LOG): rotate_log_file(
            APP_SERVER_STDOUT_LOG,
            max_bytes=settings.runtime_log_max_bytes,
            backups=settings.runtime_log_backups,
        ),
        str(APP_SERVER_STDERR_LOG): rotate_log_file(
            APP_SERVER_STDERR_LOG,
            max_bytes=settings.runtime_log_max_bytes,
            backups=settings.runtime_log_backups,
        ),
    }
    archived = archive_old_session_event_logs(days=settings.session_archive_after_days)
    return {
        "rotated_runtime_logs": rotated,
        "archived_session_events": archived,
        "storage_report": storage_report(),
    }
