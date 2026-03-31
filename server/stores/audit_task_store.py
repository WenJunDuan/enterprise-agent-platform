"""Task-status persistence for async audit submissions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from server.platform.paths import AUDIT_TASK_FILE, ensure_local_layout
from server.platform.storage import append_json_file, load_json_file

ensure_local_layout()


@dataclass(slots=True)
class AuditTaskRecord:
    request_id: str
    status: str
    mode: str
    case_path: str
    claim_id: str | None = None
    result_file: str | None = None
    error_detail: str | None = None
    updated_at: str = ""


def _load_task_map() -> dict[str, Any]:
    loaded = load_json_file(AUDIT_TASK_FILE)
    return loaded if loaded is not None else {}


def upsert_audit_task(record: dict[str, Any]) -> None:
    task_record = AuditTaskRecord(**record)
    payload = _load_task_map()
    payload[task_record.request_id] = asdict(task_record)
    append_json_file(AUDIT_TASK_FILE, payload)


def get_audit_task(request_id: str) -> dict[str, Any] | None:
    payload = _load_task_map()
    record = payload.get(request_id)
    return record if isinstance(record, dict) else None
