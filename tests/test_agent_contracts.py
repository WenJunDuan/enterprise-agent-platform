from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACTS_ROOT = PROJECT_ROOT / ".claude" / "contracts" / "expense"
AGENTS_ROOT = PROJECT_ROOT / ".claude" / "agents" / "expense"


def _load_schema(name: str) -> dict:
    return json.loads((CONTRACTS_ROOT / name).read_text(encoding="utf-8"))


def test_extract_result_schema_accepts_valid_payload() -> None:
    schema = _load_schema("extract-result.schema.json")
    payload = {
        "claim_id": "EXP-2026-001",
        "source_path": "data/case-expense-001",
        "applicant": {
            "name": "张三",
            "employee_id": "E-001",
            "department": "销售部",
        },
        "expense": {
            "category": "travel",
            "amount": 1280.5,
            "currency": "CNY",
            "date": "2026-04-21",
            "description": "上海差旅报销",
        },
        "invoice_numbers": ["INV-001", "INV-002"],
        "attachments": [
            {
                "name": "audit-request.json",
                "path": "data/case-expense-001/audit-request.json",
                "media_type": "application/json",
                "document_type": "application_form",
            },
            {
                "name": "invoice-001.pdf",
                "path": "data/case-expense-001/invoice-001.pdf",
                "media_type": "application/pdf",
                "document_type": "invoice",
            },
        ],
        "extracted_fields": ["claim_id", "applicant.name", "expense.amount", "invoice_numbers"],
        "missing_fields": [],
        "ambiguities": [],
        "reviewed_by": "expense-extractor",
        "timestamp": "2026-04-21T08:00:00+08:00",
    }

    validate(payload, schema)


def test_extract_result_schema_rejects_business_verdict_fields() -> None:
    schema = _load_schema("extract-result.schema.json")
    payload = {
        "claim_id": "EXP-2026-001",
        "source_path": "data/case-expense-001",
        "applicant": {
            "name": "张三",
            "employee_id": None,
            "department": None,
        },
        "expense": {
            "category": "travel",
            "amount": 1280.5,
            "currency": "CNY",
            "date": "2026-04-21",
            "description": "上海差旅报销",
        },
        "invoice_numbers": [],
        "attachments": [],
        "extracted_fields": ["claim_id"],
        "missing_fields": [],
        "ambiguities": [],
        "reviewed_by": "expense-extractor",
        "timestamp": "2026-04-21T08:00:00+08:00",
        "verdict": "approved",
    }

    with pytest.raises(ValidationError):
        validate(payload, schema)


def test_review_delta_schema_accepts_valid_payload() -> None:
    schema = _load_schema("review-delta.schema.json")
    payload = {
        "claim_id": "EXP-2026-001",
        "initial_verdict": "approved",
        "reviewer_verdict": "manual_review",
        "agrees_with_initial": False,
        "escalation_recommended": True,
        "confirmed_points": ["票据金额与申请金额一致"],
        "disagreement_points": [
            {
                "field": "pre_approval",
                "initial_assessment": "初审认为现有材料可视为满足要求",
                "reviewer_assessment": "复核认为缺少可追溯的事前申请记录",
                "evidence_basis": "未发现有效的事前审批附件或审批号",
            }
        ],
        "additional_policy_refs": ["expense.travel.012"],
        "additional_evidence_chain": [
            {
                "source": "rule:expense.travel.012",
                "finding": "差旅报销需提供有效事前申请记录",
                "conclusion": "当前材料无法闭合规则要求",
            }
        ],
        "final_recommendation": "manual_review",
        "explanation": "复核发现初审遗漏了事前申请缺失这一关键条件，建议升级为人工复核。",
        "reviewed_by": "expense-reviewer",
        "timestamp": "2026-04-21T09:00:00+08:00",
    }

    validate(payload, schema)


def test_review_delta_schema_requires_disagreement_points_when_reviewer_disagrees() -> None:
    schema = _load_schema("review-delta.schema.json")
    payload = {
        "claim_id": "EXP-2026-001",
        "initial_verdict": "approved",
        "reviewer_verdict": "manual_review",
        "agrees_with_initial": False,
        "escalation_recommended": True,
        "confirmed_points": [],
        "disagreement_points": [],
        "additional_policy_refs": ["expense.travel.012"],
        "additional_evidence_chain": [],
        "final_recommendation": "manual_review",
        "explanation": "复核不同意初审结论。",
        "reviewed_by": "expense-reviewer",
        "timestamp": "2026-04-21T09:00:00+08:00",
    }

    with pytest.raises(ValidationError):
        validate(payload, schema)


def test_expense_agents_reference_structured_handoffs() -> None:
    extractor = (AGENTS_ROOT / "extractor.md").read_text(encoding="utf-8")
    auditor = (AGENTS_ROOT / "auditor.md").read_text(encoding="utf-8")
    reviewer = (AGENTS_ROOT / "reviewer.md").read_text(encoding="utf-8")

    assert "extract-result.schema.json" in extractor
    assert "extract-result.schema.json" in auditor
    assert "review-delta.schema.json" in reviewer
