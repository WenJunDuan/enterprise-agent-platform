"""Structured result archiving for JSON schema responses."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from server.platform.paths import (
    RESULT_BY_REQUEST_DIR,
    RESULT_INDEX_SHARD_DIR,
    build_result_archive_path,
    ensure_local_layout,
)
from server.platform.storage import (
    append_json_file,
    append_jsonl_record,
    describe_storage_target,
    load_json_file,
    load_jsonl_records_from_paths,
)

ensure_local_layout()

StructuredJSON = dict[str, Any] | list[Any]


@dataclass(slots=True)
class ResultRecord:
    request_id: str
    created_at: str
    conversation_id: str
    request_mode: str
    schema_name: str | None
    result_file: str
    tenant: str | None = None
    claude_session_id: str | None = None
    resume_session_id: str | None = None
    fork_from_session_id: str | None = None
    result_subtype: str | None = None
    claim_id: str | None = None
    verdict: str | None = None
    cost_usd: float = 0.0
    prompt_preview: str | None = None


class ResultStore(Protocol):
    """Persistence boundary for archived structured outputs."""

    def archive_result(self, record: ResultRecord, payload: dict[str, Any]) -> None: ...

    def list_records(
        self,
        tenant: str | None = None,
        conversation_id: str | None = None,
        claim_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def get_record_by_request_id(
        self,
        request_id: str,
        tenant: str | None = None,
    ) -> dict[str, Any] | None: ...

    def get_payload_by_request_id(
        self,
        request_id: str,
        tenant: str | None = None,
    ) -> dict[str, Any] | None: ...

    def describe(self) -> dict[str, Any]: ...


class JSONLResultStore:
    """File-backed structured result archive."""

    def __init__(self, shard_dir, archive_root) -> None:
        self.shard_dir = shard_dir
        self.archive_root = archive_root

    def archive_result(self, record: ResultRecord, payload: dict[str, Any]) -> None:
        append_json_file(self._result_path(record.result_file), payload)
        shard_path = self.shard_dir / f"results-{_month_key(record.created_at)}.jsonl"
        append_jsonl_record(shard_path, asdict(record))

    def list_records(
        self,
        tenant: str | None = None,
        conversation_id: str | None = None,
        claim_id: str | None = None,
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
            if claim_id and record.get("claim_id") != claim_id:
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

    def get_payload_by_request_id(
        self,
        request_id: str,
        tenant: str | None = None,
    ) -> dict[str, Any] | None:
        record = self.get_record_by_request_id(request_id=request_id, tenant=tenant)
        if record is None:
            return None
        payload = load_json_file(self._result_path(str(record["result_file"])))
        return payload

    def describe(self) -> dict[str, Any]:
        description = describe_storage_target(self.shard_dir)
        description["backend"] = "jsonl-sharded+json-files"
        description["archive_dir"] = str(self.archive_root)
        description["archive"] = describe_storage_target(self.archive_root)
        return description

    def _shard_paths(self) -> list:
        return [item for item in sorted(self.shard_dir.glob("*.jsonl")) if item.is_file()]

    def _result_path(self, stored_path: str):
        path = (self.archive_root.parent.parent / stored_path).resolve()
        root = self.archive_root.parent.parent.resolve()
        if root not in path.parents and path != root:
            raise ValueError(f"Result path escapes logs root: {stored_path}")
        return path


RESULT_STORE: ResultStore = JSONLResultStore(RESULT_INDEX_SHARD_DIR, RESULT_BY_REQUEST_DIR)


def archive_result_payload(
    *,
    request_id: str,
    tenant: str | None,
    conversation_id: str,
    claude_session_id: str | None,
    resume_session_id: str | None,
    fork_from_session_id: str | None,
    schema_name: str | None,
    request_mode: str,
    result_subtype: str | None,
    cost_usd: float,
    prompt_preview: str | None,
    response: StructuredJSON,
    created_at: str | None = None,
) -> ResultRecord:
    """Persist a structured result and return its metadata record."""
    created_at = created_at or datetime.now(timezone.utc).isoformat()
    result_file_path = build_result_archive_path(request_id=request_id, timestamp=created_at)
    claim_id = response.get("claim_id") if isinstance(response, dict) else None
    verdict = response.get("verdict") if isinstance(response, dict) else None
    payload = {
        "request_id": request_id,
        "tenant": tenant,
        "conversation_id": conversation_id,
        "claude_session_id": claude_session_id,
        "resume_session_id": resume_session_id,
        "fork_from_session_id": fork_from_session_id,
        "schema_name": schema_name,
        "request_mode": request_mode,
        "result_subtype": result_subtype,
        "cost_usd": cost_usd,
        "prompt_preview": prompt_preview,
        "created_at": created_at,
        "response": response,
    }
    record = ResultRecord(
        request_id=request_id,
        tenant=tenant,
        conversation_id=conversation_id,
        claude_session_id=claude_session_id,
        resume_session_id=resume_session_id,
        fork_from_session_id=fork_from_session_id,
        schema_name=schema_name,
        request_mode=request_mode,
        result_subtype=result_subtype,
        claim_id=str(claim_id) if claim_id else None,
        verdict=str(verdict) if verdict else None,
        cost_usd=cost_usd,
        prompt_preview=prompt_preview,
        created_at=created_at,
        result_file=str(result_file_path.relative_to(RESULT_BY_REQUEST_DIR.parent.parent)),
    )
    RESULT_STORE.archive_result(record, payload)
    return record


def list_result_records(
    tenant: str | None = None,
    conversation_id: str | None = None,
    claim_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return RESULT_STORE.list_records(
        tenant=tenant,
        conversation_id=conversation_id,
        claim_id=claim_id,
        limit=limit,
        offset=offset,
    )


def get_result_record_by_request_id(
    request_id: str,
    tenant: str | None = None,
) -> dict[str, Any] | None:
    return RESULT_STORE.get_record_by_request_id(request_id=request_id, tenant=tenant)


def get_result_payload_by_request_id(
    request_id: str,
    tenant: str | None = None,
) -> dict[str, Any] | None:
    return RESULT_STORE.get_payload_by_request_id(request_id=request_id, tenant=tenant)


def describe_result_store() -> dict[str, Any]:
    return RESULT_STORE.describe()


def _month_key(timestamp: str | None) -> str:
    if timestamp:
        return datetime.fromisoformat(timestamp).strftime("%Y-%m")
    return datetime.now(timezone.utc).strftime("%Y-%m")
