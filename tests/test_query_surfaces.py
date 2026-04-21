from __future__ import annotations

import json
from pathlib import Path

from server.stores import memory_store as memory_store_module
from server.stores import review_delta_store as review_delta_store_module
from server.stores import result_store as result_store_module


def test_requests_endpoint_supports_route_and_status_filters(
    client,
    auth_headers,
    query_recorder,
) -> None:
    response = client.post(
        "/chat",
        json={"message": "seed request", "conversation_id": "conv-requests"},
        headers=auth_headers["tenantA"],
    )
    assert response.status_code == 200, response.text

    filtered = client.get(
        "/requests",
        params={"route": "/chat", "status": "success"},
        headers=auth_headers["tenantA"],
    )
    assert filtered.status_code == 200, filtered.text
    body = filtered.json()
    items = body["items"]
    assert len(items) == 1
    assert items[0]["route"] == "/chat"
    assert items[0]["status"] == "success"
    assert body["meta"] == {
        "limit": 20,
        "offset": 0,
        "returned": 1,
        "filters": {"route": "/chat", "status": "success"},
    }

    sessions = client.get(
        "/sessions",
        params={"conversation_id": "conv-requests"},
        headers=auth_headers["tenantA"],
    )
    assert sessions.status_code == 200, sessions.text
    session_body = sessions.json()
    assert len(session_body["logged_sessions"]) == 1
    assert session_body["meta"]["limit"] == 20
    assert session_body["meta"]["offset"] == 0
    assert session_body["meta"]["returned"] == 1
    assert session_body["meta"]["filters"] == {"conversation_id": "conv-requests"}
    assert session_body["meta"]["sdk_returned"] == len(session_body["sdk_sessions"])


def test_results_endpoint_supports_manual_review_reason_and_links_memory(
    client,
    auth_headers,
    isolated_local_layout: dict[str, Path],
) -> None:
    payload = {
        "claim_id": "EXP-QUERY-001",
        "verdict": "manual_review",
        "result": False,
        "conclusion": "待人工复核",
        "explanation": "缺少事前申请。",
        "reasons": ["缺少事前申请"],
        "policy_refs": ["expense.travel.016"],
        "risk_score": 80,
        "extracted_data": {"category": "travel"},
        "evidence_chain": [
            {"source": "doc:audit-request.json", "finding": "缺少申请单", "conclusion": "证据不足"}
        ],
        "reviewed_by": "expense-auditor",
        "timestamp": "2026-04-21T10:00:00+08:00",
        "manual_review_reason": "pre_approval_mismatch",
    }
    record = result_store_module.archive_result_payload(
        request_id="req-query-1",
        tenant="tenantA",
        conversation_id="conv-query-1",
        claude_session_id="sess-query-1",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="common/audit-result.schema.json",
        request_mode="structured",
        result_subtype="success",
        cost_usd=0.1,
        prompt_preview="/audit tests/fixtures/x",
        response=payload,
        created_at="2026-04-21T02:00:00+00:00",
    )

    memory_payload = {
        "memory_id": "expense.travel.pre-approval-mismatch.manual-review.v1",
        "domain": "expense",
        "memory_type": "exception_pattern",
        "title": "差旅报销：事前申请缺失",
        "summary": "示例摘要",
        "category": "travel",
        "applicable_when": ["缺少出差申请单"],
        "checkpoints": ["检查事前申请"],
        "policy_refs": ["expense.travel.016"],
        "recommended_verdict": "manual_review",
        "manual_review_reason": "pre_approval_mismatch",
        "rationale": "示例原因",
        "tags": ["travel"],
        "source_trace": {
            "request_id": "req-query-1",
            "result_file": record.result_file,
            "claim_id": "EXP-QUERY-001",
            "conversation_id": "conv-query-1",
            "claude_session_id": "sess-query-1",
            "review_delta_file": None,
        },
        "distilled_by": "system-memory-distill",
        "distilled_at": "2026-04-21T10:30:00+08:00",
    }
    memory_path = (
        isolated_local_layout["memory_root"]
        / "expense"
        / "expense.travel.pre-approval-mismatch.manual-review.v1.json"
    )
    memory_path.write_text(json.dumps(memory_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    memory_store_module.MEMORY_STORE.refresh_index()

    filtered = client.get(
        "/results",
        params={"manual_review_reason": "pre_approval_mismatch"},
        headers=auth_headers["tenantA"],
    )
    assert filtered.status_code == 200, filtered.text
    body = filtered.json()
    items = body["items"]
    assert len(items) == 1
    assert items[0]["request_id"] == "req-query-1"
    assert body["meta"] == {
        "limit": 20,
        "offset": 0,
        "returned": 1,
        "filters": {"manual_review_reason": "pre_approval_mismatch"},
    }

    detail = client.get("/results/req-query-1", headers=auth_headers["tenantA"])
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["record"]["manual_review_reason"] == "pre_approval_mismatch"
    assert len(body["linked_memories"]) == 1
    assert body["linked_memories"][0]["memory_id"] == memory_payload["memory_id"]


def test_memories_endpoints_list_and_detail(
    client,
    auth_headers,
    isolated_local_layout: dict[str, Path],
) -> None:
    memory_payload = {
        "memory_id": "expense.entertainment.budget-exceeded.manual-review.v1",
        "domain": "expense",
        "memory_type": "exception_pattern",
        "title": "招待费预算超额模式",
        "summary": "示例摘要",
        "category": "entertainment",
        "applicable_when": ["预算超额"],
        "checkpoints": ["检查预算"],
        "policy_refs": ["expense.entertainment.003"],
        "recommended_verdict": "manual_review",
        "manual_review_reason": "budget_exceeded",
        "rationale": "示例原因",
        "tags": ["entertainment", "budget"],
        "source_trace": {
            "request_id": "req-memory-1",
            "result_file": "results/by-request/2026/04/21/req-memory-1.json",
            "claim_id": "EXP-MEMORY-001",
            "conversation_id": "conv-memory-1",
            "claude_session_id": "sess-memory-1",
            "review_delta_file": None,
        },
        "distilled_by": "system-memory-distill",
        "distilled_at": "2026-04-21T11:00:00+08:00",
    }
    memory_path = (
        isolated_local_layout["memory_root"]
        / "expense"
        / "expense.entertainment.budget-exceeded.manual-review.v1.json"
    )
    memory_path.write_text(json.dumps(memory_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    memory_store_module.MEMORY_STORE.refresh_index()

    listing = client.get(
        "/memories",
        params={"domain": "expense", "manual_review_reason": "budget_exceeded"},
        headers=auth_headers["tenantA"],
    )
    assert listing.status_code == 200, listing.text
    body = listing.json()
    items = body["items"]
    assert len(items) == 1
    assert items[0]["memory_id"] == memory_payload["memory_id"]
    assert body["meta"] == {
        "limit": 20,
        "offset": 0,
        "returned": 1,
        "filters": {
            "domain": "expense",
            "manual_review_reason": "budget_exceeded",
        },
    }

    detail = client.get(
        f"/memories/{memory_payload['memory_id']}",
        headers=auth_headers["tenantA"],
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["payload"]["manual_review_reason"] == "budget_exceeded"


def test_review_delta_endpoints_and_result_detail_link(
    client,
    auth_headers,
) -> None:
    payload = {
        "claim_id": "EXP-REVIEW-001",
        "initial_verdict": "approved",
        "reviewer_verdict": "manual_review",
        "agrees_with_initial": False,
        "escalation_recommended": True,
        "confirmed_points": ["票据金额一致"],
        "disagreement_points": [
            {
                "field": "pre_approval",
                "initial_assessment": "初审认为材料足够",
                "reviewer_assessment": "复核认为缺少事前申请",
                "evidence_basis": "未找到申请单",
            }
        ],
        "additional_policy_refs": ["expense.travel.016"],
        "additional_evidence_chain": [
            {
                "source": "rule:expense.travel.016",
                "finding": "事后补提不予报销",
                "conclusion": "需升级人工复核",
            }
        ],
        "final_recommendation": "manual_review",
        "explanation": "复核发现缺少事前申请。",
        "reviewed_by": "expense-reviewer",
        "timestamp": "2026-04-21T12:00:00+08:00",
    }
    review_delta_store_module.archive_review_delta_payload(
        request_id="req-review-1",
        tenant="tenantA",
        conversation_id="conv-review-1",
        claude_session_id="sess-review-1",
        payload=payload,
        created_at="2026-04-21T04:00:00+00:00",
    )

    listing = client.get(
        "/review-deltas",
        params={"claim_id": "EXP-REVIEW-001", "final_recommendation": "manual_review"},
        headers=auth_headers["tenantA"],
    )
    assert listing.status_code == 200, listing.text
    body = listing.json()
    items = body["items"]
    assert len(items) == 1
    assert items[0]["request_id"] == "req-review-1"
    assert body["meta"] == {
        "limit": 20,
        "offset": 0,
        "returned": 1,
        "filters": {
            "claim_id": "EXP-REVIEW-001",
            "final_recommendation": "manual_review",
        },
    }

    detail = client.get("/review-deltas/req-review-1", headers=auth_headers["tenantA"])
    assert detail.status_code == 200, detail.text
    assert detail.json()["payload"]["claim_id"] == "EXP-REVIEW-001"


def test_governance_assets_endpoint_returns_validation_report(
    client,
    auth_headers,
) -> None:
    response = client.get("/governance/assets", headers=auth_headers["tenantA"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert "rules" in body
    assert "memory" in body


def test_error_responses_include_structured_error_with_legacy_detail(
    client,
    auth_headers,
) -> None:
    response = client.get("/results/req-missing", headers=auth_headers["tenantA"])

    assert response.status_code == 404, response.text
    body = response.json()
    assert body["detail"] == "Result not found"
    assert body["error"] == {
        "code": "not_found",
        "message": "Result not found",
        "status_code": 404,
        "path": "/results/req-missing",
        "correlation_id": response.headers["X-Request-ID"],
    }


def test_validation_errors_include_structured_error_payload(
    client,
    auth_headers,
) -> None:
    response = client.post(
        "/chat",
        json={
            "message": "hello",
            "resume_session_id": "sess-1",
            "fork_from_session_id": "sess-2",
        },
        headers=auth_headers["tenantA"],
    )

    assert response.status_code == 422, response.text
    body = response.json()
    assert isinstance(body["detail"], list)
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "Request validation failed"
    assert body["error"]["status_code"] == 422
    assert body["error"]["path"] == "/chat"
    assert body["error"]["correlation_id"] == response.headers["X-Request-ID"]
    assert body["error"]["details"] == body["detail"]
