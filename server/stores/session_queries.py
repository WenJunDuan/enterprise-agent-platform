"""Module-level session store singleton and delegating query functions."""

from __future__ import annotations

from typing import Any

from server.platform.paths import (
    SESSION_INDEX_DB_FILE,
    SESSION_INDEX_SHARD_DIR,
)
from server.stores.session_records import SessionRecord, SessionStore
from server.stores.session_sqlite_store import SQLiteSessionStore

SESSION_STORE: SessionStore = SQLiteSessionStore(SESSION_INDEX_DB_FILE, SESSION_INDEX_SHARD_DIR)


def append_session_record(record: SessionRecord) -> None:
    SESSION_STORE.append_record(record)


def load_session_records(
    *,
    tenant: str,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    return SESSION_STORE.load_records(conversation_id=conversation_id, tenant=tenant)


def get_session_record_by_request_id(
    request_id: str,
    tenant: str,
) -> dict[str, Any] | None:
    return SESSION_STORE.get_record_by_request_id(request_id=request_id, tenant=tenant)


def get_session_record_by_session_id(
    session_id: str,
    tenant: str,
) -> dict[str, Any] | None:
    return SESSION_STORE.get_record_by_session_id(session_id=session_id, tenant=tenant)


def resolve_latest_session_id(conversation_id: str, tenant: str) -> str | None:
    return SESSION_STORE.resolve_latest_session_id(conversation_id=conversation_id, tenant=tenant)


def list_logged_sessions(
    *,
    tenant: str,
    conversation_id: str | None = None,
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
    tenant: str,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return SESSION_STORE.list_conversation_summaries(tenant=tenant, limit=limit, offset=offset)


def list_known_session_ids(tenant: str) -> set[str]:
    return SESSION_STORE.list_known_session_ids(tenant=tenant)


def get_session_record_by_request_id_admin(request_id: str) -> dict[str, Any] | None:
    return SESSION_STORE.get_record_by_request_id_admin(request_id)


def get_session_record_by_session_id_admin(session_id: str) -> dict[str, Any] | None:
    return SESSION_STORE.get_record_by_session_id_admin(session_id)


def resolve_latest_session_id_admin(conversation_id: str) -> str | None:
    return SESSION_STORE.resolve_latest_session_id_admin(conversation_id)


def list_logged_sessions_admin(
    conversation_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return SESSION_STORE.list_logged_sessions_admin(
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
    )


def list_conversation_summaries_admin(limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    return SESSION_STORE.list_conversation_summaries_admin(limit=limit, offset=offset)


def list_known_session_ids_admin() -> set[str]:
    return SESSION_STORE.list_known_session_ids_admin()


def describe_session_store() -> dict[str, Any]:
    return SESSION_STORE.describe()
