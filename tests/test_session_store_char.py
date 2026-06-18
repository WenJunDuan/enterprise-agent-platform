"""Characterization tests for server/stores/session_store.py.

锁定现有行为（不评判对错），为任务 4 的拆分提供保护网。
全部使用 tmp_path / monkeypatch 隔离文件系统，不依赖真实数据库。
"""

from __future__ import annotations

import re
from pathlib import Path

# （conftest.py 已经搞定了 offline guard env vars。）


# ═════════════════════════════════════════════════════════════════════════════
# utc_now — 格式锁定
# ═════════════════════════════════════════════════════════════════════════════


class TestUtcNow:
    def test_returns_isoformat_string(self):
        from server.stores.session_store import utc_now

        ts = utc_now()
        # ISO 8601 with timezone offset or Z suffix
        assert isinstance(ts, str)
        assert len(ts) > 10

    def test_contains_timezone_info(self):
        from server.stores.session_store import utc_now

        ts = utc_now()
        # Must have UTC offset (+00:00 or +0000 or Z)
        assert "+" in ts or ts.endswith("Z")

    def test_format_is_parseable(self):
        from datetime import datetime

        from server.stores.session_store import utc_now

        ts = utc_now()
        # Should not raise
        dt = datetime.fromisoformat(ts)
        assert dt.tzinfo is not None


# ═════════════════════════════════════════════════════════════════════════════
# new_conversation_id — UUID 格式锁定
# ═════════════════════════════════════════════════════════════════════════════


class TestNewConversationId:
    _UUID_RE = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )

    def test_returns_uuid_string(self):
        from server.stores.session_store import new_conversation_id

        cid = new_conversation_id()
        assert isinstance(cid, str)
        assert self._UUID_RE.match(cid), f"Not a UUID: {cid}"

    def test_each_call_returns_different_id(self):
        from server.stores.session_store import new_conversation_id

        ids = {new_conversation_id() for _ in range(10)}
        assert len(ids) == 10


# ═════════════════════════════════════════════════════════════════════════════
# append_session_record + resolve_latest_session_id (tenant-scoped)
# ═════════════════════════════════════════════════════════════════════════════


def _make_record(
    *,
    request_id: str,
    conversation_id: str,
    claude_session_id: str | None = None,
    tenant: str = "test-tenant",
    started_at: str | None = None,
    finished_at: str | None = None,
) -> object:
    from server.stores.session_store import SessionRecord, utc_now

    now = utc_now()
    return SessionRecord(
        request_id=request_id,
        conversation_id=conversation_id,
        claude_session_id=claude_session_id,
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=None,
        request_mode="structured",
        prompt_preview="test prompt",
        log_file="logs/test.jsonl",
        status="success",
        result_subtype=None,
        cost_usd=0.0,
        started_at=started_at or now,
        finished_at=finished_at or now,
        tenant=tenant,
        result_file=None,
    )


class TestAppendAndResolveSessionRecord:
    """Covers append_session_record + resolve_latest_session_id (tenant) together."""

    def _patch_store(self, monkeypatch, tmp_path: Path):
        """Redirect SESSION_STORE to a fresh SQLite DB in tmp_path."""
        import server.stores.session_store as ss

        from server.stores.session_store import SQLiteSessionStore

        db_path = tmp_path / "sessions.db"
        fresh_store = SQLiteSessionStore(db_path)
        monkeypatch.setattr(ss, "SESSION_STORE", fresh_store)
        return fresh_store

    def test_appended_record_is_retrievable(self, tmp_path, monkeypatch):
        self._patch_store(monkeypatch, tmp_path)
        from server.stores.session_store import (
            append_session_record,
            get_session_record_by_request_id,
        )

        rec = _make_record(
            request_id="req-001",
            conversation_id="conv-001",
            claude_session_id="sess-abc",
        )
        append_session_record(rec)
        result = get_session_record_by_request_id("req-001", tenant="test-tenant")
        assert result is not None
        assert result["request_id"] == "req-001"
        assert result["claude_session_id"] == "sess-abc"

    def test_resolve_latest_session_id_returns_most_recent(self, tmp_path, monkeypatch):
        self._patch_store(monkeypatch, tmp_path)
        from server.stores.session_store import (
            append_session_record,
            resolve_latest_session_id,
        )

        conv_id = "conv-resolve-test"
        rec1 = _make_record(
            request_id="req-r1",
            conversation_id=conv_id,
            claude_session_id="sess-first",
            started_at="2024-01-01T10:00:00+00:00",
        )
        rec2 = _make_record(
            request_id="req-r2",
            conversation_id=conv_id,
            claude_session_id="sess-second",
            started_at="2024-01-01T11:00:00+00:00",
        )
        append_session_record(rec1)
        append_session_record(rec2)

        resolved = resolve_latest_session_id(conv_id, tenant="test-tenant")
        assert resolved == "sess-second"

    def test_resolve_latest_session_id_wrong_tenant_returns_none(self, tmp_path, monkeypatch):
        self._patch_store(monkeypatch, tmp_path)
        from server.stores.session_store import (
            append_session_record,
            resolve_latest_session_id,
        )

        conv_id = "conv-tenant-isolation"
        rec = _make_record(
            request_id="req-iso",
            conversation_id=conv_id,
            claude_session_id="sess-xyz",
            tenant="tenant-a",
        )
        append_session_record(rec)

        # Different tenant must not see the session
        resolved = resolve_latest_session_id(conv_id, tenant="tenant-b")
        assert resolved is None

    def test_resolve_returns_none_when_no_records(self, tmp_path, monkeypatch):
        self._patch_store(monkeypatch, tmp_path)
        from server.stores.session_store import resolve_latest_session_id

        resolved = resolve_latest_session_id("conv-nonexistent", tenant="test-tenant")
        assert resolved is None

    def test_resolve_skips_records_with_null_claude_session_id(self, tmp_path, monkeypatch):
        self._patch_store(monkeypatch, tmp_path)
        from server.stores.session_store import (
            append_session_record,
            resolve_latest_session_id,
        )

        conv_id = "conv-null-session"
        rec = _make_record(
            request_id="req-null",
            conversation_id=conv_id,
            claude_session_id=None,  # no session id yet
        )
        append_session_record(rec)
        resolved = resolve_latest_session_id(conv_id, tenant="test-tenant")
        assert resolved is None


# ═════════════════════════════════════════════════════════════════════════════
# resolve_latest_session_id_admin — bypasses tenant isolation
# ═════════════════════════════════════════════════════════════════════════════


class TestResolveLatestSessionIdAdmin:
    def _patch_store(self, monkeypatch, tmp_path: Path):
        import server.stores.session_store as ss
        from server.stores.session_store import SQLiteSessionStore

        db_path = tmp_path / "sessions.db"
        fresh_store = SQLiteSessionStore(db_path)
        monkeypatch.setattr(ss, "SESSION_STORE", fresh_store)

    def test_admin_sees_across_tenants(self, tmp_path, monkeypatch):
        self._patch_store(monkeypatch, tmp_path)
        from server.stores.session_store import (
            append_session_record,
            resolve_latest_session_id_admin,
        )

        conv_id = "conv-admin-cross"
        rec = _make_record(
            request_id="req-admin-1",
            conversation_id=conv_id,
            claude_session_id="sess-cross-tenant",
            tenant="tenant-x",
        )
        append_session_record(rec)

        # Admin should find it even without specifying a tenant
        resolved = resolve_latest_session_id_admin(conv_id)
        assert resolved == "sess-cross-tenant"

    def test_admin_returns_none_for_missing_conv(self, tmp_path, monkeypatch):
        self._patch_store(monkeypatch, tmp_path)
        from server.stores.session_store import resolve_latest_session_id_admin

        assert resolve_latest_session_id_admin("conv-no-such") is None
