"""One-time storage migration: old per-domain ``logs/`` stores → unified ``data/db/platform.sqlite3``.

旧版本每个域一个 ``logs/*/index.sqlite3``，结果 payload 落 ``logs/results/by-request`` 文件。
本迁移把这些结构化记录幂等导入统一库（``INSERT OR IGNORE``），并把旧结果 payload 文件
按 ``result_file`` 指针读回 ``results.payload`` 列。

audit_tasks 不在此处理——store 启动时自动从旧 ``tasks.json`` 回填（见 audit_task_store）。
``data/`` 与 ``logs/`` 均 gitignore，本迁移只动运行态、不入库、可重复执行。
"""

from __future__ import annotations

import json
from pathlib import Path

from server.platform.paths import (
    LEGACY_MEMORY_DB_FILE,
    LEGACY_REQUEST_DB_FILE,
    LEGACY_RESULT_DB_FILE,
    LEGACY_REVIEW_DB_FILE,
    LEGACY_SESSION_DB_FILE,
    LOGS_ROOT,
    PLATFORM_DB_FILE,
    ensure_local_layout,
)
from server.platform.sqlite_store import connect_sqlite

# 旧库 → 统一库的同名表。迁移前先 import 各 store 触发统一库建表（见 migrate_storage）。
_TABLE_SOURCES: dict[str, Path] = {
    "requests": LEGACY_REQUEST_DB_FILE,
    "sessions": LEGACY_SESSION_DB_FILE,
    "results": LEGACY_RESULT_DB_FILE,
    "review_deltas": LEGACY_REVIEW_DB_FILE,
    "memory_assets": LEGACY_MEMORY_DB_FILE,
}


def _copy_table(table: str, src_db: Path) -> int:
    """Copy every row of `table` from an old per-domain DB into the unified DB."""
    if src_db == PLATFORM_DB_FILE or not src_db.is_file():
        return 0
    with connect_sqlite(src_db) as src:
        try:
            rows = src.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608 — table 来自固定白名单
        except Exception:  # pragma: no cover - 旧库可能无此表
            return 0
    if not rows:
        return 0
    columns = list(rows[0].keys())
    col_list = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    migrated = 0
    with connect_sqlite(PLATFORM_DB_FILE) as dest:
        for row in rows:
            cursor = dest.execute(
                f"INSERT OR IGNORE INTO {table} ({col_list}) VALUES ({placeholders})",  # noqa: S608
                tuple(row[column] for column in columns),
            )
            migrated += cursor.rowcount
    return migrated


def _reconstruct_result_payloads() -> int:
    """旧结果 payload 在 by-request 文件里；按 result_file 指针读回 payload 列。"""
    filled = 0
    with connect_sqlite(PLATFORM_DB_FILE) as dest:
        rows = dest.execute(
            "SELECT request_id, result_file FROM results "
            "WHERE payload IS NULL AND result_file IS NOT NULL"
        ).fetchall()
        for row in rows:
            old_file = LOGS_ROOT / str(row["result_file"])
            if not old_file.is_file():
                continue
            try:
                payload = old_file.read_text(encoding="utf-8")
                json.loads(payload)  # 仅接受合法 JSON
            except (OSError, ValueError):
                continue
            dest.execute(
                "UPDATE results SET payload = ? WHERE request_id = ?",
                (payload, str(row["request_id"])),
            )
            filled += 1
    return filled


def migrate_storage() -> dict[str, int]:
    """Run the one-time migration into the unified DB. Idempotent. Returns per-table counts."""
    ensure_local_layout()
    # 触发各 store 在统一库建好目标表，再导入旧数据。
    import server.stores.memory_store  # noqa: F401
    import server.stores.request_store  # noqa: F401
    import server.stores.result_store  # noqa: F401
    import server.stores.review_delta_store  # noqa: F401
    import server.stores.session_store  # noqa: F401

    report: dict[str, int] = {table: _copy_table(table, src) for table, src in _TABLE_SOURCES.items()}
    report["result_payloads_reconstructed"] = _reconstruct_result_payloads()
    return report
