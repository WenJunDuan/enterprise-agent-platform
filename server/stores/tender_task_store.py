"""Task-status persistence for async tender evaluation submissions (SQLite).

域隔离镜像 ``audit_task_store``：tender 评标任务自有一张 ``tender_tasks`` 表，
不和 audit 共表（``mode`` 仍表示提交模式 directory/upload，不承载域信息）。一行一个
request_id，upsert 是单行 ``INSERT OR REPLACE`` 合并语义，并发交给 SQLite。

无 legacy backfill：tender 是新域，不存在旧 ``tasks.json`` 历史面。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from typing import Any

from server.platform.paths import PLATFORM_DB_FILE, ensure_local_layout
from server.platform.sqlite_store import connect_sqlite

ensure_local_layout()


@dataclass(slots=True)
class TenderTaskRecord:
    request_id: str
    tenant: str | None
    session_id: str | None
    status: str
    mode: str
    source_mode: str
    case_path: str
    claim_id: str | None = None
    result_file: str | None = None
    error_detail: str | None = None
    progress_message: str | None = None
    submitted_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str = ""


_FIELDS = [f.name for f in fields(TenderTaskRecord)]
_COLUMNS = ", ".join(_FIELDS)
_PLACEHOLDERS = ", ".join("?" for _ in _FIELDS)


def _coerce_record(updates: dict[str, Any], existing: dict[str, Any] | None) -> TenderTaskRecord:
    """Merge a partial update onto any existing row, mirroring the dict-merge upsert."""
    merged: dict[str, Any] = dict(existing) if existing else {}
    merged.update(updates)
    merged.setdefault("tenant", None)
    merged.setdefault("session_id", None)
    if "source_mode" not in merged and "mode" in merged:
        merged["source_mode"] = merged["mode"]
    return TenderTaskRecord(**{k: v for k, v in merged.items() if k in _FIELDS})


def _record_values(record: TenderTaskRecord) -> tuple[Any, ...]:
    data = asdict(record)
    return tuple(data[name] for name in _FIELDS)


def _initialize_schema() -> None:
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS tender_tasks (
                request_id TEXT PRIMARY KEY,
                tenant TEXT,
                session_id TEXT,
                status TEXT NOT NULL,
                mode TEXT NOT NULL,
                source_mode TEXT NOT NULL,
                case_path TEXT NOT NULL,
                claim_id TEXT,
                result_file TEXT,
                error_detail TEXT,
                progress_message TEXT,
                submitted_at TEXT,
                started_at TEXT,
                finished_at TEXT,
                updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_tender_tasks_tenant
                ON tender_tasks (tenant, submitted_at DESC);
            CREATE INDEX IF NOT EXISTS idx_tender_tasks_status
                ON tender_tasks (status);
            """
        )


_initialize_schema()


def upsert_tender_task(record: dict[str, Any]) -> None:
    # immediate=True：读现有行→合并→写 在一个原子事务内，防同一 request_id 并发丢更新。
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as connection:
        existing = connection.execute(
            "SELECT * FROM tender_tasks WHERE request_id = ?", (record["request_id"],)
        ).fetchone()
        merged = _coerce_record(record, dict(existing) if existing else None)
        connection.execute(
            f"INSERT OR REPLACE INTO tender_tasks ({_COLUMNS}) VALUES ({_PLACEHOLDERS})",
            _record_values(merged),
        )


def delete_tender_task(request_id: str, tenant: str) -> bool:
    """Remove a task owned by `tenant`. Returns True when a record was deleted."""
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        cursor = connection.execute(
            "DELETE FROM tender_tasks WHERE request_id = ? AND tenant = ?",
            (request_id, tenant),
        )
        return cursor.rowcount > 0


def get_tender_task(request_id: str, tenant: str) -> dict[str, Any] | None:
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        row = connection.execute(
            "SELECT * FROM tender_tasks WHERE request_id = ? AND tenant = ?",
            (request_id, tenant),
        ).fetchone()
        return dict(row) if row else None


def list_tender_tasks(
    tenant: str,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM tender_tasks WHERE tenant = ?"
    params: list[Any] = [tenant]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY COALESCE(submitted_at, updated_at) DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def get_tender_task_admin(request_id: str) -> dict[str, Any] | None:
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        row = connection.execute(
            "SELECT * FROM tender_tasks WHERE request_id = ?", (request_id,)
        ).fetchone()
        return dict(row) if row else None


def list_tender_tasks_admin() -> list[dict[str, Any]]:
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM tender_tasks").fetchall()]


def recover_stale_tender_tasks(timeout_seconds: int, now: str | None = None) -> list[str]:
    current = _coerce_timestamp(now)
    recovered: list[str] = []
    for record in list_tender_tasks_admin():
        if record.get("status") != "running":
            continue
        started_at = record.get("started_at") or record.get("updated_at")
        if not started_at:
            continue
        started_moment = _coerce_timestamp(str(started_at))
        if (current - started_moment).total_seconds() <= timeout_seconds:
            continue
        recovered.append(str(record["request_id"]))
        upsert_tender_task(
            {
                "request_id": str(record["request_id"]),
                "status": "failed",
                "error_detail": "任务超时或服务重启后自动终止",
                "progress_message": "任务超时或服务重启后自动终止",
                "finished_at": current.isoformat(),
                "updated_at": current.isoformat(),
            }
        )
    return recovered


def _coerce_timestamp(value: str | None) -> datetime:
    if value:
        return datetime.fromisoformat(value)
    return datetime.now(timezone.utc)
