"""Tests for tender upload endpoints:
  POST /tender/projects/{project_id}/tender-doc
  POST /tender/projects/{project_id}/bids
  GET  /tender/projects/{project_id}/docs-status

TDD: tests written before implementation.
"""

from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient

_TOKEN = "test-fake-token-acme-upload"
_AUTH = {"Authorization": f"Bearer {_TOKEN}"}


@pytest.fixture
def client(monkeypatch):
    """TestClient with patched tenant + no-op background tasks."""
    monkeypatch.setattr("server.routes.deps.TENANT_KEYS", {"acme": _TOKEN})
    import server.api as api_module
    import server.routes.deps as deps_module

    monkeypatch.setattr(deps_module, "tenant_keys_are_default", lambda: False)
    monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
    # Patch schedule_tender_evaluation_task to no-op (existing evaluate tests depend on it)
    monkeypatch.setattr(
        "server.routes.tender.tasks.schedule_tender_evaluation_task", lambda **kwargs: None
    )
    return TestClient(api_module.app)


def _make_project(client: TestClient, tender_no: str | None = None) -> str:
    tn = tender_no or f"R-{uuid.uuid4().hex[:8]}"
    resp = client.post("/tender/projects", json={"tender_no": tn}, headers=_AUTH)
    assert resp.status_code == 200, resp.text
    return resp.json()["project_id"]


def _pdf_file(name: str = "tender.pdf") -> tuple[str, tuple]:
    """Build a multipart file tuple with fake PDF content."""
    content = b"%PDF-1.4 fake tender document content"
    return ("files", (name, io.BytesIO(content), "application/pdf"))


# ── POST /tender/projects/{project_id}/tender-doc ────────────────────────────


def test_upload_tender_doc_returns_project_id_and_ocr_status(client, monkeypatch):
    """Successful upload returns {project_id, ocr_status}."""
    import server.routes.tender.docs as tender_module

    # Patch background OCR so test doesn't actually run OCR
    monkeypatch.setattr(
        tender_module, "_start_project_doc_ocr_task", lambda *a, **kw: None
    )

    pid = _make_project(client)
    resp = client.post(
        f"/tender/projects/{pid}/tender-doc",
        files=[_pdf_file("招标文件.pdf")],
        headers=_AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["project_id"] == pid
    assert body["ocr_status"] in {"pending", "running"}


def test_upload_tender_doc_unknown_project_returns_404(client, monkeypatch):
    import server.routes.tender.docs as tender_module

    monkeypatch.setattr(
        tender_module, "_start_project_doc_ocr_task", lambda *a, **kw: None
    )
    resp = client.post(
        "/tender/projects/nope-pid/tender-doc",
        files=[_pdf_file()],
        headers=_AUTH,
    )
    assert resp.status_code == 404


def test_upload_tender_doc_requires_auth(client):
    pid = _make_project(client)
    resp = client.post(f"/tender/projects/{pid}/tender-doc", files=[_pdf_file()])
    assert resp.status_code == 401


def test_upload_tender_doc_writes_to_store(client, monkeypatch):
    """After upload, tender_project_docs row exists with ocr_status running."""
    import server.routes.tender.docs as tender_module
    from server.stores.tender_doc_store import get_project_doc

    monkeypatch.setattr(
        tender_module, "_start_project_doc_ocr_task", lambda *a, **kw: None
    )

    pid = _make_project(client)
    resp = client.post(
        f"/tender/projects/{pid}/tender-doc",
        files=[_pdf_file("招标文件.pdf")],
        headers=_AUTH,
    )
    assert resp.status_code == 200, resp.text
    row = get_project_doc(pid, "acme")
    assert row is not None
    assert row["ocr_status"] == "running"


def test_upload_tender_doc_rejects_unsupported_or_spoofed_files(client, monkeypatch):
    import server.routes.tender.docs as tender_module

    monkeypatch.setattr(tender_module, "_start_project_doc_ocr_task", lambda *a, **kw: None)
    pid = _make_project(client)

    unsupported = client.post(
        f"/tender/projects/{pid}/tender-doc",
        files=[("files", ("绕过前端.exe", b"MZ fake executable", "application/octet-stream"))],
        headers=_AUTH,
    )
    spoofed = client.post(
        f"/tender/projects/{pid}/tender-doc",
        files=[("files", ("伪造.pdf", b"MZ fake executable", "application/pdf"))],
        headers=_AUTH,
    )

    assert unsupported.status_code == 400
    assert "Unsupported document format" in unsupported.json()["detail"]
    assert spoofed.status_code == 400
    assert "does not match" in spoofed.json()["detail"]


# ── POST /tender/projects/{project_id}/bids ───────────────────────────────────


def test_upload_bid_returns_bid_id_and_ocr_status(client, monkeypatch):
    import server.routes.tender.docs as tender_module

    monkeypatch.setattr(
        tender_module, "_start_bid_doc_ocr_task", lambda *a, **kw: None
    )

    pid = _make_project(client)
    resp = client.post(
        f"/tender/projects/{pid}/bids",
        data={"bidder_name": "华为技术"},
        files=[_pdf_file("投标文件.pdf")],
        headers=_AUTH,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "bid_id" in body
    assert body["bid_id"]
    assert body["ocr_status"] in {"pending", "running"}


def test_upload_bid_unknown_project_returns_404(client, monkeypatch):
    import server.routes.tender.docs as tender_module

    monkeypatch.setattr(
        tender_module, "_start_bid_doc_ocr_task", lambda *a, **kw: None
    )
    resp = client.post(
        "/tender/projects/nope-pid/bids",
        data={"bidder_name": "Alpha"},
        files=[_pdf_file()],
        headers=_AUTH,
    )
    assert resp.status_code == 404


def test_upload_bid_requires_auth(client):
    pid = _make_project(client)
    resp = client.post(
        f"/tender/projects/{pid}/bids",
        data={"bidder_name": "X"},
        files=[_pdf_file()],
    )
    assert resp.status_code == 401


def test_upload_bid_writes_to_store(client, monkeypatch):
    """After upload, tender_bid_docs row exists for project with running ocr_status."""
    import server.routes.tender.docs as tender_module
    from server.stores.tender_doc_store import list_bid_docs

    monkeypatch.setattr(
        tender_module, "_start_bid_doc_ocr_task", lambda *a, **kw: None
    )

    pid = _make_project(client)
    resp = client.post(
        f"/tender/projects/{pid}/bids",
        data={"bidder_name": "Beta Corp"},
        files=[_pdf_file("beta_bid.pdf")],
        headers=_AUTH,
    )
    assert resp.status_code == 200, resp.text
    bid_id = resp.json()["bid_id"]

    rows = list_bid_docs(pid, "acme")
    assert any(r["bid_id"] == bid_id for r in rows)
    row = next(r for r in rows if r["bid_id"] == bid_id)
    assert row["bidder_name"] == "Beta Corp"
    assert row["ocr_status"] == "running"


def test_upload_multiple_bids(client, monkeypatch):
    """Multiple bid uploads to same project each get unique bid_id."""
    import server.routes.tender.docs as tender_module

    monkeypatch.setattr(
        tender_module, "_start_bid_doc_ocr_task", lambda *a, **kw: None
    )

    pid = _make_project(client)
    bid_ids = set()
    for name in ["A公司", "B公司", "C公司"]:
        r = client.post(
            f"/tender/projects/{pid}/bids",
            data={"bidder_name": name},
            files=[_pdf_file(f"{name}.pdf")],
            headers=_AUTH,
        )
        assert r.status_code == 200, r.text
        bid_ids.add(r.json()["bid_id"])
    assert len(bid_ids) == 3  # all unique


# ── GET /tender/projects/{project_id}/docs-status ────────────────────────────


def test_docs_status_returns_structure(client, monkeypatch):
    """docs-status returns {tender_doc, bids} with expected fields."""
    import server.routes.tender.docs as tender_module

    monkeypatch.setattr(
        tender_module, "_start_project_doc_ocr_task", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        tender_module, "_start_bid_doc_ocr_task", lambda *a, **kw: None
    )

    pid = _make_project(client)

    # Upload tender-doc
    client.post(
        f"/tender/projects/{pid}/tender-doc",
        files=[_pdf_file()],
        headers=_AUTH,
    )

    # Upload a bid
    client.post(
        f"/tender/projects/{pid}/bids",
        data={"bidder_name": "Alpha"},
        files=[_pdf_file("alpha.pdf")],
        headers=_AUTH,
    )

    resp = client.get(f"/tender/projects/{pid}/docs-status", headers=_AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "tender_doc" in body
    assert "bids" in body
    assert isinstance(body["bids"], list)
    assert len(body["bids"]) == 1
    assert "ocr_status" in body["tender_doc"]
    assert "bid_id" in body["bids"][0]
    assert "bidder_name" in body["bids"][0]
    assert "ocr_status" in body["bids"][0]


def test_docs_status_no_doc_uploaded(client):
    """If no tender-doc uploaded yet, tender_doc is None."""
    pid = _make_project(client)
    resp = client.get(f"/tender/projects/{pid}/docs-status", headers=_AUTH)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tender_doc"] is None
    assert body["bids"] == []


def test_docs_status_unknown_project_returns_404(client):
    resp = client.get("/tender/projects/nope-pid/docs-status", headers=_AUTH)
    assert resp.status_code == 404


def test_docs_status_requires_auth(client):
    pid = _make_project(client)
    resp = client.get(f"/tender/projects/{pid}/docs-status")
    assert resp.status_code == 401
