from __future__ import annotations

from pathlib import Path
from typing import Any

from server.stores.result_store import (
    archive_result_payload,
    get_result_payload_by_request_id,
    get_result_record_by_request_id,
    list_result_records,
)


def _response(claim_id: str = "CLAIM-001", verdict: str = "approved") -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "verdict": verdict,
        "conclusion": "合规",
        "explanation": "材料齐全，符合规则。",
        "reasons": ["票据完整"],
        "policy_refs": ["expense.policy.001"],
        "risk_score": 5,
    }


def _archive(
    request_id: str,
    *,
    tenant: str = "tenantA",
    conversation_id: str = "conv-001",
    verdict: str = "approved",
) -> None:
    archive_result_payload(
        request_id=request_id,
        tenant=tenant,
        conversation_id=conversation_id,
        claude_session_id=None,
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="audit-result-v1",
        request_mode="upload",
        result_subtype="success",
        cost_usd=0.01,
        prompt_preview=None,
        response=_response(claim_id=request_id, verdict=verdict),
    )


def test_archive_and_get_record(isolated_local_layout: dict[str, Path]) -> None:
    _archive("req-rs-001")
    record = get_result_record_by_request_id("req-rs-001", tenant="tenantA")
    assert record is not None
    assert record["request_id"] == "req-rs-001"
    assert record["verdict"] == "approved"
    assert record["tenant"] == "tenantA"


def test_get_payload_by_request_id(isolated_local_layout: dict[str, Path]) -> None:
    _archive("req-rs-002")
    payload = get_result_payload_by_request_id("req-rs-002", tenant="tenantA")
    assert payload is not None
    assert payload["response"]["claim_id"] == "req-rs-002"


def test_get_payload_wrong_tenant_returns_none(isolated_local_layout: dict[str, Path]) -> None:
    _archive("req-rs-003", tenant="tenantA")
    assert get_result_payload_by_request_id("req-rs-003", tenant="tenantB") is None


def test_get_record_nonexistent_returns_none(isolated_local_layout: dict[str, Path]) -> None:
    assert get_result_record_by_request_id("does-not-exist", tenant="tenantA") is None


def test_list_records(isolated_local_layout: dict[str, Path]) -> None:
    for i in range(3):
        _archive(f"req-rs-list-{i:03d}", conversation_id="conv-list")
    records = list_result_records("tenantA", limit=10)
    ids = {r["request_id"] for r in records}
    assert {"req-rs-list-000", "req-rs-list-001", "req-rs-list-002"}.issubset(ids)


def test_list_records_verdict_filter(isolated_local_layout: dict[str, Path]) -> None:
    _archive("req-rs-approved", conversation_id="conv-filter", verdict="approved")
    _archive("req-rs-rejected", conversation_id="conv-filter", verdict="rejected")
    approved = list_result_records("tenantA", verdict="approved")
    assert all(r["verdict"] == "approved" for r in approved)
    rejected = list_result_records("tenantA", verdict="rejected")
    assert all(r["verdict"] == "rejected" for r in rejected)


def test_list_records_pagination(isolated_local_layout: dict[str, Path]) -> None:
    for i in range(5):
        _archive(f"req-rs-page-{i:03d}", conversation_id="conv-page")
    page1 = list_result_records("tenantA", limit=3, offset=0)
    page2 = list_result_records("tenantA", limit=3, offset=3)
    assert len(page1) == 3
    assert len(page2) >= 2
    assert {r["request_id"] for r in page1}.isdisjoint({r["request_id"] for r in page2})


def test_list_records_scoped_by_tenant(isolated_local_layout: dict[str, Path]) -> None:
    _archive("req-rs-ta", tenant="tenantA")
    _archive("req-rs-tb", tenant="tenantB")
    ids_a = {r["request_id"] for r in list_result_records("tenantA")}
    assert "req-rs-ta" in ids_a
    assert "req-rs-tb" not in ids_a
