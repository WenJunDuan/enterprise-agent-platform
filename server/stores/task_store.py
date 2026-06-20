"""Generic async-task status store (SQLite) — shared by audit/tender (round4 F7).

删 contract 死域后，audit/tender 的 task store 仍是 ~96% 逐字复制（dataclass / _coerce /
upsert / get / list / recover_stale 全同，仅表名 + audit 的一次性 legacy backfill 不同）。
本模块把这份逻辑收敛为一个泛型 ``TaskStore(table_name, legacy_file=...)``；域 store
(``audit_task_store`` / ``tender_task_store``) 退化成绑定表名的薄包装，再导出同名函数保持
调用方零改。在一处修 bug 即对所有域生效。

一行一个 request_id；upsert 是单行 ``INSERT OR REPLACE`` 合并语义（``immediate=True`` 事务内
读现有行→合并→写，防同一 request_id 并发丢更新）；并发交给 SQLite（WAL + busy_timeout）。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from typing import Any

from server.platform.paths import PLATFORM_DB_FILE, ensure_local_layout
from server.platform.sqlite_store import connect_sqlite
from server.platform.storage import load_json_file

ensure_local_layout()

_SAFE_TABLE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(slots=True)
class TaskRecord:
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


_FIELDS = [f.name for f in fields(TaskRecord)]
_COLUMNS = ", ".join(_FIELDS)
_PLACEHOLDERS = ", ".join("?" for _ in _FIELDS)


def _coerce_record(updates: dict[str, Any], existing: dict[str, Any] | None) -> TaskRecord:
    """Merge a partial update onto any existing row, mirroring the dict-merge upsert."""
    merged: dict[str, Any] = dict(existing) if existing else {}
    merged.update(updates)
    merged.setdefault("tenant", None)
    merged.setdefault("session_id", None)
    if "source_mode" not in merged and "mode" in merged:
        merged["source_mode"] = merged["mode"]
    return TaskRecord(**{k: v for k, v in merged.items() if k in _FIELDS})


def _record_values(record: TaskRecord) -> tuple[Any, ...]:
    data = asdict(record)
    return tuple(data[name] for name in _FIELDS)


def _coerce_timestamp(value: str | None) -> datetime:
    if value:
        return datetime.fromisoformat(value)
    return datetime.now(timezone.utc)


class TaskStore:
    """Async-task status table bound to one ``{domain}_tasks`` table name."""

    def __init__(self, table_name: str, *, legacy_file: Any | None = None) -> None:
        # table_name 仅来自本仓硬编码的域 store（"audit_tasks"/"tender_tasks"），非用户输入；
        # 仍白名单校验，杜绝未来误传外部串进 f-string SQL。
        if not _SAFE_TABLE.match(table_name):
            raise ValueError(f"unsafe task table name: {table_name!r}")
        self.table = table_name
        self._initialize_schema()
        if legacy_file is not None:
            self._backfill_legacy(legacy_file)

    def _initialize_schema(self) -> None:
        with connect_sqlite(PLATFORM_DB_FILE) as connection:
            connection.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
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
                CREATE INDEX IF NOT EXISTS idx_{self.table}_tenant
                    ON {self.table} (tenant, submitted_at DESC);
                CREATE INDEX IF NOT EXISTS idx_{self.table}_status
                    ON {self.table} (status);
                """  # noqa: S608 - table 名经白名单校验，无外部输入
            )

    def _backfill_legacy(self, legacy_file: Any) -> None:
        """One-time import of an old ``tasks.json`` blob into the table (idempotent)."""
        loaded = load_json_file(legacy_file)
        if not isinstance(loaded, dict) or not loaded:
            return
        with connect_sqlite(PLATFORM_DB_FILE) as connection:
            for value in loaded.values():
                if not isinstance(value, dict) or "request_id" not in value:
                    continue
                try:
                    record = _coerce_record(value, existing=None)
                except TypeError:
                    # 旧任务行缺必填字段 → 跳过，绝不让坏数据在 import 时炸掉服务启动。
                    continue
                connection.execute(
                    f"INSERT OR IGNORE INTO {self.table} ({_COLUMNS}) "  # noqa: S608
                    f"VALUES ({_PLACEHOLDERS})",
                    _record_values(record),
                )

    def upsert(self, record: dict[str, Any]) -> None:
        with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as connection:
            existing = connection.execute(
                f"SELECT * FROM {self.table} WHERE request_id = ?",  # noqa: S608
                (record["request_id"],),
            ).fetchone()
            merged = _coerce_record(record, dict(existing) if existing else None)
            connection.execute(
                f"INSERT OR REPLACE INTO {self.table} ({_COLUMNS}) "  # noqa: S608
                f"VALUES ({_PLACEHOLDERS})",
                _record_values(merged),
            )

    def delete(self, request_id: str, tenant: str) -> bool:
        with connect_sqlite(PLATFORM_DB_FILE) as connection:
            cursor = connection.execute(
                f"DELETE FROM {self.table} WHERE request_id = ? AND tenant = ?",  # noqa: S608
                (request_id, tenant),
            )
            return cursor.rowcount > 0

    def get(self, request_id: str, tenant: str) -> dict[str, Any] | None:
        with connect_sqlite(PLATFORM_DB_FILE) as connection:
            row = connection.execute(
                f"SELECT * FROM {self.table} WHERE request_id = ? AND tenant = ?",  # noqa: S608
                (request_id, tenant),
            ).fetchone()
            return dict(row) if row else None

    def list(
        self,
        tenant: str,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = f"SELECT * FROM {self.table} WHERE tenant = ?"  # noqa: S608
        params: list[Any] = [tenant]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY COALESCE(submitted_at, updated_at) DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with connect_sqlite(PLATFORM_DB_FILE) as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def get_admin(self, request_id: str) -> dict[str, Any] | None:
        with connect_sqlite(PLATFORM_DB_FILE) as connection:
            row = connection.execute(
                f"SELECT * FROM {self.table} WHERE request_id = ?",  # noqa: S608
                (request_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_admin(self) -> list[dict[str, Any]]:
        with connect_sqlite(PLATFORM_DB_FILE) as connection:
            return [
                dict(row)
                for row in connection.execute(f"SELECT * FROM {self.table}").fetchall()  # noqa: S608
            ]

    def recover_stale(self, timeout_seconds: int, now: str | None = None) -> list[str]:
        current = _coerce_timestamp(now)
        recovered: list[str] = []
        for record in self.list_admin():
            if record.get("status") != "running":
                continue
            started_at = record.get("started_at") or record.get("updated_at")
            if not started_at:
                continue
            started_moment = _coerce_timestamp(str(started_at))
            if (current - started_moment).total_seconds() <= timeout_seconds:
                continue
            recovered.append(str(record["request_id"]))
            self.upsert(
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
