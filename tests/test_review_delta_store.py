from __future__ import annotations

from pathlib import Path

from server.stores import review_delta_store as review_delta_store_module


def test_sqlite_review_delta_store_archives_and_queries_payload(tmp_path: Path) -> None:
    archive_root = tmp_path / "reviews" / "by-request"
    store = review_delta_store_module.SQLiteReviewDeltaStore(
        db_path=tmp_path / "reviews" / "index.sqlite3",
        archive_root=archive_root,
    )
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
                "initial_assessment": "初审认为现有材料足够",
                "reviewer_assessment": "复核认为缺少事前申请",
                "evidence_basis": "未找到有效申请单",
            }
        ],
        "additional_policy_refs": ["expense.travel.016"],
        "additional_evidence_chain": [
            {
                "source": "rule:expense.travel.016",
                "finding": "事后补提申请不予报销",
                "conclusion": "需升级人工复核",
            }
        ],
        "final_recommendation": "manual_review",
        "explanation": "复核发现初审遗漏了事前申请缺失这一关键条件。",
        "reviewed_by": "expense-reviewer",
        "timestamp": "2026-04-21T12:00:00+08:00",
    }

    record = review_delta_store_module.archive_review_delta_payload(
        request_id="req-review-1",
        tenant="tenantA",
        conversation_id="conv-review-1",
        claude_session_id="sess-review-1",
        payload=payload,
        created_at="2026-04-21T04:00:00+00:00",
        store=store,
    )

    assert record.request_id == "req-review-1"
    loaded = store.get_record_by_request_id("req-review-1", tenant="tenantA")
    assert loaded is not None
    assert loaded["final_recommendation"] == "manual_review"
    items = store.list_records(tenant="tenantA", claim_id="EXP-REVIEW-001")
    assert len(items) == 1
    detail = store.get_payload_by_request_id("req-review-1", tenant="tenantA")
    assert detail == payload

