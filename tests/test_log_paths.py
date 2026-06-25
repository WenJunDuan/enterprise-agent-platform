from __future__ import annotations

from server.platform import paths


def test_app_server_log_path_uses_year_month_day_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "APP_SERVER_DIR", tmp_path)

    log_path = paths.app_server_log_path(stderr=False)

    assert log_path.name == "stdout.log"
    relative_parts = log_path.relative_to(tmp_path).parts
    assert len(relative_parts) == 4
    assert all(part.isdigit() for part in relative_parts[:3])
    assert [len(part) for part in relative_parts[:3]] == [4, 2, 2]


def test_latest_dated_log_path_prefers_year_month_day_layout(tmp_path):
    legacy = tmp_path / "20260624" / "stdout.log"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("legacy", encoding="utf-8")
    current = tmp_path / "2026" / "06" / "25" / "stdout.log"
    current.parent.mkdir(parents=True)
    current.write_text("current", encoding="utf-8")

    assert paths.latest_dated_log_path(tmp_path, "stdout.log") == current


def test_latest_dated_log_path_falls_back_to_legacy_compact_day(tmp_path):
    legacy = tmp_path / "20260624" / "stderr.log"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("legacy", encoding="utf-8")

    assert paths.latest_dated_log_path(tmp_path, "stderr.log") == legacy


def test_session_event_log_path_is_partitioned_by_tenant(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "SESSION_EVENT_DIR", tmp_path)

    log_path = paths.build_session_event_log_path(
        session_id="sess-abcdef123456",
        request_id="req-001",
        timestamp="2026-06-25T01:02:03+00:00",
        tenant="acme",
    )

    assert log_path.relative_to(tmp_path).parts[:4] == ("acme", "2026", "06", "25")
    assert log_path.name == "010203_req-001_sess-abc.jsonl"


def test_session_event_log_path_sanitizes_invalid_tenant_segment(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "SESSION_EVENT_DIR", tmp_path)

    log_path = paths.build_session_event_log_path(
        session_id="sess-abcdef123456",
        request_id="req-001",
        timestamp="2026-06-25T01:02:03+00:00",
        tenant="../evil",
    )

    first_segment = log_path.relative_to(tmp_path).parts[0]
    assert first_segment.startswith("tenant-")
    assert ".." not in log_path.parts
