"""Shared SQLite helpers for local query stores."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server.platform.storage import describe_storage_target


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def connect_sqlite(db_path: Path, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection (WAL).

    immediate=True 立即取写锁（BEGIN IMMEDIATE），让"读-改-写"在一个原子事务内完成，
    避免同一行并发更新时的丢更新（用于 audit_tasks 的 upsert 合并）。
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute("PRAGMA synchronous=NORMAL")
    # 统一单库 platform.sqlite3 多表共写：WAL 让读写不互相阻塞，提升并发。
    connection.execute("PRAGMA journal_mode=WAL")
    if immediate:
        connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def describe_sqlite_target(db_path: Path, *, backend: str) -> dict[str, Any]:
    description = describe_storage_target(db_path)
    description["backend"] = backend
    return description
