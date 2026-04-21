"""Tests for audit-result schema semantic validation in server.core."""

from __future__ import annotations

import pytest

from server.core import (
    DEFAULT_OUTPUT_SCHEMA_NAME,
    JSONContractError,
    validate_structured_output_semantics,
)


def _approved_payload() -> dict:
    return {
        "claim_id": "C001",
        "verdict": "approved",
        "result": True,
        "conclusion": "合规",
        "explanation": "全部条件符合",
        "reasons": ["发票齐全"],
        "policy_refs": ["expense.travel.001"],
        "risk_score": 10,
        "extracted_data": {},
        "evidence_chain": [],
        "reviewed_by": "system",
        "timestamp": "2026-04-20T00:00:00Z",
    }


def _manual_review_payload() -> dict:
    payload = _approved_payload()
    payload.update(
        verdict="manual_review",
        result=False,
        conclusion="待人工复核",
        explanation="缺少审批节点",
    )
    return payload


def test_legacy_approved_payload_without_new_fields_passes():
    validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, _approved_payload())


def test_manual_review_with_valid_reason_passes():
    payload = _manual_review_payload()
    payload["manual_review_reason"] = "missing_approval"
    validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_manual_review_without_reason_raises():
    payload = _manual_review_payload()
    with pytest.raises(JSONContractError):
        validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_manual_review_with_invalid_reason_raises():
    payload = _manual_review_payload()
    payload["manual_review_reason"] = "not_a_real_reason"
    with pytest.raises(JSONContractError):
        validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_valid_risk_dimensions_pass():
    payload = _approved_payload()
    payload["risk_dimensions"] = [
        {"name": "invoice", "score": 3},
        {"name": "amount", "score": 0},
        {"name": "anomaly", "score": 10},
    ]
    validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_risk_dimensions_not_a_list_raises():
    payload = _approved_payload()
    payload["risk_dimensions"] = {"name": "invoice", "score": 3}
    with pytest.raises(JSONContractError):
        validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_risk_dimension_score_out_of_upper_bound_raises():
    payload = _approved_payload()
    payload["risk_dimensions"] = [{"name": "invoice", "score": 11}]
    with pytest.raises(JSONContractError):
        validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_risk_dimension_score_negative_raises():
    payload = _approved_payload()
    payload["risk_dimensions"] = [{"name": "invoice", "score": -1}]
    with pytest.raises(JSONContractError):
        validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_risk_dimension_unknown_name_raises():
    payload = _approved_payload()
    payload["risk_dimensions"] = [{"name": "unknown", "score": 5}]
    with pytest.raises(JSONContractError):
        validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_risk_dimension_non_integer_score_raises():
    payload = _approved_payload()
    payload["risk_dimensions"] = [{"name": "invoice", "score": 5.5}]
    with pytest.raises(JSONContractError):
        validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_risk_dimension_item_not_an_object_raises():
    payload = _approved_payload()
    payload["risk_dimensions"] = ["invoice:3"]
    with pytest.raises(JSONContractError):
        validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_approved_with_manual_review_reason_field_still_passes():
    # 向后兼容：非 manual_review 的 payload 含 manual_review_reason 字段也不应抛错
    payload = _approved_payload()
    payload["manual_review_reason"] = "missing_approval"
    validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)
