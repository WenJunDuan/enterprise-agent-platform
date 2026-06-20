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
    DATA_ROOT,
    LOGS_ROOT,
    PLATFORM_DB_FILE,
    PROJECT_ROOT,
    SESSION_EVENT_DIR,
    SUBMISSION_ROOT_DIR,
)
from server.platform.storage import describe_storage_target
from server.stores.audit_task_store import list_audit_tasks_admin
from server.stores.tender_task_store import list_tender_tasks_admin


def _resolve_case_path(case_path: str) -> Path:
    """相对 case_path 一律按 PROJECT_ROOT 解析（codex P1.4），不受 CWD 影响。"""
    candidate = Path(case_path)
    return (candidate if candidate.is_absolute() else PROJECT_ROOT / candidate).resolve()


def _all_upload_tasks() -> list[dict[str, Any]]:
    """audit + tender 两域的任务（都会 materialize submission 目录）。

    compare 任务（tender_compare_tasks）case_path 为占位 "-"，不建目录，故不纳入。
    """
    return [*list_audit_tasks_admin(), *list_tender_tasks_admin()]


def _known_case_dirs() -> set[str]:
    """所有任务登记的 case 目录（resolved），孤儿清理据此排除活跃目录。"""
    known: set[str] = set()
    for record in _all_upload_tasks():
        case_path = str(record.get("case_path") or "").strip()
        if case_path and case_path != "-":
            known.add(str(_resolve_case_path(case_path)))
    return known


def _iter_leaf_case_dirs(submission_root: Path) -> list[Path]:
    """枚举叶子 case 目录（域感知，避免误删 tenant/domain/project 中间目录）。

    新结构：``<tenant>/audit/<rid>``、``<tenant>/ocr/<rid>``、``<tenant>/tender/<project>/<rid>``。
    """
    leaves: list[Path] = []
    leaves.extend(submission_root.glob("*/audit/*"))
    leaves.extend(submission_root.glob("*/ocr/*"))
    leaves.extend(submission_root.glob("*/tender/*/*"))
    return [p for p in leaves if p.is_dir()]


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
        "data_root": describe_storage_target(DATA_ROOT),
        "platform_db": describe_storage_target(PLATFORM_DB_FILE),
        "session_events": describe_storage_target(SESSION_EVENT_DIR),
        "submissions": describe_storage_target(SUBMISSION_ROOT_DIR),
        "runtime_stdout": describe_storage_target(APP_SERVER_STDOUT_LOG),
        "runtime_stderr": describe_storage_target(APP_SERVER_STDERR_LOG),
    }


def cleanup_old_submission_directories(days: int, now: str | None = None) -> list[str]:
    """Remove expired submission directories for finished upload-mode tasks（audit + tender）。"""
    cutoff = _coerce_timestamp(now) - timedelta(days=days)
    removed: list[str] = []
    submission_root = SUBMISSION_ROOT_DIR.resolve()

    for record in _all_upload_tasks():
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
        if not case_path or case_path == "-":
            continue

        # codex P1.4：相对路径按 PROJECT_ROOT 解析（不受 CWD 影响）。
        resolved = _resolve_case_path(case_path)
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

    # codex P1.4：known 纳入 audit + tender 两域任务目录（PROJECT_ROOT 解析），
    # 否则活跃 tender 目录会被当 orphan 误删。
    known = _known_case_dirs()

    removed: list[str] = []
    # codex P1.4：递归到**叶子 case 目录**（域感知 glob），不再只扫第一层（租户级）——
    # 否则会误删整个 tenant/domain/project 中间目录，或漏删深层 leaf。
    for case_dir in _iter_leaf_case_dirs(submission_root):
        resolved = case_dir.resolve()
        if str(resolved) in known:
            continue  # 有 task 记录 → 交给 cleanup_old_submission_directories
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
