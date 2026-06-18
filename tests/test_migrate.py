"""存储迁移：旧 logs/ 域库行 → 统一库；旧 by-request payload 文件 → payload 列。"""

from __future__ import annotations

import sqlite3
import uuid

import server.stores.result_store  # noqa: F401 — 确保统一库 results 表已建
from server.platform.paths import PLATFORM_DB_FILE
from server.platform.sqlite_store import connect_sqlite
from server.stores import migrate


def test_copy_table_imports_rows_into_unified_db(tmp_path):
    rid = "mig-" + uuid.uuid4().hex
    src = tmp_path / "old_results.sqlite3"
    con = sqlite3.connect(src)
    con.execute(
        "CREATE TABLE results (request_id TEXT PRIMARY KEY, created_at TEXT, "
        "conversation_id TEXT, request_mode TEXT, result_file TEXT, tenant TEXT, verdict TEXT)"
    )
    con.execute(
        "INSERT INTO results VALUES (?, ?, ?, ?, ?, ?, ?)",
        (rid, "2026-06-19T00:00:00+00:00", "c1", "text", f"{rid}.json", "acme", "approved"),
    )
    con.commit()
    con.close()

    migrated = migrate._copy_table("results", src)
    assert migrated == 1
    with connect_sqlite(PLATFORM_DB_FILE) as dest:
        row = dest.execute("SELECT verdict FROM results WHERE request_id = ?", (rid,)).fetchone()
    assert row is not None
    assert row["verdict"] == "approved"


def test_copy_table_idempotent(tmp_path):
    rid = "mig-" + uuid.uuid4().hex
    src = tmp_path / "old_requests.sqlite3"
    con = sqlite3.connect(src)
    con.execute(
        "CREATE TABLE requests (request_id TEXT PRIMARY KEY, route TEXT, method TEXT, "
        "status_code INTEGER, status TEXT, duration_ms INTEGER, created_at TEXT)"
    )
    con.execute(
        "INSERT INTO requests VALUES (?, ?, ?, ?, ?, ?, ?)",
        (rid, "/audit", "POST", 200, "ok", 10, "2026-06-19T00:00:00+00:00"),
    )
    con.commit()
    con.close()

    import server.stores.request_store  # noqa: F401

    assert migrate._copy_table("requests", src) == 1
    assert migrate._copy_table("requests", src) == 0  # 第二次 INSERT OR IGNORE → 0


def test_missing_legacy_db_is_noop(tmp_path):
    assert migrate._copy_table("results", tmp_path / "nope.sqlite3") == 0
