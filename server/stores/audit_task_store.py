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
        if "source_mode" not in merged and "mode" in merged:
            merged["source_mode"] = merged["mode"]
        task_record = AuditTaskRecord(**merged)
        payload[task_record.request_id] = asdict(task_record)
        append_json_file(AUDIT_TASK_FILE, payload)


def get_audit_task(request_id: str, tenant: str | None = None) -> dict[str, Any] | None:
    payload = _load_task_map()
    record = payload.get(request_id)
    if not isinstance(record, dict):
        return None
    if tenant is not None and record.get("tenant") != tenant:
        return None
    return record


def list_audit_tasks(tenant: str | None = None) -> list[dict[str, Any]]:
    payload = _load_task_map()
    records = [value for value in payload.values() if isinstance(value, dict)]
    if tenant is None:
        return records
    return [record for record in records if record.get("tenant") == tenant]


def recover_stale_audit_tasks(timeout_seconds: int, now: str | None = None) -> list[str]:
    current = _coerce_timestamp(now)
    recovered: list[str] = []
    for record in list_audit_tasks():
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
