"""SQLite-backed session store implementation with optional legacy JSONL backfill."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from server.platform.sqlite_store import connect_sqlite, describe_sqlite_target, row_to_dict
from server.platform.storage import load_jsonl_records_from_paths
from server.stores.session_records import SessionRecord


class SQLiteSessionStore:
    """SQLite-backed session repository with optional legacy JSONL backfill."""

    COLUMNS = [
        "request_id",
        "conversation_id",
        "claude_session_id",
        "resume_session_id",
        "fork_from_session_id",
        "schema_name",
        "request_mode",
        "prompt_preview",
        "log_file",
        "status",
        "result_subtype",
        "cost_usd",
        "started_at",
        "finished_at",
        "tenant",
        "result_file",
    ]

    def __init__(self, db_path: Path, legacy_shard_dir: Path | None) -> None:
        self.db_path = db_path
        self.legacy_shard_dir = legacy_shard_dir
        self._initialize_schema()
        self._backfill_legacy_records()

    def append_record(self, record: SessionRecord) -> None:
        with connect_sqlite(self.db_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO sessions (
                    request_id, conversation_id, claude_session_id, resume_session_id,
                    fork_from_session_id, schema_name, request_mode, prompt_preview,
                    log_file, status, result_subtype, cost_usd, started_at,
                    finished_at, tenant, result_file
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._record_values(asdict(record)),
            )

    def load_records(
        self,
        *,
        tenant: str,
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM sessions WHERE tenant = ?"
        params: list[Any] = [tenant]
        if conversation_id:
            query += " AND conversation_id = ?"
            params.append(conversation_id)
        query += " ORDER BY started_at ASC, request_id ASC"
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
                "SELECT * FROM sessions WHERE request_id = ? AND tenant = ?",
                (request_id, tenant),
            ).fetchone()
        return row_to_dict(row)

    def get_record_by_session_id(
        self,
        session_id: str,
        tenant: str,
    ) -> dict[str, Any] | None:
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE claude_session_id = ? AND tenant = ? ORDER BY started_at DESC LIMIT 1",
                (session_id, tenant),
            ).fetchone()
        return row_to_dict(row)

    def resolve_latest_session_id(
        self,
        conversation_id: str,
        tenant: str,
    ) -> str | None:
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT claude_session_id FROM sessions
                WHERE conversation_id = ? AND tenant = ? AND claude_session_id IS NOT NULL
                ORDER BY started_at DESC, request_id DESC
                LIMIT 1
                """,
                (conversation_id, tenant),
            ).fetchone()
        return str(row["claude_session_id"]) if row else None

    def list_logged_sessions(
        self,
        *,
        tenant: str,
        conversation_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM sessions WHERE tenant = ?"
        params: list[Any] = [tenant]
        if conversation_id:
            query += " AND conversation_id = ?"
            params.append(conversation_id)
        query += " ORDER BY started_at DESC, request_id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def list_conversation_summaries(
        self,
        tenant: str,
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
        ordered = sorted(
            summaries.values(),
            key=lambda item: item.get("last_activity_at") or "",
            reverse=True,
        )
        sliced = ordered[offset : offset + limit]
        for item in sliced:
            item["request_modes"] = sorted(mode for mode in item["request_modes"] if mode)
        return sliced

    def list_known_session_ids(self, tenant: str) -> set[str]:
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(
                "SELECT DISTINCT claude_session_id FROM sessions WHERE tenant = ? AND claude_session_id IS NOT NULL",
                (tenant,),
            ).fetchall()
        return {str(row["claude_session_id"]) for row in rows}

    def get_record_by_request_id_admin(self, request_id: str) -> dict[str, Any] | None:
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return row_to_dict(row)

    def get_record_by_session_id_admin(self, session_id: str) -> dict[str, Any] | None:
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE claude_session_id = ? ORDER BY started_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        return row_to_dict(row)

    def resolve_latest_session_id_admin(self, conversation_id: str) -> str | None:
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT claude_session_id FROM sessions
                WHERE conversation_id = ? AND claude_session_id IS NOT NULL
                ORDER BY started_at DESC, request_id DESC
                LIMIT 1
                """,
                (conversation_id,),
            ).fetchone()
        return str(row["claude_session_id"]) if row else None

    def list_logged_sessions_admin(
        self,
        conversation_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM sessions"
        params: list[Any] = []
        if conversation_id:
            query += " WHERE conversation_id = ?"
            params.append(conversation_id)
        query += " ORDER BY started_at DESC, request_id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def list_conversation_summaries_admin(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        summaries: dict[str, dict[str, Any]] = {}
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM sessions ORDER BY started_at ASC, request_id ASC"
            ).fetchall()
        for row in rows:
            record = dict(row)
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
        ordered = sorted(
            summaries.values(),
            key=lambda item: item.get("last_activity_at") or "",
            reverse=True,
        )
        sliced = ordered[offset : offset + limit]
        for item in sliced:
            item["request_modes"] = sorted(mode for mode in item["request_modes"] if mode)
        return sliced

    def list_known_session_ids_admin(self) -> set[str]:
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(
                "SELECT DISTINCT claude_session_id FROM sessions WHERE claude_session_id IS NOT NULL"
            ).fetchall()
        return {str(row["claude_session_id"]) for row in rows}

    def describe(self) -> dict[str, Any]:
        description = describe_sqlite_target(self.db_path, backend="sqlite")
        description["legacy_shard_dir"] = str(self.legacy_shard_dir) if self.legacy_shard_dir else None
        return description

    def _initialize_schema(self) -> None:
        with connect_sqlite(self.db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    request_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    claude_session_id TEXT,
                    resume_session_id TEXT,
                    fork_from_session_id TEXT,
                    schema_name TEXT,
                    request_mode TEXT NOT NULL,
                    prompt_preview TEXT NOT NULL,
                    log_file TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_subtype TEXT,
                    cost_usd REAL NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    tenant TEXT,
                    result_file TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_tenant_started
                    ON sessions (tenant, started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_sessions_conversation
                    ON sessions (tenant, conversation_id, started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_sessions_claude_session
                    ON sessions (tenant, claude_session_id);
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
                INSERT OR IGNORE INTO sessions (
                    request_id, conversation_id, claude_session_id, resume_session_id,
                    fork_from_session_id, schema_name, request_mode, prompt_preview,
                    log_file, status, result_subtype, cost_usd, started_at,
                    finished_at, tenant, result_file
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [self._record_values(record) for record in legacy_records],
            )

    def _record_values(self, record: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(record.get(column) for column in self.COLUMNS)
