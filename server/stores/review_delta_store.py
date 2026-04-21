"""SQLite-backed storage for structured review delta payloads."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.platform.paths import (
    REVIEW_DELTA_BY_REQUEST_DIR,
    REVIEW_DELTA_INDEX_DB_FILE,
    build_review_delta_archive_path,
    ensure_local_layout,
)
from server.platform.sqlite_store import connect_sqlite, describe_sqlite_target, row_to_dict
from server.platform.storage import append_json_file, describe_storage_target, load_json_file

ensure_local_layout()


@dataclass(slots=True)
class ReviewDeltaRecord:
    request_id: str
    created_at: str
    conversation_id: str | None
    claude_session_id: str | None
    result_file: str
    tenant: str | None = None
    claim_id: str | None = None
    initial_verdict: str | None = None
    reviewer_verdict: str | None = None
    final_recommendation: str | None = None
    agrees_with_initial: bool = False
    escalation_recommended: bool = False
    reviewed_by: str | None = None


class SQLiteReviewDeltaStore:
    """SQLite-backed review delta index with JSON archive payloads."""

    COLUMNS = [
        "request_id",
        "created_at",
        "conversation_id",
        "claude_session_id",
        "result_file",
        "tenant",
        "claim_id",
        "initial_verdict",
        "reviewer_verdict",
        "final_recommendation",
        "agrees_with_initial",
        "escalation_recommended",
        "reviewed_by",
    ]

    def __init__(self, db_path: Path, archive_root: Path) -> None:
        self.db_path = db_path
        self.archive_root = archive_root
        self._initialize_schema()

    def archive_review_delta(self, record: ReviewDeltaRecord, payload: dict[str, Any]) -> None:
        append_json_file(self._archive_path(record.result_file), payload)
        with connect_sqlite(self.db_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO review_deltas (
                    request_id, created_at, conversation_id, claude_session_id, result_file,
                    tenant, claim_id, initial_verdict, reviewer_verdict, final_recommendation,
                    agrees_with_initial, escalation_recommended, reviewed_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(asdict(record).get(column) for column in self.COLUMNS),
            )

    def list_records(
        self,
        tenant: str,
        claim_id: str | None = None,
        final_recommendation: str | None = None,
        reviewer_verdict: str | None = None,
        agrees_with_initial: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM review_deltas WHERE tenant = ?"
        params: list[Any] = [tenant]
        if claim_id:
            query += " AND claim_id = ?"
            params.append(claim_id)
        if final_recommendation:
            query += " AND final_recommendation = ?"
            params.append(final_recommendation)
        if reviewer_verdict:
            query += " AND reviewer_verdict = ?"
            params.append(reviewer_verdict)
        if agrees_with_initial is not None:
            query += " AND agrees_with_initial = ?"
            params.append(1 if agrees_with_initial else 0)
        query += " ORDER BY created_at DESC, request_id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_record_by_request_id(self, request_id: str, tenant: str) -> dict[str, Any] | None:
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM review_deltas WHERE request_id = ? AND tenant = ?",
                (request_id, tenant),
            ).fetchone()
        return row_to_dict(row)

    def get_payload_by_request_id(self, request_id: str, tenant: str) -> dict[str, Any] | None:
        record = self.get_record_by_request_id(request_id, tenant)
        if record is None:
            return None
        return load_json_file(self._archive_path(str(record["result_file"])))

    def list_records_admin(
        self,
        claim_id: str | None = None,
        final_recommendation: str | None = None,
        reviewer_verdict: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM review_deltas"
        clauses: list[str] = []
        params: list[Any] = []
        if claim_id:
            clauses.append("claim_id = ?")
            params.append(claim_id)
        if final_recommendation:
            clauses.append("final_recommendation = ?")
            params.append(final_recommendation)
        if reviewer_verdict:
            clauses.append("reviewer_verdict = ?")
            params.append(reviewer_verdict)
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
                "SELECT * FROM review_deltas WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return row_to_dict(row)

    def get_payload_by_request_id_admin(self, request_id: str) -> dict[str, Any] | None:
        record = self.get_record_by_request_id_admin(request_id)
        if record is None:
            return None
        return load_json_file(self._archive_path(str(record["result_file"])))

    def describe(self) -> dict[str, Any]:
        description = describe_sqlite_target(self.db_path, backend="sqlite+json-files")
        description["archive_dir"] = str(self.archive_root)
        description["archive"] = describe_storage_target(self.archive_root)
        return description

    def _initialize_schema(self) -> None:
        with connect_sqlite(self.db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS review_deltas (
                    request_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    conversation_id TEXT,
                    claude_session_id TEXT,
                    result_file TEXT NOT NULL,
                    tenant TEXT,
                    claim_id TEXT,
                    initial_verdict TEXT,
                    reviewer_verdict TEXT,
                    final_recommendation TEXT,
                    agrees_with_initial INTEGER NOT NULL DEFAULT 0,
                    escalation_recommended INTEGER NOT NULL DEFAULT 0,
                    reviewed_by TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_review_deltas_tenant_created
                    ON review_deltas (tenant, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_review_deltas_claim
                    ON review_deltas (tenant, claim_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_review_deltas_recommendation
                    ON review_deltas (tenant, final_recommendation, reviewer_verdict, created_at DESC);
                """
            )

    def _archive_path(self, stored_path: str) -> Path:
        path = (self.archive_root.parent.parent / stored_path).resolve()
        root = self.archive_root.parent.parent.resolve()
        if root not in path.parents and path != root:
            raise ValueError(f"Review delta path escapes logs root: {stored_path}")
        return path


REVIEW_DELTA_STORE = SQLiteReviewDeltaStore(REVIEW_DELTA_INDEX_DB_FILE, REVIEW_DELTA_BY_REQUEST_DIR)


def archive_review_delta_payload(
    *,
    request_id: str,
    tenant: str | None,
    conversation_id: str | None,
    claude_session_id: str | None,
    payload: dict[str, Any],
    created_at: str | None = None,
    store: SQLiteReviewDeltaStore | None = None,
) -> ReviewDeltaRecord:
    created_at = created_at or datetime.now(timezone.utc).isoformat()
    archive_path = build_review_delta_archive_path(request_id=request_id, timestamp=created_at)
    record = ReviewDeltaRecord(
        request_id=request_id,
        created_at=created_at,
        conversation_id=conversation_id,
        claude_session_id=claude_session_id,
        result_file=str(archive_path.relative_to(REVIEW_DELTA_BY_REQUEST_DIR.parent.parent)),
        tenant=tenant,
        claim_id=str(payload.get("claim_id") or "") or None,
        initial_verdict=str(payload.get("initial_verdict") or "") or None,
        reviewer_verdict=str(payload.get("reviewer_verdict") or "") or None,
        final_recommendation=str(payload.get("final_recommendation") or "") or None,
        agrees_with_initial=bool(payload.get("agrees_with_initial")),
        escalation_recommended=bool(payload.get("escalation_recommended")),
        reviewed_by=str(payload.get("reviewed_by") or "") or None,
    )
    (store or REVIEW_DELTA_STORE).archive_review_delta(record, payload)
    return record


def list_review_delta_records(
    tenant: str,
    claim_id: str | None = None,
    final_recommendation: str | None = None,
    reviewer_verdict: str | None = None,
    agrees_with_initial: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return REVIEW_DELTA_STORE.list_records(
        tenant=tenant,
        claim_id=claim_id,
        final_recommendation=final_recommendation,
        reviewer_verdict=reviewer_verdict,
        agrees_with_initial=agrees_with_initial,
        limit=limit,
        offset=offset,
    )


def get_review_delta_record_by_request_id(request_id: str, tenant: str) -> dict[str, Any] | None:
    return REVIEW_DELTA_STORE.get_record_by_request_id(request_id, tenant)


def get_review_delta_payload_by_request_id(request_id: str, tenant: str) -> dict[str, Any] | None:
    return REVIEW_DELTA_STORE.get_payload_by_request_id(request_id, tenant)


def list_review_delta_records_admin(
    claim_id: str | None = None,
    final_recommendation: str | None = None,
    reviewer_verdict: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return REVIEW_DELTA_STORE.list_records_admin(
        claim_id=claim_id,
        final_recommendation=final_recommendation,
        reviewer_verdict=reviewer_verdict,
        limit=limit,
        offset=offset,
    )


def get_review_delta_record_by_request_id_admin(request_id: str) -> dict[str, Any] | None:
    return REVIEW_DELTA_STORE.get_record_by_request_id_admin(request_id)


def get_review_delta_payload_by_request_id_admin(request_id: str) -> dict[str, Any] | None:
    return REVIEW_DELTA_STORE.get_payload_by_request_id_admin(request_id)


def describe_review_delta_store() -> dict[str, Any]:
    return REVIEW_DELTA_STORE.describe()
