"""SQLite-backed index for structured memory assets stored under knowledge/memory."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, ClassVar

from server.platform.paths import MEMORY_INDEX_DB_FILE, PROJECT_ROOT
from server.platform.sqlite_store import connect_sqlite, describe_sqlite_target, row_to_dict

logger = logging.getLogger(__name__)


KNOWLEDGE_MEMORY_ROOT = PROJECT_ROOT / "knowledge" / "memory"


class SQLiteMemoryStore:
    """Indexes memory JSON assets for query surfaces while keeping files as source of truth."""

    COLUMNS: ClassVar[list[str]] = [
        "memory_id",
        "domain",
        "memory_type",
        "title",
        "summary",
        "category",
        "recommended_verdict",
        "manual_review_reason",
        "rationale",
        "tags",
        "source_request_id",
        "source_result_file",
        "source_claim_id",
        "source_conversation_id",
        "source_claude_session_id",
        "source_review_delta_file",
        "distilled_by",
        "distilled_at",
        "file_path",
        "payload_json",
    ]

    def __init__(self, db_path: Path, memory_root: Path) -> None:
        self.db_path = db_path
        self.memory_root = memory_root
        self._last_signature: tuple[tuple[str, int, int], ...] | None = None
        self._initialize_schema()

    def _memory_signature(self) -> tuple[tuple[str, int, int], ...]:
        """memory 文件 (path, mtime_ns, size) 指纹；文件未变即可跳过重建。"""
        if not self.memory_root.is_dir():
            return ()
        return tuple(
            (str(path), path.stat().st_mtime_ns, path.stat().st_size)
            for path in sorted(self.memory_root.rglob("*.json"))
        )

    def refresh_index(self, *, force: bool = False) -> None:
        # memory index 是 knowledge/memory 文件的派生缓存。统一库下"每次读都 DELETE+重插"
        # 会与 audit/请求写抢同一 SQLite writer，故用 mtime 指纹守卫：文件没变就不写库。
        signature = self._memory_signature()
        if not force and signature == self._last_signature:
            return
        records = self._load_memory_files()
        with connect_sqlite(self.db_path) as connection:
            connection.execute("DELETE FROM memory_assets")
            connection.executemany(
                """
                INSERT INTO memory_assets (
                    memory_id, domain, memory_type, title, summary, category,
                    recommended_verdict, manual_review_reason, rationale, tags,
                    source_request_id, source_result_file, source_claim_id,
                    source_conversation_id, source_claude_session_id, source_review_delta_file,
                    distilled_by, distilled_at, file_path, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [self._record_values(record) for record in records],
            )
        self._last_signature = signature

    def list_records(
        self,
        domain: str | None = None,
        category: str | None = None,
        recommended_verdict: str | None = None,
        manual_review_reason: str | None = None,
        source_request_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self.refresh_index()
        query = "SELECT * FROM memory_assets"
        clauses: list[str] = []
        params: list[Any] = []
        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if recommended_verdict:
            clauses.append("recommended_verdict = ?")
            params.append(recommended_verdict)
        if manual_review_reason:
            clauses.append("manual_review_reason = ?")
            params.append(manual_review_reason)
        if source_request_id:
            clauses.append("source_request_id = ?")
            params.append(source_request_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY distilled_at DESC, memory_id ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_record_by_memory_id(self, memory_id: str) -> dict[str, Any] | None:
        self.refresh_index()
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM memory_assets WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def list_records_by_request_id(self, request_id: str) -> list[dict[str, Any]]:
        return self.list_records(source_request_id=request_id, limit=100, offset=0)

    def describe(self) -> dict[str, Any]:
        description = describe_sqlite_target(self.db_path, backend="sqlite+knowledge-files")
        description["memory_root"] = str(self.memory_root)
        return description

    def _initialize_schema(self) -> None:
        with connect_sqlite(self.db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_assets (
                    memory_id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    category TEXT,
                    recommended_verdict TEXT NOT NULL,
                    manual_review_reason TEXT,
                    rationale TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    source_request_id TEXT NOT NULL,
                    source_result_file TEXT NOT NULL,
                    source_claim_id TEXT,
                    source_conversation_id TEXT,
                    source_claude_session_id TEXT,
                    source_review_delta_file TEXT,
                    distilled_by TEXT NOT NULL,
                    distilled_at TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_domain_category
                    ON memory_assets (domain, category, distilled_at DESC);
                CREATE INDEX IF NOT EXISTS idx_memory_verdict_reason
                    ON memory_assets (domain, recommended_verdict, manual_review_reason, distilled_at DESC);
                CREATE INDEX IF NOT EXISTS idx_memory_request
                    ON memory_assets (source_request_id, distilled_at DESC);
                """
            )

    def _load_memory_files(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(self.memory_root.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("corrupt/unreadable memory file %s, skipping: %s", path, exc)
                continue
            try:
                payload["_file_path"] = str(path.relative_to(PROJECT_ROOT))
            except ValueError:
                payload["_file_path"] = str(path)
            records.append(payload)
        return records

    def _record_values(self, record: dict[str, Any]) -> tuple[Any, ...]:
        trace = record.get("source_trace") or {}
        return (
            record.get("memory_id"),
            record.get("domain"),
            record.get("memory_type"),
            record.get("title"),
            record.get("summary"),
            record.get("category"),
            record.get("recommended_verdict"),
            record.get("manual_review_reason"),
            record.get("rationale"),
            json.dumps(record.get("tags", []), ensure_ascii=False),
            trace.get("request_id"),
            trace.get("result_file"),
            trace.get("claim_id"),
            trace.get("conversation_id"),
            trace.get("claude_session_id"),
            trace.get("review_delta_file"),
            record.get("distilled_by"),
            record.get("distilled_at"),
            record.get("_file_path"),
            json.dumps(record, ensure_ascii=False),
        )

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        loaded = row_to_dict(row) or {}
        tags = loaded.get("tags")
        payload_json = loaded.get("payload_json")
        loaded["tags"] = json.loads(tags) if tags else []
        loaded["payload"] = json.loads(payload_json) if payload_json else None
        return loaded


MEMORY_STORE = SQLiteMemoryStore(MEMORY_INDEX_DB_FILE, KNOWLEDGE_MEMORY_ROOT)


def list_memory_records(
    domain: str | None = None,
    category: str | None = None,
    recommended_verdict: str | None = None,
    manual_review_reason: str | None = None,
    source_request_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return MEMORY_STORE.list_records(
        domain=domain,
        category=category,
        recommended_verdict=recommended_verdict,
        manual_review_reason=manual_review_reason,
        source_request_id=source_request_id,
        limit=limit,
        offset=offset,
    )


def get_memory_record_by_id(memory_id: str) -> dict[str, Any] | None:
    return MEMORY_STORE.get_record_by_memory_id(memory_id)


def list_memory_records_by_request_id(request_id: str) -> list[dict[str, Any]]:
    return MEMORY_STORE.list_records_by_request_id(request_id)


def describe_memory_store() -> dict[str, Any]:
    return MEMORY_STORE.describe()
