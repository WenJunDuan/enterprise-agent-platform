"""One-time storage migration: old per-domain ``logs/`` stores → unified ``data/db/platform.sqlite3``.

旧版本每个域一个 ``logs/*/index.sqlite3``；result/review payload 落 ``logs/{results,review-deltas}
/by-request`` 文件；会话 event 流落 ``logs/sessions/events``。本迁移：
- 把各域结构化记录幂等导入统一库（``INSERT OR IGNORE``，按列交集 + 逐行隔离坏数据）。
- 把旧 result/review payload 文件按 ``result_file`` 指针读回各自 ``payload`` 列。
- 把旧会话 event 流文件搬到 ``data/sessions/events``。

audit_tasks 不在此处理——store 启动时自动从旧 ``tasks.json`` 回填（见 audit_task_store）。
``data/`` 与 ``logs/`` 均 gitignore，本迁移只动运行态、不入库、可重复执行。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from server.platform.paths import (
    LEGACY_MEMORY_DB_FILE,
    LEGACY_REQUEST_DB_FILE,
    LEGACY_RESULT_DB_FILE,
    LEGACY_REVIEW_DB_FILE,
    LEGACY_SESSION_DB_FILE,
    LOGS_ROOT,
    PLATFORM_DB_FILE,
    SESSION_EVENT_DIR,
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

# payload 折叠进列的表：旧 payload 在 by-request 文件，按 result_file 指针读回。
_PAYLOAD_TABLES = ("results", "review_deltas")


def _dest_columns(table: str) -> set[str]:
    with connect_sqlite(PLATFORM_DB_FILE) as dest:
        rows = dest.execute(f"PRAGMA table_info({table})").fetchall()  # noqa: S608 — 固定白名单
    return {str(row["name"]) for row in rows}


def _copy_table(table: str, src_db: Path) -> int:
    """Copy rows from an old per-domain DB into the unified DB.

    Robust to schema drift: 只取源表与目标表的列交集（避免 "no such column"），逐行隔离
    坏数据（缺 NOT NULL 等单行错误不中断整表迁移）。
    """
    if src_db == PLATFORM_DB_FILE or not src_db.is_file():
        return 0
    with connect_sqlite(src_db) as src:
        try:
            rows = src.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608 — 固定白名单
        except Exception:  # pragma: no cover - 旧库可能无此表
            return 0
    if not rows:
        return 0
    columns = [column for column in rows[0].keys() if column in _dest_columns(table)]
    if not columns:
        return 0
    col_list = ", ".join(columns)
    placeholders = ", ".join("?" for _ in columns)
    migrated = 0
    with connect_sqlite(PLATFORM_DB_FILE) as dest:
        for row in rows:
            try:
                cursor = dest.execute(
                    f"INSERT OR IGNORE INTO {table} ({col_list}) VALUES ({placeholders})",  # noqa: S608
                    tuple(row[column] for column in columns),
                )
                migrated += cursor.rowcount
            except Exception:  # 单行坏数据（缺 NOT NULL / 类型不符）跳过，不中断整表
                continue
    return migrated


def _reconstruct_payloads(table: str) -> int:
    """payload-折叠表的旧 payload 在 by-request 文件；按 result_file 指针读回 payload 列。"""
    filled = 0
    with connect_sqlite(PLATFORM_DB_FILE) as dest:
        rows = dest.execute(
            f"SELECT request_id, result_file FROM {table} "  # noqa: S608 — 固定白名单
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
                f"UPDATE {table} SET payload = ? WHERE request_id = ?",  # noqa: S608
                (payload, str(row["request_id"])),
            )
            filled += 1
    return filled


def _migrate_session_events() -> int:
    """旧会话 event 流从 logs/sessions/events 搬到 data/sessions/events（已存在则跳过）。"""
    old_root = LOGS_ROOT / "sessions" / "events"
    if not old_root.is_dir() or old_root.resolve() == SESSION_EVENT_DIR.resolve():
        return 0
    moved = 0
    for src in old_root.rglob("*.jsonl"):
        dest = SESSION_EVENT_DIR / src.relative_to(old_root)
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        moved += 1
    return moved


def migrate_storage() -> dict[str, int]:
    """Run the one-time migration into the unified DB. Idempotent. Returns per-step counts."""
    ensure_local_layout()
    # 触发各 store 在统一库建好目标表，再导入旧数据。
    import server.stores.memory_store  # noqa: F401
    import server.stores.request_store  # noqa: F401
    import server.stores.result_store  # noqa: F401
    import server.stores.review_delta_store  # noqa: F401
    import server.stores.session_store  # noqa: F401

    report: dict[str, int] = {table: _copy_table(table, src) for table, src in _TABLE_SOURCES.items()}
    for table in _PAYLOAD_TABLES:
        report[f"{table}_payloads_reconstructed"] = _reconstruct_payloads(table)
    report["session_events_migrated"] = _migrate_session_events()
    return report
