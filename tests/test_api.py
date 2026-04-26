from __future__ import annotations

import json
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from server import api as api_module


@pytest.fixture
def api_client(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setattr(api_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setattr(
        api_module,
        "collect_runtime_diagnostics",
        lambda: {"status": "ok", "checks": {}, "advisories": []},
    )
    return client


BEARER_A = "Bearer sk-A"
FORM_JSON = json.dumps({"case_id": "C001", "applicant_name": "张三", "expense_type": "差旅"})
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_health_returns_200(api_client: TestClient) -> None:
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_submit_missing_auth_header_returns_422(api_client: TestClient) -> None:
    response = api_client.post(
        "/audit/submit",
        content=json.dumps({"mode": "directory", "directory_path": "/tmp"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_submit_unsupported_content_type_returns_415(api_client: TestClient) -> None:
    response = api_client.post(
        "/audit/submit",
        content=b"plain",
        headers={"Authorization": BEARER_A, "Content-Type": "text/plain"},
    )
    assert response.status_code == 415


def test_submit_multipart_missing_form_json_returns_400(api_client: TestClient) -> None:
    response = api_client.post(
        "/audit/submit",
        data={"mode": "upload"},
        files={"files": ("receipt.png", BytesIO(PNG_BYTES), "image/png")},
        headers={"Authorization": BEARER_A},
    )
    assert response.status_code == 400


def test_submit_urlencoded_without_files_returns_415(api_client: TestClient) -> None:
    response = api_client.post(
        "/audit/submit",
        data={"mode": "upload", "form_json": FORM_JSON},
        headers={"Authorization": BEARER_A},
    )
    assert response.status_code == 415


def test_submit_multipart_valid_returns_200(api_client: TestClient) -> None:
    form = json.dumps({"case_id": "C002", "applicant_name": "李四", "expense_type": "餐饮"})
    response = api_client.post(
        "/audit/submit",
        data={"mode": "upload", "form_json": form},
        files={"files": ("receipt.png", BytesIO(PNG_BYTES), "image/png")},
        headers={"Authorization": BEARER_A},
    )
    assert response.status_code == 200
    body = response.json()
    assert "request_id" in body
    assert body["status"] == "accepted"
    assert body["mode"] == "upload"
    assert "/audit/tasks/" in body["task_status_url"]


def test_list_tasks_returns_200_and_list(api_client: TestClient) -> None:
    response = api_client.get("/audit/tasks", headers={"Authorization": BEARER_A})
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_tasks_status_filter(api_client: TestClient) -> None:
    response = api_client.get(
        "/audit/tasks",
        params={"status": "running", "limit": 5, "offset": 0},
        headers={"Authorization": BEARER_A},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert all(r["status"] == "running" for r in data)


def test_list_tasks_pagination_params(api_client: TestClient) -> None:
    response = api_client.get(
        "/audit/tasks",
        params={"limit": 2, "offset": 100},
        headers={"Authorization": BEARER_A},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_task_detail_not_found_returns_404(api_client: TestClient) -> None:
    response = api_client.get(
        "/audit/tasks/nonexistent-request-id",
        headers={"Authorization": BEARER_A},
    )
    assert response.status_code == 404


def test_task_detail_found_returns_200(api_client: TestClient) -> None:
    form = json.dumps({"case_id": "C003", "applicant_name": "王五", "expense_type": "交通"})
    submit = api_client.post(
        "/audit/submit",
        data={"mode": "upload", "form_json": form},
        files={"files": ("receipt.png", BytesIO(PNG_BYTES), "image/png")},
        headers={"Authorization": BEARER_A},
    )
    assert submit.status_code == 200
    request_id = submit.json()["request_id"]

    detail = api_client.get(f"/audit/tasks/{request_id}", headers={"Authorization": BEARER_A})
    assert detail.status_code == 200
    body = detail.json()
    assert body["request_id"] == request_id
    assert body["status"] in {"accepted", "running", "completed", "failed"}


def test_invalid_api_key_returns_401(api_client: TestClient) -> None:
    response = api_client.get(
        "/audit/tasks",
        headers={"Authorization": "Bearer wrong-key"},
    )
    assert response.status_code == 401
