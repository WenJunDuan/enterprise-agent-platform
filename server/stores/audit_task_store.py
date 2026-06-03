"""Task-status persistence for async audit submissions."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from server.platform.paths import AUDIT_TASK_FILE, ensure_local_layout
from server.platform.storage import append_json_file, load_json_file

try:  # pragma: no cover - Windows fallback is environment-dependent
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback is environment-dependent
    fcntl = None

ensure_local_layout()


@dataclass(slots=True)
class AuditTaskRecord:
    request_id: str
    tenant: str | None
    session_id: str | None
    status: str
    mode: str
    source_mode: str
    case_path: str
    claim_id: str | None = None
    result_file: str | None = None
    error_detail: str | None = None
    progress_message: str | None = None
    submitted_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str = ""


def _load_task_map() -> dict[str, Any]:
    loaded = load_json_file(AUDIT_TASK_FILE)
    return loaded if loaded is not None else {}


def upsert_audit_task(record: dict[str, Any]) -> None:
    with _task_file_lock():
        payload = _load_task_map()
        existing = payload.get(record["request_id"], {})
        merged = {**existing, **record}
        if "tenant" not in merged:
            merged["tenant"] = None
        if "session_id" not in merged:
            merged["session_id"] = None
        if "source_mode" not in merged and "mode" in merged:
            merged["source_mode"] = merged["mode"]
        task_record = AuditTaskRecord(**merged)
        payload[task_record.request_id] = asdict(task_record)
        append_json_file(AUDIT_TASK_FILE, payload)


def delete_audit_task(request_id: str, tenant: str) -> bool:
    """Remove a task owned by `tenant`. Returns True when a record was deleted."""
    with _task_file_lock():
        payload = _load_task_map()
        record = payload.get(request_id)
        if not isinstance(record, dict) or record.get("tenant") != tenant:
            return False
        del payload[request_id]
        append_json_file(AUDIT_TASK_FILE, payload)
        return True


def get_audit_task(request_id: str, tenant: str) -> dict[str, Any] | None:
    payload = _load_task_map()
    record = payload.get(request_id)
    if not isinstance(record, dict):
        return None
    if record.get("tenant") != tenant:
        return None
    return record


def list_audit_tasks(
    tenant: str,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    payload = _load_task_map()
    records = [v for v in payload.values() if isinstance(v, dict) and v.get("tenant") == tenant]
    if status:
        records = [r for r in records if r.get("status") == status]
    records.sort(key=lambda r: str(r.get("submitted_at") or r.get("updated_at") or ""), reverse=True)
    return records[offset : offset + limit]


def get_audit_task_admin(request_id: str) -> dict[str, Any] | None:
    payload = _load_task_map()
    record = payload.get(request_id)
    return record if isinstance(record, dict) else None


def list_audit_tasks_admin() -> list[dict[str, Any]]:
    payload = _load_task_map()
    return [value for value in payload.values() if isinstance(value, dict)]


def recover_stale_audit_tasks(timeout_seconds: int, now: str | None = None) -> list[str]:
    current = _coerce_timestamp(now)
    recovered: list[str] = []
    for record in list_audit_tasks_admin():
        if record.get("status") != "running":
            continue
        started_at = record.get("started_at") or record.get("updated_at")
        if not started_at:
            continue
        started_moment = _coerce_timestamp(str(started_at))
        if (current - started_moment).total_seconds() <= timeout_seconds:
            continue
        recovered.append(str(record["request_id"]))
        upsert_audit_task(
            {
                "request_id": str(record["request_id"]),
                "status": "failed",
                "error_detail": "任务超时或服务重启后自动终止",
                "progress_message": "任务超时或服务重启后自动终止",
                "finished_at": current.isoformat(),
                "updated_at": current.isoformat(),
            }
        )
    return recovered


def _coerce_timestamp(value: str | None) -> datetime:
    if value:
        return datetime.fromisoformat(value)
    return datetime.now(timezone.utc)


def _task_lock_path() -> Any:
    return AUDIT_TASK_FILE.with_suffix(AUDIT_TASK_FILE.suffix + ".lock")


@contextmanager
def _task_file_lock():
    lock_path = _task_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
