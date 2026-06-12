"""Session dataclass, store Protocol, and primitive helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


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
        *,
        tenant: str,
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_record_by_request_id(
        self,
        request_id: str,
        tenant: str,
    ) -> dict[str, Any] | None: ...

    def get_record_by_session_id(
        self,
        session_id: str,
        tenant: str,
    ) -> dict[str, Any] | None: ...

    def resolve_latest_session_id(
        self,
        conversation_id: str,
        tenant: str,
    ) -> str | None: ...

    def list_logged_sessions(
        self,
        *,
        tenant: str,
        conversation_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def list_conversation_summaries(
        self,
        tenant: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def list_known_session_ids(self, tenant: str) -> set[str]: ...

    # DANGEROUS: bypasses tenant isolation — admin-only.
    def get_record_by_request_id_admin(self, request_id: str) -> dict[str, Any] | None: ...

    # DANGEROUS: bypasses tenant isolation — admin-only.
    def get_record_by_session_id_admin(self, session_id: str) -> dict[str, Any] | None: ...

    # DANGEROUS: bypasses tenant isolation — admin-only.
    def resolve_latest_session_id_admin(self, conversation_id: str) -> str | None: ...

    # DANGEROUS: bypasses tenant isolation — admin-only.
    def list_logged_sessions_admin(
        self,
        conversation_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    # DANGEROUS: bypasses tenant isolation — admin-only.
    def list_conversation_summaries_admin(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    # DANGEROUS: bypasses tenant isolation — admin-only.
    def list_known_session_ids_admin(self) -> set[str]: ...

    def describe(self) -> dict[str, Any]: ...


def new_request_id() -> str:
    return str(uuid.uuid4())


def new_conversation_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _month_key(timestamp: str | None) -> str:
    if timestamp:
        return datetime.fromisoformat(timestamp).strftime("%Y-%m")
    return datetime.now(timezone.utc).strftime("%Y-%m")
