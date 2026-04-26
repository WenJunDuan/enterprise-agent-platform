"""Structured result archiving for JSON schema responses."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from server.platform.paths import (
    RESULT_BY_REQUEST_DIR,
    RESULT_INDEX_DB_FILE,
    RESULT_INDEX_SHARD_DIR,
    build_result_archive_path,
    ensure_local_layout,
)
from server.platform.sqlite_store import connect_sqlite, describe_sqlite_target, row_to_dict
from server.platform.storage import (
    append_json_file,
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
    session_id: str | None = None
    resume_session_id: str | None = None
    fork_from_session_id: str | None = None
    result_subtype: str | None = None
    claim_id: str | None = None
    verdict: str | None = None
    manual_review_reason: str | None = None
    cost_usd: float = 0.0
    prompt_preview: str | None = None


class ResultStore(Protocol):
    """Persistence boundary for archived structured outputs."""

    def archive_result(self, record: ResultRecord, payload: dict[str, Any]) -> None: ...

    def list_records(
        self,
        tenant: str,
        conversation_id: str | None = None,
        claim_id: str | None = None,
        verdict: str | None = None,
        manual_review_reason: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def get_record_by_request_id(
        self,
        request_id: str,
        tenant: str,
    ) -> dict[str, Any] | None: ...

    def get_payload_by_request_id(
        self,
        request_id: str,
        tenant: str,
    ) -> dict[str, Any] | None: ...

    def list_records_admin(
        self,
        conversation_id: str | None = None,
        claim_id: str | None = None,
        verdict: str | None = None,
        manual_review_reason: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def get_record_by_request_id_admin(self, request_id: str) -> dict[str, Any] | None: ...

    def get_payload_by_request_id_admin(self, request_id: str) -> dict[str, Any] | None: ...

    def describe(self) -> dict[str, Any]: ...


class SQLiteResultStore:
    """SQLite-backed structured result index with JSON archive payloads."""

    COLUMNS = [
        "request_id",
        "created_at",
        "conversation_id",
        "request_mode",
        "schema_name",
        "result_file",
        "tenant",
        "claude_session_id",
        "session_id",
        "resume_session_id",
        "fork_from_session_id",
        "result_subtype",
        "claim_id",
        "verdict",
        "manual_review_reason",
        "cost_usd",
        "prompt_preview",
    ]

    def __init__(self, db_path: Path, archive_root: Path, legacy_shard_dir: Path | None) -> None:
        self.db_path = db_path
        self.archive_root = archive_root
        self.legacy_shard_dir = legacy_shard_dir
        self._initialize_schema()
        self._backfill_legacy_records()

    def archive_result(self, record: ResultRecord, payload: dict[str, Any]) -> None:
        append_json_file(self._result_path(record.result_file), payload)
        with connect_sqlite(self.db_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO results (
                    request_id, created_at, conversation_id, request_mode, schema_name,
                    result_file, tenant, claude_session_id, session_id, resume_session_id,
                    fork_from_session_id, result_subtype, claim_id, verdict, manual_review_reason, cost_usd,
                    prompt_preview
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._record_values(asdict(record)),
            )

    def list_records(
        self,
        tenant: str,
        conversation_id: str | None = None,
        claim_id: str | None = None,
        verdict: str | None = None,
        manual_review_reason: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM results WHERE tenant = ?"
        params: list[Any] = [tenant]
        if conversation_id:
            query += " AND conversation_id = ?"
            params.append(conversation_id)
        if claim_id:
            query += " AND claim_id = ?"
            params.append(claim_id)
        if verdict:
            query += " AND verdict = ?"
            params.append(verdict)
        if manual_review_reason:
            query += " AND manual_review_reason = ?"
            params.append(manual_review_reason)
        query += " ORDER BY created_at DESC, request_id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_record_by_request_id(
        self,
        request_id: str,
        tenant: str,
    ) -> dict[str, Any] | None:
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM results WHERE request_id = ? AND tenant = ?",
                (request_id, tenant),
            ).fetchone()
        return row_to_dict(row)

    def get_payload_by_request_id(
        self,
        request_id: str,
        tenant: str,
    ) -> dict[str, Any] | None:
        record = self.get_record_by_request_id(request_id=request_id, tenant=tenant)
        if record is None:
            return None
        return load_json_file(self._result_path(str(record["result_file"])))

    def list_records_admin(
        self,
        conversation_id: str | None = None,
        claim_id: str | None = None,
        verdict: str | None = None,
        manual_review_reason: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM results"
        clauses: list[str] = []
        params: list[Any] = []
        if conversation_id:
            clauses.append("conversation_id = ?")
            params.append(conversation_id)
        if claim_id:
            clauses.append("claim_id = ?")
            params.append(claim_id)
        if verdict:
            clauses.append("verdict = ?")
            params.append(verdict)
        if manual_review_reason:
            clauses.append("manual_review_reason = ?")
            params.append(manual_review_reason)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC, request_id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_record_by_request_id_admin(self, request_id: str) -> dict[str, Any] | None:
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM results WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return row_to_dict(row)

    def get_payload_by_request_id_admin(self, request_id: str) -> dict[str, Any] | None:
        record = self.get_record_by_request_id_admin(request_id)
        if record is None:
            return None
        return load_json_file(self._result_path(str(record["result_file"])))

    def describe(self) -> dict[str, Any]:
        description = describe_sqlite_target(self.db_path, backend="sqlite+json-files")
        description["archive_dir"] = str(self.archive_root)
        description["archive"] = describe_storage_target(self.archive_root)
        description["legacy_shard_dir"] = str(self.legacy_shard_dir) if self.legacy_shard_dir else None
        return description

    def _result_path(self, stored_path: str) -> Path:
        path = (self.archive_root.parent.parent / stored_path).resolve()
        root = self.archive_root.parent.parent.resolve()
        if root not in path.parents and path != root:
            raise ValueError(f"Result path escapes logs root: {stored_path}")
        return path

    def _initialize_schema(self) -> None:
        with connect_sqlite(self.db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS results (
                    request_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    request_mode TEXT NOT NULL,
                    schema_name TEXT,
                    result_file TEXT NOT NULL,
                    tenant TEXT,
                    claude_session_id TEXT,
                    session_id TEXT,
                    resume_session_id TEXT,
                    fork_from_session_id TEXT,
                    result_subtype TEXT,
                    claim_id TEXT,
                    verdict TEXT,
                    manual_review_reason TEXT,
                    cost_usd REAL NOT NULL DEFAULT 0,
                    prompt_preview TEXT
                );
                """
            )
            existing_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(results)").fetchall()
            }
            if "manual_review_reason" not in existing_columns:
                connection.execute(
                    "ALTER TABLE results ADD COLUMN manual_review_reason TEXT"
                )
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_results_tenant_created
                    ON results (tenant, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_results_conversation
                    ON results (tenant, conversation_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_results_claim
                    ON results (tenant, claim_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_results_verdict_reason
                    ON results (tenant, verdict, manual_review_reason, created_at DESC);
                """
            )

    def _backfill_legacy_records(self) -> None:
        if self.legacy_shard_dir is None:
            return
        shard_paths = [item for item in sorted(self.legacy_shard_dir.glob("*.jsonl")) if item.is_file()]
        legacy_records = load_jsonl_records_from_paths(shard_paths)
        if not legacy_records:
            return
        with connect_sqlite(self.db_path) as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO results (
                    request_id, created_at, conversation_id, request_mode, schema_name,
                    result_file, tenant, claude_session_id, session_id, resume_session_id,
                    fork_from_session_id, result_subtype, claim_id, verdict, manual_review_reason, cost_usd,
                    prompt_preview
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [self._record_values(record) for record in legacy_records],
            )

    def _record_values(self, record: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(record.get(column) for column in self.COLUMNS)


RESULT_STORE: ResultStore = SQLiteResultStore(RESULT_INDEX_DB_FILE, RESULT_BY_REQUEST_DIR, RESULT_INDEX_SHARD_DIR)


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
    manual_review_reason = response.get("manual_review_reason") if isinstance(response, dict) else None
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
        session_id=claude_session_id,
        resume_session_id=resume_session_id,
        fork_from_session_id=fork_from_session_id,
        schema_name=schema_name,
        request_mode=request_mode,
        result_subtype=result_subtype,
        claim_id=str(claim_id) if claim_id else None,
        verdict=str(verdict) if verdict else None,
        manual_review_reason=str(manual_review_reason) if manual_review_reason else None,
        cost_usd=cost_usd,
        prompt_preview=prompt_preview,
        created_at=created_at,
        result_file=str(result_file_path.relative_to(RESULT_BY_REQUEST_DIR.parent.parent)),
    )
    RESULT_STORE.archive_result(record, payload)
    return record


def list_result_records(
    tenant: str,
    conversation_id: str | None = None,
    claim_id: str | None = None,
    verdict: str | None = None,
    manual_review_reason: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return RESULT_STORE.list_records(
        tenant=tenant,
        conversation_id=conversation_id,
        claim_id=claim_id,
        verdict=verdict,
        manual_review_reason=manual_review_reason,
        limit=limit,
        offset=offset,
    )


def get_result_record_by_request_id(
    request_id: str,
    tenant: str,
) -> dict[str, Any] | None:
    return RESULT_STORE.get_record_by_request_id(request_id=request_id, tenant=tenant)


def get_result_payload_by_request_id(
    request_id: str,
    tenant: str,
) -> dict[str, Any] | None:
    return RESULT_STORE.get_payload_by_request_id(request_id=request_id, tenant=tenant)


def list_result_records_admin(
    conversation_id: str | None = None,
    claim_id: str | None = None,
    verdict: str | None = None,
    manual_review_reason: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return RESULT_STORE.list_records_admin(
        conversation_id=conversation_id,
        claim_id=claim_id,
        verdict=verdict,
        manual_review_reason=manual_review_reason,
        limit=limit,
        offset=offset,
    )


def get_result_record_by_request_id_admin(request_id: str) -> dict[str, Any] | None:
    return RESULT_STORE.get_record_by_request_id_admin(request_id)


def get_result_payload_by_request_id_admin(request_id: str) -> dict[str, Any] | None:
    return RESULT_STORE.get_payload_by_request_id_admin(request_id)


def describe_result_store() -> dict[str, Any]:
    return RESULT_STORE.describe()
