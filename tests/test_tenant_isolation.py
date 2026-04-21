from __future__ import annotations

import asyncio
from pathlib import Path

from server import api as api_module
from server.stores import session_store as session_store_module

import pytest


def test_tenant_b_cannot_see_tenant_a_records(
    client,
    auth_headers,
    query_recorder,
    isolated_local_layout: dict[str, Path],
) -> None:
    chat_response = client.post(
        "/chat",
        json={"message": "tenant A seed", "conversation_id": "conv-tenant-a"},
        headers=auth_headers["tenantA"],
    )
    assert chat_response.status_code == 200, chat_response.text
    chat_payload = chat_response.json()

    case_dir = isolated_local_layout["project_root"] / "data" / "case-a"
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "receipt.txt").write_text("tenant A audit input", encoding="utf-8")

    submit_response = client.post(
        "/audit/submit",
        json={"mode": "directory", "directory_path": str(case_dir)},
        headers=auth_headers["tenantA"],
    )
    assert submit_response.status_code == 200, submit_response.text
    submit_payload = submit_response.json()

    asyncio.run(
        api_module._execute_directory_audit_task(
            request_id=submit_payload["request_id"],
            tenant="tenantA",
            directory_path=str(case_dir.relative_to(isolated_local_layout["project_root"])),
            source_mode="directory",
        )
    )

    sessions = client.get("/sessions", headers=auth_headers["tenantB"])
    assert sessions.status_code == 200, sessions.text
    assert chat_payload["claude_session_id"] not in sessions.text

    conversations = client.get("/conversations", headers=auth_headers["tenantB"])
    assert conversations.status_code == 200, conversations.text
    assert chat_payload["conversation_id"] not in conversations.text

    requests = client.get("/requests", headers=auth_headers["tenantB"])
    assert requests.status_code == 200, requests.text
    assert chat_payload["request_id"] not in requests.text
    assert submit_payload["request_id"] not in requests.text

    results = client.get("/results", headers=auth_headers["tenantB"])
    assert results.status_code == 200, results.text
    assert chat_payload["request_id"] not in results.text
    assert submit_payload["request_id"] not in results.text

    request_detail = client.get(
        f"/requests/{chat_payload['request_id']}",
        headers=auth_headers["tenantB"],
    )
    assert request_detail.status_code == 404

    result_detail = client.get(
        f"/results/{submit_payload['request_id']}",
        headers=auth_headers["tenantB"],
    )
    assert result_detail.status_code == 404

    task_detail = client.get(
        f"/audit/tasks/{submit_payload['request_id']}",
        headers=auth_headers["tenantB"],
    )
    assert task_detail.status_code == 404

    task_result = client.get(
        f"/audit/tasks/{submit_payload['request_id']}/result",
        headers=auth_headers["tenantB"],
    )
    assert task_result.status_code == 404

    messages = client.get(
        f"/sessions/{chat_payload['claude_session_id']}/messages",
        headers=auth_headers["tenantB"],
    )
    assert messages.status_code in {403, 404}


def test_session_store_public_reads_require_explicit_tenant() -> None:
    with pytest.raises(TypeError):
        session_store_module.load_session_records()

    with pytest.raises(TypeError):
        session_store_module.list_logged_sessions()

    with pytest.raises(TypeError):
        session_store_module.resolve_latest_session_id("conv-1")
