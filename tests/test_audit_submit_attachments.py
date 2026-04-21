"""Regression tests for /audit/submit attachment handling.

Covers the two must-work cases for the multipart upload mode:
- zero attachments (pure form submission)
- one or more attachments

The guard that used to reject empty `files` lists has been removed; these
tests pin the behaviour so a future regression cannot silently restore it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import api as api_module


VALID_FORM = {
    "case_id": "TEST-CASE-001",
    "applicant_name": "测试人",
    "expense_type": "业务招待",
}

# 8-byte PNG signature + zero padding; passes _validate_upload_bytes (.png + non-empty).
PNG_BYTES = bytes.fromhex("89504E470D0A1A0A") + b"\x00" * 16


@pytest.fixture
def auth_headers() -> dict[str, str]:
    first_key = next(iter(api_module.TENANT_KEYS.values()))
    return {"Authorization": f"Bearer {first_key}"}


@pytest.fixture
def isolated_submissions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    submissions_root = tmp_path / "submissions"
    submissions_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(api_module, "SUBMISSION_ROOT_DIR", submissions_root)
    monkeypatch.setattr(api_module, "_schedule_directory_audit_task", lambda **kwargs: None)
    monkeypatch.setattr(api_module, "upsert_audit_task", lambda payload: None)
    monkeypatch.setattr(api_module, "recover_stale_audit_tasks", lambda timeout: None)
    return submissions_root


@pytest.fixture
def client() -> TestClient:
    return TestClient(api_module.app)


def _read_audit_request(submissions_root: Path, request_id: str) -> dict:
    path = submissions_root / request_id / "audit-request.json"
    assert path.exists(), f"audit-request.json missing at {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _multipart_body_without_files(form_payload: dict) -> tuple[bytes, str]:
    boundary = "test-boundary-no-files"
    lines = [
        f"--{boundary}",
        'Content-Disposition: form-data; name="mode"',
        "",
        "upload",
        f"--{boundary}",
        'Content-Disposition: form-data; name="form_json"',
        "",
        json.dumps(form_payload),
        f"--{boundary}--",
        "",
    ]
    body = "\r\n".join(lines).encode("utf-8")
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


def test_audit_submit_upload_without_files(
    client: TestClient,
    isolated_submissions: Path,
    auth_headers: dict[str, str],
) -> None:
    body, content_type = _multipart_body_without_files(VALID_FORM)

    response = client.post(
        "/audit/submit",
        content=body,
        headers={**auth_headers, "Content-Type": content_type},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["mode"] == "upload"

    audit_request = _read_audit_request(isolated_submissions, payload["request_id"])
    assert audit_request["attachments"] == []
    assert audit_request["form"]["case_id"] == VALID_FORM["case_id"]


def test_audit_submit_upload_with_multiple_files(
    client: TestClient,
    isolated_submissions: Path,
    auth_headers: dict[str, str],
) -> None:
    files = [
        ("files", ("receipt-a.png", PNG_BYTES, "image/png")),
        ("files", ("receipt-b.png", PNG_BYTES + b"\x01", "image/png")),
    ]
    data = {
        "mode": "upload",
        "form_json": json.dumps(VALID_FORM),
    }

    response = client.post(
        "/audit/submit",
        data=data,
        files=files,
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["mode"] == "upload"

    audit_request = _read_audit_request(isolated_submissions, payload["request_id"])
    attachments = audit_request["attachments"]
    assert len(attachments) == 2
    names = sorted(entry["name"] for entry in attachments)
    assert names == ["receipt-a.png", "receipt-b.png"]
    for entry in attachments:
        assert entry["type"] == "uploaded"
        assert entry["path"], "serialized path should not be empty"
