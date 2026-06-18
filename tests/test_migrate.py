"""存储迁移：旧 logs/ 域库行 → 统一库；旧 by-request payload 文件 → payload 列。"""

from __future__ import annotations

import json
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


def test_copy_table_ignores_unknown_src_columns(tmp_path):
    # 旧库多出目标表没有的列时，取交集、不报 "no such column"。
    rid = "mig-" + uuid.uuid4().hex
    src = tmp_path / "old.sqlite3"
    con = sqlite3.connect(src)
    con.execute(
        "CREATE TABLE requests (request_id TEXT PRIMARY KEY, route TEXT, method TEXT, "
        "status_code INTEGER, status TEXT, duration_ms INTEGER, created_at TEXT, bogus_col TEXT)"
    )
    con.execute(
        "INSERT INTO requests VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (rid, "/audit", "POST", 200, "ok", 10, "2026-06-19T00:00:00+00:00", "drop-me"),
    )
    con.commit()
    con.close()

    import server.stores.request_store  # noqa: F401

    assert migrate._copy_table("requests", src) == 1


def test_reconstruct_review_delta_payload_from_old_file(tmp_path, monkeypatch):
    from server.platform.sqlite_store import connect_sqlite
    from server.platform.paths import PLATFORM_DB_FILE
    import server.stores.review_delta_store  # noqa: F401 — 确保 review_deltas 表已建

    rid = "mig-" + uuid.uuid4().hex
    # 旧 by-request 文件放在 monkeypatch 后的 LOGS_ROOT 下
    monkeypatch.setattr(migrate, "LOGS_ROOT", tmp_path)
    old_file = tmp_path / "review-deltas" / "by-request" / f"{rid}.json"
    old_file.parent.mkdir(parents=True, exist_ok=True)
    old_file.write_text('{"final_recommendation": "approve"}', encoding="utf-8")
    with connect_sqlite(PLATFORM_DB_FILE) as con:
        con.execute(
            "INSERT INTO review_deltas (request_id, created_at, result_file) VALUES (?, ?, ?)",
            (rid, "2026-06-19T00:00:00+00:00", f"review-deltas/by-request/{rid}.json"),
        )

    assert migrate._reconstruct_payloads("review_deltas") >= 1
    with connect_sqlite(PLATFORM_DB_FILE) as con:
        row = con.execute("SELECT payload FROM review_deltas WHERE request_id = ?", (rid,)).fetchone()
    assert json.loads(row["payload"])["final_recommendation"] == "approve"


def test_migrate_session_events_moves_old_jsonl(tmp_path, monkeypatch):
    old_logs = tmp_path / "logs"
    new_events = tmp_path / "data" / "sessions" / "events"
    (old_logs / "sessions" / "events" / "2026" / "06").mkdir(parents=True)
    (old_logs / "sessions" / "events" / "2026" / "06" / "evt.jsonl").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(migrate, "LOGS_ROOT", old_logs)
    monkeypatch.setattr(migrate, "SESSION_EVENT_DIR", new_events)

    assert migrate._migrate_session_events() == 1
    assert (new_events / "2026" / "06" / "evt.jsonl").is_file()
    assert migrate._migrate_session_events() == 0  # 第二次已存在 → 跳过
