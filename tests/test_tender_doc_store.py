"""Tests for tender_doc_store (tender_project_docs + tender_bid_docs tables).

TDD: tests written before implementation. Each test validates CRUD operations,
tenant isolation, JSON fields, and OCR/criteria update operations.
"""

from __future__ import annotations

import json
import uuid


def _pid() -> str:
    return f"tp-{uuid.uuid4().hex[:16]}"


def _bid() -> str:
    return f"bid-{uuid.uuid4().hex[:8]}"


# ── tender_project_docs ──────────────────────────────────────────────────────


def test_upsert_and_get_project_doc():
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc

    pid = _pid()
    upsert_project_doc(
        project_id=pid,
        tenant="t1",
        tender_files=json.dumps(["a.pdf", "b.pdf"]),
    )
    row = get_project_doc(pid, "t1")
    assert row is not None
    assert row["project_id"] == pid
    assert row["tenant"] == "t1"
    assert row["ocr_status"] == "pending"
    assert json.loads(row["tender_files"]) == ["a.pdf", "b.pdf"]
    assert row["ocr_text"] is None
    assert row["criteria"] is None


def test_upsert_project_doc_is_idempotent():
    """Second upsert with same project_id replaces the row (INSERT OR REPLACE)."""
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc

    pid = _pid()
    upsert_project_doc(project_id=pid, tenant="t1", tender_files='["a.pdf"]')
    upsert_project_doc(project_id=pid, tenant="t1", tender_files='["a.pdf", "b.pdf"]')
    row = get_project_doc(pid, "t1")
    assert row is not None
    assert json.loads(row["tender_files"]) == ["a.pdf", "b.pdf"]


def test_get_project_doc_tenant_isolation():
    """tenant isolation: same project_id but different tenant returns None."""
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc

    pid = _pid()
    upsert_project_doc(project_id=pid, tenant="t-iso-a", tender_files="[]")
    assert get_project_doc(pid, "t-iso-b") is None
    assert get_project_doc(pid, "t-iso-a") is not None


def test_get_project_doc_missing_returns_none():
    from server.stores.tender_doc_store import get_project_doc

    assert get_project_doc("nonexistent-pid", "any-tenant") is None


def test_update_project_doc_ocr():
    from server.stores.tender_doc_store import (
        get_project_doc,
        update_project_doc_ocr,
        upsert_project_doc,
    )

    pid = _pid()
    upsert_project_doc(project_id=pid, tenant="t1", tender_files="[]", ocr_status="running")
    update_project_doc_ocr(pid, tenant="t1", ocr_text="底稿文本内容", ocr_clarity="clear", status="ready")
    row = get_project_doc(pid, "t1")
    assert row is not None
    assert row["ocr_text"] == "底稿文本内容"
    assert row["ocr_clarity"] == "clear"
    assert row["ocr_status"] == "ready"


def test_update_project_doc_ocr_failed():
    from server.stores.tender_doc_store import (
        get_project_doc,
        update_project_doc_ocr,
        upsert_project_doc,
    )

    pid = _pid()
    upsert_project_doc(project_id=pid, tenant="t1", tender_files="[]", ocr_status="running")
    update_project_doc_ocr(pid, tenant="t1", ocr_text=None, ocr_clarity=None, status="failed")
    row = get_project_doc(pid, "t1")
    assert row is not None
    assert row["ocr_status"] == "failed"
    assert row["ocr_text"] is None


def test_update_project_doc_criteria():
    from server.stores.tender_doc_store import (
        get_project_doc,
        update_project_doc_criteria,
        upsert_project_doc,
    )

    pid = _pid()
    upsert_project_doc(project_id=pid, tenant="t1", tender_files="[]")
    criteria = json.dumps([{"item": "技术评分", "max": 60}])
    update_project_doc_criteria(pid, "t1", criteria)
    row = get_project_doc(pid, "t1")
    assert row is not None
    assert row["criteria"] == criteria
    loaded = json.loads(row["criteria"])
    assert loaded[0]["item"] == "技术评分"


def test_upsert_project_doc_with_ocr_status_running():
    from server.stores.tender_doc_store import get_project_doc, upsert_project_doc

    pid = _pid()
    upsert_project_doc(project_id=pid, tenant="t1", tender_files="[]", ocr_status="running")
    row = get_project_doc(pid, "t1")
    assert row is not None
    assert row["ocr_status"] == "running"


# ── tender_bid_docs ──────────────────────────────────────────────────────────


def test_upsert_and_get_bid_doc():
    from server.stores.tender_doc_store import get_bid_doc, upsert_bid_doc

    pid = _pid()
    bid_id = _bid()
    upsert_bid_doc(
        project_id=pid,
        bid_id=bid_id,
        tenant="t1",
        bidder_name="华为技术",
        bid_files=json.dumps(["投标文件.pdf"]),
    )
    row = get_bid_doc(pid, bid_id, "t1")
    assert row is not None
    assert row["project_id"] == pid
    assert row["bid_id"] == bid_id
    assert row["bidder_name"] == "华为技术"
    assert row["ocr_status"] == "pending"
    assert row["ocr_text"] is None
    assert row["extracted"] is None


def test_upsert_bid_doc_composite_pk():
    """(project_id, bid_id) composite PK: same bid_id under different projects are different rows."""
    from server.stores.tender_doc_store import get_bid_doc, upsert_bid_doc

    pid_a = _pid()
    pid_b = _pid()
    bid_id = _bid()
    upsert_bid_doc(project_id=pid_a, bid_id=bid_id, tenant="t1", bidder_name="A", bid_files="[]")
    upsert_bid_doc(project_id=pid_b, bid_id=bid_id, tenant="t1", bidder_name="B", bid_files="[]")
    row_a = get_bid_doc(pid_a, bid_id, "t1")
    row_b = get_bid_doc(pid_b, bid_id, "t1")
    assert row_a is not None and row_a["bidder_name"] == "A"
    assert row_b is not None and row_b["bidder_name"] == "B"


def test_get_bid_doc_tenant_isolation():
    from server.stores.tender_doc_store import get_bid_doc, upsert_bid_doc

    pid = _pid()
    bid_id = _bid()
    upsert_bid_doc(
        project_id=pid, bid_id=bid_id, tenant="t-bid-a", bidder_name="X", bid_files="[]"
    )
    assert get_bid_doc(pid, bid_id, "t-bid-b") is None
    assert get_bid_doc(pid, bid_id, "t-bid-a") is not None


def test_list_bid_docs():
    from server.stores.tender_doc_store import list_bid_docs, upsert_bid_doc

    pid = _pid()
    bid1 = _bid()
    bid2 = _bid()
    upsert_bid_doc(project_id=pid, bid_id=bid1, tenant="t1", bidder_name="Alpha", bid_files="[]")
    upsert_bid_doc(project_id=pid, bid_id=bid2, tenant="t1", bidder_name="Beta", bid_files="[]")
    rows = list_bid_docs(pid, "t1")
    bid_ids = [r["bid_id"] for r in rows]
    assert bid1 in bid_ids
    assert bid2 in bid_ids


def test_list_bid_docs_tenant_isolation():
    from server.stores.tender_doc_store import list_bid_docs, upsert_bid_doc

    pid = _pid()
    upsert_bid_doc(project_id=pid, bid_id=_bid(), tenant="t-l-a", bidder_name="A", bid_files="[]")
    upsert_bid_doc(project_id=pid, bid_id=_bid(), tenant="t-l-b", bidder_name="B", bid_files="[]")
    rows_a = list_bid_docs(pid, "t-l-a")
    rows_b = list_bid_docs(pid, "t-l-b")
    assert len(rows_a) == 1 and rows_a[0]["bidder_name"] == "A"
    assert len(rows_b) == 1 and rows_b[0]["bidder_name"] == "B"


def test_update_bid_doc_ocr():
    from server.stores.tender_doc_store import get_bid_doc, update_bid_doc_ocr, upsert_bid_doc

    pid = _pid()
    bid_id = _bid()
    upsert_bid_doc(
        project_id=pid,
        bid_id=bid_id,
        tenant="t1",
        bidder_name="X",
        bid_files="[]",
        ocr_status="running",
    )
    update_bid_doc_ocr(pid, bid_id, tenant="t1", ocr_text="投标底稿内容", status="ready")
    row = get_bid_doc(pid, bid_id, "t1")
    assert row is not None
    assert row["ocr_text"] == "投标底稿内容"
    assert row["ocr_status"] == "ready"


def test_update_bid_doc_ocr_failed():
    from server.stores.tender_doc_store import get_bid_doc, update_bid_doc_ocr, upsert_bid_doc

    pid = _pid()
    bid_id = _bid()
    upsert_bid_doc(
        project_id=pid,
        bid_id=bid_id,
        tenant="t1",
        bidder_name="X",
        bid_files="[]",
        ocr_status="running",
    )
    update_bid_doc_ocr(pid, bid_id, tenant="t1", ocr_text=None, status="failed")
    row = get_bid_doc(pid, bid_id, "t1")
    assert row is not None
    assert row["ocr_status"] == "failed"


def test_update_bid_doc_extracted():
    from server.stores.tender_doc_store import (
        get_bid_doc,
        update_bid_doc_extracted,
        upsert_bid_doc,
    )

    pid = _pid()
    bid_id = _bid()
    upsert_bid_doc(project_id=pid, bid_id=bid_id, tenant="t1", bidder_name="X", bid_files="[]")
    extracted = json.dumps({"bidder": "华为", "price": 1000000})
    update_bid_doc_extracted(pid, bid_id, "t1", extracted)
    row = get_bid_doc(pid, bid_id, "t1")
    assert row is not None
    assert row["extracted"] == extracted


def test_list_bid_docs_empty():
    from server.stores.tender_doc_store import list_bid_docs

    assert list_bid_docs(_pid(), "t-empty") == []


def test_bid_doc_missing_returns_none():
    from server.stores.tender_doc_store import get_bid_doc

    assert get_bid_doc(_pid(), _bid(), "t1") is None
