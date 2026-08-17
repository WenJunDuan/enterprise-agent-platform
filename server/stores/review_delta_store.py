"""SQLite-backed storage for structured review delta payloads."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from server.platform.paths import REVIEW_DELTA_INDEX_DB_FILE, ensure_local_layout
from server.platform.sqlite_store import connect_sqlite, describe_sqlite_target, row_to_dict

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

    COLUMNS: ClassVar[list[str]] = [
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

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._initialize_schema()

    def archive_review_delta(self, record: ReviewDeltaRecord, payload: dict[str, Any]) -> None:
        # B1: 完整 payload 折叠进 payload TEXT 列（不再写 by-request 文件树）。
        columns = [*self.COLUMNS, "payload"]
        placeholders = ", ".join("?" for _ in columns)
        values = (
            *(asdict(record).get(column) for column in self.COLUMNS),
            json.dumps(payload, ensure_ascii=False),
        )
        with connect_sqlite(self.db_path) as connection:
            connection.execute(
                f"INSERT OR REPLACE INTO review_deltas ({', '.join(columns)}) VALUES ({placeholders})",
                values,
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
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT payload FROM review_deltas WHERE request_id = ? AND tenant = ?",
                (request_id, tenant),
            ).fetchone()
        if row is None or row["payload"] is None:
            return None
        return json.loads(row["payload"])

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
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT payload FROM review_deltas WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        if row is None or row["payload"] is None:
            return None
        return json.loads(row["payload"])

    def describe(self) -> dict[str, Any]:
        return describe_sqlite_target(self.db_path, backend="sqlite")

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
                    reviewed_by TEXT,
                    payload TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_review_deltas_tenant_created
                    ON review_deltas (tenant, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_review_deltas_claim
                    ON review_deltas (tenant, claim_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_review_deltas_recommendation
                    ON review_deltas (tenant, final_recommendation, reviewer_verdict, created_at DESC);
                """
            )
            existing_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(review_deltas)").fetchall()
            }
            if "payload" not in existing_columns:
                connection.execute("ALTER TABLE review_deltas ADD COLUMN payload TEXT")


REVIEW_DELTA_STORE = SQLiteReviewDeltaStore(REVIEW_DELTA_INDEX_DB_FILE)


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
    created_at = created_at or datetime.now(UTC).isoformat()
    record = ReviewDeltaRecord(
        request_id=request_id,
        created_at=created_at,
        conversation_id=conversation_id,
        claude_session_id=claude_session_id,
        result_file=f"{request_id}.json",
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
