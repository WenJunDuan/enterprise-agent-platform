"""Request-level audit logging for the serve layer."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Protocol

from server.platform.paths import SERVICE_REQUEST_DB_FILE, ensure_local_layout
from server.platform.sqlite_store import connect_sqlite, describe_sqlite_target, row_to_dict

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
    session_id: str | None = None
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
        tenant: str,
        conversation_id: str | None = None,
        claude_session_id: str | None = None,
        route: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def get_record_by_request_id(
        self,
        request_id: str,
        tenant: str,
    ) -> dict[str, Any] | None: ...

    def describe(self) -> dict[str, Any]: ...


class SQLiteRequestAuditStore:
    """SQLite-backed request audit index (the requests table in platform.sqlite3)."""

    COLUMNS: ClassVar[list[str]] = [
        "request_id",
        "route",
        "method",
        "status_code",
        "status",
        "duration_ms",
        "created_at",
        "tenant",
        "conversation_id",
        "claude_session_id",
        "session_id",
        "resume_session_id",
        "fork_from_session_id",
        "schema_name",
        "prompt_preview",
        "request_payload",
        "session_log_file",
        "result_file",
        "error_detail",
    ]

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._initialize_schema()

    def append_record(self, record: RequestAuditRecord) -> None:
        with connect_sqlite(self.db_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO requests (
                    request_id, route, method, status_code, status, duration_ms, created_at,
                    tenant, conversation_id, claude_session_id, session_id, resume_session_id,
                    fork_from_session_id, schema_name, prompt_preview, request_payload,
                    session_log_file, result_file, error_detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._record_values(asdict(record)),
            )

    def list_records(
        self,
        tenant: str,
        conversation_id: str | None = None,
        claude_session_id: str | None = None,
        route: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM requests WHERE tenant = ?"
        params: list[Any] = [tenant]
        if conversation_id:
            query += " AND conversation_id = ?"
            params.append(conversation_id)
        if claude_session_id:
            query += " AND claude_session_id = ?"
            params.append(claude_session_id)
        if route:
            query += " AND route = ?"
            params.append(route)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC, request_id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_record_by_request_id(
        self,
        request_id: str,
        tenant: str,
    ) -> dict[str, Any] | None:
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM requests WHERE request_id = ? AND tenant = ?",
                (request_id, tenant),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_records_admin(
        self,
        conversation_id: str | None = None,
        claude_session_id: str | None = None,
        route: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM requests"
        clauses: list[str] = []
        params: list[Any] = []
        if conversation_id:
            clauses.append("conversation_id = ?")
            params.append(conversation_id)
        if claude_session_id:
            clauses.append("claude_session_id = ?")
            params.append(claude_session_id)
        if route:
            clauses.append("route = ?")
            params.append(route)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC, request_id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_record_by_request_id_admin(self, request_id: str) -> dict[str, Any] | None:
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def describe(self) -> dict[str, Any]:
        return describe_sqlite_target(self.db_path, backend="sqlite")

    def _initialize_schema(self) -> None:
        with connect_sqlite(self.db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    route TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    tenant TEXT,
                    conversation_id TEXT,
                    claude_session_id TEXT,
                    session_id TEXT,
                    resume_session_id TEXT,
                    fork_from_session_id TEXT,
                    schema_name TEXT,
                    prompt_preview TEXT,
                    request_payload TEXT,
                    session_log_file TEXT,
                    result_file TEXT,
                    error_detail TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_requests_tenant_created
                    ON requests (tenant, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_requests_conversation
                    ON requests (tenant, conversation_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_requests_claude_session
                    ON requests (tenant, claude_session_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_requests_route_status
                    ON requests (tenant, route, status, created_at DESC);
                """
            )

    def _record_values(self, record: dict[str, Any]) -> tuple[Any, ...]:
        normalized = dict(record)
        request_payload = normalized.get("request_payload")
        normalized["request_payload"] = (
            json.dumps(request_payload, ensure_ascii=False)
            if request_payload is not None
            else None
        )
        return tuple(normalized.get(column) for column in self.COLUMNS)

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        loaded = row_to_dict(row) or {}
        if loaded.get("request_payload"):
            loaded["request_payload"] = json.loads(str(loaded["request_payload"]))
        else:
            loaded["request_payload"] = None
        return loaded


REQUEST_AUDIT_STORE: RequestAuditStore = SQLiteRequestAuditStore(SERVICE_REQUEST_DB_FILE)


def new_request_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def append_request_audit(record: RequestAuditRecord) -> None:
    REQUEST_AUDIT_STORE.append_record(record)


def list_request_audits_admin(
    conversation_id: str | None = None,
    claude_session_id: str | None = None,
    route: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return REQUEST_AUDIT_STORE.list_records_admin(
        conversation_id=conversation_id,
        claude_session_id=claude_session_id,
        route=route,
        status=status,
        limit=limit,
        offset=offset,
    )


def get_request_audit_by_request_id_admin(request_id: str) -> dict[str, Any] | None:
    return REQUEST_AUDIT_STORE.get_record_by_request_id_admin(request_id)


def describe_request_store() -> dict[str, Any]:
    return REQUEST_AUDIT_STORE.describe()
