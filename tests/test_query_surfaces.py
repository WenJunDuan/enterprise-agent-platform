from __future__ import annotations


REMOVED_HTTP_ROUTES = {
    "/chat",
    "/chat/stream",
    "/audit",
    "/init-rules",
    "/sessions",
    "/sessions/{session_id}/messages",
    "/conversations",
    "/requests",
    "/requests/{request_id}",
    "/results",
    "/results/{request_id}",
    "/memories",
    "/memories/{memory_id}",
    "/review-deltas",
    "/review-deltas/{request_id}",
    "/governance/assets",
}


def test_http_api_does_not_expose_cli_query_or_governance_routes(client) -> None:
    paths = {route.path for route in client.app.routes}

    for path in REMOVED_HTTP_ROUTES:
        assert path not in paths


def test_audit_task_status_returns_compact_business_payload(
    client,
    auth_headers,
) -> None:
    request_id = "req-task-public-1"
    client.app.dependency_overrides = {}

    from server.stores.audit_task_store import upsert_audit_task

    upsert_audit_task(
        {
            "request_id": request_id,
            "tenant": "tenantA",
            "status": "running",
            "mode": "upload",
            "source_mode": "upload",
            "case_path": "data/submissions/req-task-public-1",
            "claim_id": None,
            "result_file": "logs/results/by-request/x.json",
            "session_id": "sess-task-1",
            "error_detail": None,
            "progress_message": "正在调用 Claude 审核",
            "submitted_at": "2026-04-22T03:10:00+00:00",
            "started_at": "2026-04-22T03:10:05+00:00",
            "finished_at": None,
            "updated_at": "2026-04-22T03:10:05+00:00",
        }
    )

    response = client.get(f"/audit/tasks/{request_id}", headers=auth_headers["tenantA"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "request_id": request_id,
        "status": "running",
        "mode": "upload",
        "claim_id": None,
        "error_detail": None,
        "progress_message": "正在调用 Claude 审核",
        "submitted_at": "2026-04-22T03:10:00+00:00",
        "started_at": "2026-04-22T03:10:05+00:00",
        "finished_at": None,
        "updated_at": "2026-04-22T03:10:05+00:00",
    }


def test_audit_task_missing_returns_structured_error(
    client,
    auth_headers,
) -> None:
    response = client.get("/audit/tasks/req-missing", headers=auth_headers["tenantA"])

    assert response.status_code == 404, response.text
    body = response.json()
    assert body["detail"] == "Audit task not found"
    assert body["error"] == {
        "code": "not_found",
        "message": "Audit task not found",
        "status_code": 404,
        "path": "/audit/tasks/req-missing",
        "correlation_id": response.headers["X-Request-ID"],
    }


def test_validation_errors_include_structured_error_payload(
    client,
    auth_headers,
) -> None:
    response = client.post(
        "/audit/submit",
        json={},
        headers=auth_headers["tenantA"],
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert isinstance(body["detail"], list)
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Request validation failed"
    assert body["error"]["status_code"] == 422
    assert body["error"]["path"] == "/audit/submit"
    assert body["error"]["correlation_id"] == response.headers["X-Request-ID"]
    assert body["error"]["details"] == body["detail"]
