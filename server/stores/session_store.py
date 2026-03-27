"""Application-level session index and transcript helpers."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from claude_agent_sdk import get_session_messages, list_sessions

from server.platform.paths import (
    PROJECT_ROOT,
    SESSION_INDEX_SHARD_DIR,
    ensure_local_layout,
)
from server.platform.storage import (
    append_jsonl_record,
    describe_storage_target,
    load_jsonl_records_from_paths,
)

ensure_local_layout()


@dataclass(slots=True)
class SessionRecord:
    request_id: str
    conversation_id: str
    claude_session_id: str | None
    resume_session_id: str | None
    fork_from_session_id: str | None
    schema_name: str | None
    request_mode: str
    prompt_preview: str
    log_file: str
    status: str
    result_subtype: str | None
    cost_usd: float
    started_at: str
    finished_at: str | None
    tenant: str | None = None
    result_file: str | None = None


class SessionStore(Protocol):
    """Persistence boundary for session metadata."""

    def append_record(self, record: SessionRecord) -> None: ...

    def load_records(
        self,
        conversation_id: str | None = None,
        tenant: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_record_by_request_id(
        self,
        request_id: str,
        tenant: str | None = None,
    ) -> dict[str, Any] | None: ...

    def get_record_by_session_id(
        self,
        session_id: str,
        tenant: str | None = None,
    ) -> dict[str, Any] | None: ...

    def resolve_latest_session_id(
        self,
        conversation_id: str,
        tenant: str | None = None,
    ) -> str | None: ...

    def list_logged_sessions(
        self,
        conversation_id: str | None = None,
        tenant: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def list_conversation_summaries(
        self,
        tenant: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def list_known_session_ids(self, tenant: str | None = None) -> set[str]: ...

    def describe(self) -> dict[str, Any]: ...


class JSONLSessionStore:
    """File-backed session repository used by the serve layer."""

    def __init__(self, shard_dir) -> None:
        self.shard_dir = shard_dir

    def append_record(self, record: SessionRecord) -> None:
        timestamp = record.finished_at or record.started_at
        shard_path = self.shard_dir / f"sessions-{_month_key(timestamp)}.jsonl"
        append_jsonl_record(shard_path, asdict(record))

    def load_records(
        self,
        conversation_id: str | None = None,
        tenant: str | None = None,
    ) -> list[dict[str, Any]]:
        records = load_jsonl_records_from_paths(self._shard_paths())
        filtered: list[dict[str, Any]] = []
        for record in records:
            if conversation_id and record.get("conversation_id") != conversation_id:
                continue
            if tenant is not None and record.get("tenant") != tenant:
                continue
            filtered.append(record)
        return filtered

    def get_record_by_request_id(
        self,
        request_id: str,
        tenant: str | None = None,
    ) -> dict[str, Any] | None:
        records = self.load_records(tenant=tenant)
        for record in reversed(records):
            if record.get("request_id") == request_id:
                return record
        return None

    def get_record_by_session_id(
        self,
        session_id: str,
        tenant: str | None = None,
    ) -> dict[str, Any] | None:
        records = self.load_records(tenant=tenant)
        for record in reversed(records):
            if record.get("claude_session_id") == session_id:
                return record
        return None

    def resolve_latest_session_id(
        self,
        conversation_id: str,
        tenant: str | None = None,
    ) -> str | None:
        records = self.load_records(conversation_id=conversation_id, tenant=tenant)
        for record in reversed(records):
            claude_session_id = record.get("claude_session_id")
            if claude_session_id:
                return str(claude_session_id)
        return None

    def list_logged_sessions(
        self,
        conversation_id: str | None = None,
        tenant: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        records = list(reversed(self.load_records(conversation_id=conversation_id, tenant=tenant)))
        return records[offset : offset + limit]

    def list_conversation_summaries(
        self,
        tenant: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        summaries: dict[str, dict[str, Any]] = {}
        for record in self.load_records(tenant=tenant):
            conversation_id = str(record["conversation_id"])
            summary = summaries.setdefault(
                conversation_id,
                {
                    "conversation_id": conversation_id,
                    "tenant": record.get("tenant"),
                    "request_count": 0,
                    "total_cost_usd": 0.0,
                    "latest_request_id": None,
                    "latest_claude_session_id": None,
                    "latest_status": None,
                    "latest_result_subtype": None,
                    "latest_schema_name": None,
                    "latest_prompt_preview": None,
                    "latest_result_file": None,
                    "first_started_at": record.get("started_at"),
                    "last_activity_at": record.get("finished_at") or record.get("started_at"),
                    "request_modes": set(),
                },
            )
            summary["request_count"] += 1
            summary["total_cost_usd"] = round(
                float(summary["total_cost_usd"]) + float(record.get("cost_usd", 0.0) or 0.0),
                6,
            )
            summary["latest_request_id"] = record.get("request_id")
            summary["latest_claude_session_id"] = record.get("claude_session_id")
            summary["latest_status"] = record.get("status")
            summary["latest_result_subtype"] = record.get("result_subtype")
            summary["latest_schema_name"] = record.get("schema_name")
            summary["latest_prompt_preview"] = record.get("prompt_preview")
            summary["latest_result_file"] = record.get("result_file")
            summary["last_activity_at"] = record.get("finished_at") or record.get("started_at")
            summary["request_modes"].add(record.get("request_mode"))

            started_at = record.get("started_at")
            if started_at and summary["first_started_at"] and started_at < summary["first_started_at"]:
                summary["first_started_at"] = started_at

        ordered = sorted(
            summaries.values(),
            key=lambda item: item.get("last_activity_at") or "",
            reverse=True,
        )
        sliced = ordered[offset : offset + limit]
        for item in sliced:
            item["request_modes"] = sorted(mode for mode in item["request_modes"] if mode)
        return sliced

    def list_known_session_ids(self, tenant: str | None = None) -> set[str]:
        session_ids: set[str] = set()
        for record in self.load_records(tenant=tenant):
            session_id = record.get("claude_session_id")
            if session_id:
                session_ids.add(str(session_id))
        return session_ids

    def describe(self) -> dict[str, Any]:
        description = describe_storage_target(self.shard_dir)
        description["backend"] = "jsonl-sharded"
        return description

    def _shard_paths(self) -> list:
        return [item for item in sorted(self.shard_dir.glob("*.jsonl")) if item.is_file()]


SESSION_STORE: SessionStore = JSONLSessionStore(SESSION_INDEX_SHARD_DIR)


def new_request_id() -> str:
    return str(uuid.uuid4())


def new_conversation_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_session_record(record: SessionRecord) -> None:
    SESSION_STORE.append_record(record)


def load_session_records(
    conversation_id: str | None = None,
    tenant: str | None = None,
) -> list[dict[str, Any]]:
    return SESSION_STORE.load_records(conversation_id=conversation_id, tenant=tenant)


def get_session_record_by_request_id(
    request_id: str,
    tenant: str | None = None,
) -> dict[str, Any] | None:
    return SESSION_STORE.get_record_by_request_id(request_id=request_id, tenant=tenant)


def get_session_record_by_session_id(
    session_id: str,
    tenant: str | None = None,
) -> dict[str, Any] | None:
    return SESSION_STORE.get_record_by_session_id(session_id=session_id, tenant=tenant)


def resolve_latest_session_id(conversation_id: str, tenant: str | None = None) -> str | None:
    return SESSION_STORE.resolve_latest_session_id(conversation_id=conversation_id, tenant=tenant)


def list_logged_sessions(
    conversation_id: str | None = None,
    tenant: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return SESSION_STORE.list_logged_sessions(
        conversation_id=conversation_id,
        tenant=tenant,
        limit=limit,
        offset=offset,
    )


def list_conversation_summaries(
    tenant: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return SESSION_STORE.list_conversation_summaries(tenant=tenant, limit=limit, offset=offset)


def list_known_session_ids(tenant: str | None = None) -> set[str]:
    return SESSION_STORE.list_known_session_ids(tenant=tenant)


def describe_session_store() -> dict[str, Any]:
    return SESSION_STORE.describe()


def list_sdk_session_summaries(
    limit: int = 20,
    session_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    probe_limit = max(limit * 10, 100) if session_ids is not None else limit
    sessions = list_sessions(directory=str(PROJECT_ROOT), limit=probe_limit, include_worktrees=True)
    summaries = [
        {
            "session_id": session.session_id,
            "summary": session.summary,
            "created_at": session.created_at,
            "last_modified": session.last_modified,
            "cwd": session.cwd,
            "git_branch": session.git_branch,
        }
        for session in sessions
        if session_ids is None or session.session_id in session_ids
    ]
    return summaries[:limit]


def get_sdk_session_transcript(
    session_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    messages = get_session_messages(
        session_id=session_id,
        directory=str(PROJECT_ROOT),
        limit=limit,
        offset=offset,
    )
    return [
        {
            "type": message.type,
            "uuid": message.uuid,
            "session_id": message.session_id,
            "message": message.message,
        }
        for message in messages
    ]


def _month_key(timestamp: str | None) -> str:
    if timestamp:
        return datetime.fromisoformat(timestamp).strftime("%Y-%m")
    return datetime.now(timezone.utc).strftime("%Y-%m")
