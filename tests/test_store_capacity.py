from __future__ import annotations

import logging
from pathlib import Path

import pytest

from server.platform import config as config_module
from server.stores.request_store import JSONLRequestAuditStore, RequestAuditRecord
from server.stores.session_store import JSONLSessionStore, SessionRecord


def test_session_store_warns_when_shard_limit_is_exceeded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    config_module.get_app_settings.cache_clear()
    monkeypatch.setenv("SESSION_STORE_MAX_SHARD_BYTES", "1")
    monkeypatch.setenv("SESSION_STORE_MAX_SHARDS", "1")
    caplog.set_level(logging.WARNING)
    store = JSONLSessionStore(tmp_path / "sessions")

    record = SessionRecord(
        request_id="req-1",
        conversation_id="conv-1",
        claude_session_id="session-1",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=None,
        request_mode="structured",
        prompt_preview="x" * 32,
        log_file="logs/session.jsonl",
        status="success",
        result_subtype="success",
        cost_usd=0.01,
        started_at="2026-04-20T00:00:00+00:00",
        finished_at="2026-04-20T00:00:01+00:00",
        tenant="tenantA",
        result_file=None,
    )

    store.append_record(record)

    assert "store capacity warning" in caplog.text
    assert any((tmp_path / "sessions").glob("*.jsonl"))


def test_request_store_warns_when_shard_limit_is_exceeded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    config_module.get_app_settings.cache_clear()
    monkeypatch.setenv("SESSION_STORE_MAX_SHARD_BYTES", "1")
    monkeypatch.setenv("SESSION_STORE_MAX_SHARDS", "1")
    caplog.set_level(logging.WARNING)
    store = JSONLRequestAuditStore(tmp_path / "requests")

    store.append_record(
        RequestAuditRecord(
            request_id="req-1",
            route="/chat",
            method="POST",
            status_code=200,
            status="success",
            duration_ms=1,
            created_at="2026-04-20T00:00:00+00:00",
            tenant="tenantA",
            conversation_id="conv-1",
            claude_session_id="session-1",
            prompt_preview="x" * 32,
        )
    )

    assert "store capacity warning" in caplog.text
    assert any((tmp_path / "requests").glob("*.jsonl"))
