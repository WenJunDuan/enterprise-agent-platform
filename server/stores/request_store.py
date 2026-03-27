"""Request-level audit logging for the serve layer."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from server.platform.paths import (
    SERVICE_REQUEST_SHARD_DIR,
    ensure_local_layout,
)
from server.platform.storage import (
    append_jsonl_record,
    describe_storage_target,
    load_jsonl_records_from_paths,
)

ensure_local_layout()


@dataclass(slots=True)
class RequestAuditRecord:
    request_id: str
    route: str
    method: str
    status_code: int
    status: str
    duration_ms: int
    created_at: str
    tenant: str | None = None
    conversation_id: str | None = None
    claude_session_id: str | None = None
    resume_session_id: str | None = None
    fork_from_session_id: str | None = None
    schema_name: str | None = None
    prompt_preview: str | None = None
    request_payload: dict[str, Any] | None = None
    session_log_file: str | None = None
    result_file: str | None = None
    error_detail: str | None = None


class RequestAuditStore(Protocol):
    """Persistence boundary for serve-level request audits."""

    def append_record(self, record: RequestAuditRecord) -> None: ...

    def list_records(
        self,
        tenant: str | None = None,
        conversation_id: str | None = None,
        claude_session_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def get_record_by_request_id(
        self,
        request_id: str,
        tenant: str | None = None,
    ) -> dict[str, Any] | None: ...

    def describe(self) -> dict[str, Any]: ...


class JSONLRequestAuditStore:
    """File-backed request audit repository used by the serve layer."""

    def __init__(self, shard_dir) -> None:
        self.shard_dir = shard_dir

    def append_record(self, record: RequestAuditRecord) -> None:
        shard_path = self.shard_dir / f"requests-{_month_key(record.created_at)}.jsonl"
        append_jsonl_record(shard_path, asdict(record))

    def list_records(
        self,
        tenant: str | None = None,
        conversation_id: str | None = None,
        claude_session_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        records = load_jsonl_records_from_paths(self._shard_paths())
        filtered: list[dict[str, Any]] = []
        for record in records:
            if tenant is not None and record.get("tenant") != tenant:
                continue
            if conversation_id and record.get("conversation_id") != conversation_id:
                continue
            if claude_session_id and record.get("claude_session_id") != claude_session_id:
                continue
            filtered.append(record)
        ordered = list(reversed(filtered))
        return ordered[offset : offset + limit]

    def get_record_by_request_id(
        self,
        request_id: str,
        tenant: str | None = None,
    ) -> dict[str, Any] | None:
        records = load_jsonl_records_from_paths(self._shard_paths())
        for record in reversed(records):
            if record.get("request_id") != request_id:
                continue
            if tenant is not None and record.get("tenant") != tenant:
                return None
            return record
        return None

    def describe(self) -> dict[str, Any]:
        description = describe_storage_target(self.shard_dir)
        description["backend"] = "jsonl-sharded"
        return description

    def _shard_paths(self) -> list:
        return [item for item in sorted(self.shard_dir.glob("*.jsonl")) if item.is_file()]


REQUEST_AUDIT_STORE: RequestAuditStore = JSONLRequestAuditStore(SERVICE_REQUEST_SHARD_DIR)


def new_request_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_request_audit(record: RequestAuditRecord) -> None:
    REQUEST_AUDIT_STORE.append_record(record)


def list_request_audits(
    tenant: str | None = None,
    conversation_id: str | None = None,
    claude_session_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return REQUEST_AUDIT_STORE.list_records(
        tenant=tenant,
        conversation_id=conversation_id,
        claude_session_id=claude_session_id,
        limit=limit,
        offset=offset,
    )


def get_request_audit_by_request_id(
    request_id: str,
    tenant: str | None = None,
) -> dict[str, Any] | None:
    return REQUEST_AUDIT_STORE.get_record_by_request_id(request_id=request_id, tenant=tenant)


def describe_request_store() -> dict[str, Any]:
    return REQUEST_AUDIT_STORE.describe()


def _month_key(timestamp: str | None) -> str:
    if timestamp:
        return datetime.fromisoformat(timestamp).strftime("%Y-%m")
    return datetime.now(timezone.utc).strftime("%Y-%m")
