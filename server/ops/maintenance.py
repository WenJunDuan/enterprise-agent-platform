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
    MEMORY_INDEX_DB_FILE,
    LOGS_ROOT,
    PROJECT_ROOT,
    RESULT_INDEX_DB_FILE,
    RESULT_BY_REQUEST_DIR,
    SERVICE_REQUEST_DB_FILE,
    SERVICE_REQUEST_SHARD_DIR,
    SUBMISSION_ROOT_DIR,
    SESSION_EVENT_DIR,
    SESSION_INDEX_DB_FILE,
)
from server.platform.storage import describe_storage_target
from server.stores.audit_task_store import list_audit_tasks_admin


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
        "session_index": describe_storage_target(SESSION_INDEX_DB_FILE),
        "session_events": describe_storage_target(SESSION_EVENT_DIR),
        "request_audits": describe_storage_target(SERVICE_REQUEST_SHARD_DIR),
        "request_index": describe_storage_target(SERVICE_REQUEST_DB_FILE),
        "result_index": describe_storage_target(RESULT_INDEX_DB_FILE),
        "memory_index": describe_storage_target(MEMORY_INDEX_DB_FILE),
        "result_archives": describe_storage_target(RESULT_BY_REQUEST_DIR),
        "runtime_stdout": describe_storage_target(APP_SERVER_STDOUT_LOG),
        "runtime_stderr": describe_storage_target(APP_SERVER_STDERR_LOG),
    }


def cleanup_old_submission_directories(days: int, now: str | None = None) -> list[str]:
    """Remove expired submission directories for finished upload-mode tasks."""
    cutoff = _coerce_timestamp(now) - timedelta(days=days)
    removed: list[str] = []
    submission_root = SUBMISSION_ROOT_DIR.resolve()

    for record in list_audit_tasks_admin():
        if record.get("source_mode") != "upload":
            continue
        if record.get("status") not in {"completed", "failed"}:
            continue

        timestamp = record.get("finished_at") or record.get("updated_at")
        if not timestamp:
            continue
        if _coerce_timestamp(str(timestamp)) >= cutoff:
            continue

        case_path = str(record.get("case_path") or "").strip()
        if not case_path:
            continue

        path = Path(case_path)
        resolved = path.resolve()
        try:
            resolved.relative_to(submission_root)
        except ValueError:
            continue
        if not resolved.exists():
            continue

        shutil.rmtree(resolved)
        removed.append(str(resolved))

    return removed


def cleanup_orphan_submission_directories(days: int, now: str | None = None) -> list[str]:
    """Remove submission directories with no audit-task record, older than retention.

    OCR 端点（/ocr/extract、/ocr/fill）的上传目录**不登记为 audit task**，故不被
    cleanup_old_submission_directories 覆盖；它们 + 任何崩溃 / 超时残留的孤儿目录由本
    函数按目录 mtime 兜底清理，避免 data/submissions 无限堆积。mtime 在 retention 内
    （可能仍在处理）的目录保留。
    """
    cutoff = _coerce_timestamp(now) - timedelta(days=days)
    submission_root = SUBMISSION_ROOT_DIR.resolve()
    if not submission_root.exists():
        return []

    # 与 remove_submission_dir 一致：相对 case_path 对 PROJECT_ROOT 解析，不受 CWD 影响，
    # 否则从非项目目录跑 maintenance 时活跃任务目录会漏出 known、被孤儿清理误删。
    known = {
        str((Path(p) if Path(p).is_absolute() else PROJECT_ROOT / p).resolve())
        for record in list_audit_tasks_admin()
        if (p := str(record.get("case_path") or "").strip())
    }

    removed: list[str] = []
    for child in submission_root.iterdir():
        if not child.is_dir():
            continue
        resolved = child.resolve()
        if str(resolved) in known:
            continue  # 有 audit task 记录 → 交给 cleanup_old_submission_directories
        modified = datetime.fromtimestamp(resolved.stat().st_mtime, tz=timezone.utc)
        if modified >= cutoff:
            continue  # retention 内，可能仍在处理，保留
        shutil.rmtree(resolved, ignore_errors=True)
        removed.append(str(resolved))

    return removed


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
    removed_submission_dirs = cleanup_old_submission_directories(
        days=settings.submission_retention_days
    )
    removed_orphan_dirs = cleanup_orphan_submission_directories(
        days=settings.submission_retention_days
    )
    return {
        "rotated_runtime_logs": rotated,
        "archived_session_events": archived,
        "removed_submission_dirs": removed_submission_dirs,
        "removed_orphan_submission_dirs": removed_orphan_dirs,
        "storage_report": storage_report(),
    }


def _coerce_timestamp(value: str | None) -> datetime:
    if value:
        return datetime.fromisoformat(value)
    return datetime.now(timezone.utc)
