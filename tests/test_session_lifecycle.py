from __future__ import annotations

import json
from pathlib import Path

from server.stores import session_store as session_store_module


def test_resume_session_id_reuses_previous_session(
    client,
    auth_headers,
    query_recorder,
) -> None:
    first = client.post(
        "/chat",
        json={"message": "first turn", "conversation_id": "conv-resume"},
        headers=auth_headers["tenantA"],
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()

    second = client.post(
        "/chat",
        json={
            "message": "second turn",
            "conversation_id": "conv-resume",
            "resume_session_id": first_payload["claude_session_id"],
        },
        headers=auth_headers["tenantA"],
    )
    assert second.status_code == 200, second.text

    assert query_recorder.calls[1]["resume"] == first_payload["claude_session_id"]


def test_fork_session_id_marks_fork_mode(
    client,
    auth_headers,
    query_recorder,
) -> None:
    first = client.post(
        "/chat",
        json={"message": "seed turn", "conversation_id": "conv-fork"},
        headers=auth_headers["tenantA"],
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()

    second = client.post(
        "/chat",
        json={
            "message": "fork turn",
            "conversation_id": "conv-fork",
            "fork_from_session_id": first_payload["claude_session_id"],
        },
        headers=auth_headers["tenantA"],
    )
    assert second.status_code == 200, second.text

    assert query_recorder.calls[1]["resume"] == first_payload["claude_session_id"]
    assert query_recorder.calls[1]["fork_session"] is True


def test_continue_recent_reuses_latest_session_and_echoes_request_id(
    client,
    auth_headers,
    isolated_local_layout: dict[str, Path],
    query_recorder,
) -> None:
    first = client.post(
        "/chat",
        json={"message": "first turn", "conversation_id": "conv-continue"},
        headers={**auth_headers["tenantA"], "X-Request-ID": "corr-123"},
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert first.headers["X-Request-ID"] == "corr-123"

    second = client.post(
        "/chat",
        json={
            "message": "continue turn",
            "conversation_id": "conv-continue",
            "continue_recent": True,
        },
        headers=auth_headers["tenantA"],
    )
    assert second.status_code == 200, second.text
    second_payload = second.json()

    assert query_recorder.calls[1]["continue_conversation"] is True
    assert second_payload["claude_session_id"] == first_payload["claude_session_id"]

    record = session_store_module.get_session_record_by_request_id(
        request_id=first_payload["request_id"],
        tenant="tenantA",
    )
    assert record is not None
    event_log = Path(str(record["log_file"]))
    assert event_log.exists()
    lines = [json.loads(line) for line in event_log.read_text(encoding="utf-8").splitlines()]
    assert all(line["request_id"] == first_payload["request_id"] for line in lines)
    assert all(line["tenant"] == "tenantA" for line in lines)
    assert all("session_id" in line for line in lines)
