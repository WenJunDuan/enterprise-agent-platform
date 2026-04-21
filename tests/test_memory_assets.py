from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "knowledge" / "_schema" / "case-memory.schema.json"
SKILL_PATH = PROJECT_ROOT / ".claude" / "skills" / "system" / "memory-distill" / "SKILL.md"
COMMAND_PATH = PROJECT_ROOT / ".claude" / "commands" / "distill-memory.md"
CLAUDE_PATH = PROJECT_ROOT / ".claude" / "CLAUDE.md"
SEED_MEMORY_PATH = (
    PROJECT_ROOT
    / "knowledge"
    / "memory"
    / "expense"
    / "expense.travel.pre-approval-mismatch.manual-review.v1.json"
)


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_case_memory_schema_accepts_valid_payload() -> None:
    schema = _load_schema()
    payload = {
        "memory_id": "expense.travel.missing-pre-approval.manual-review.v1",
        "domain": "expense",
        "memory_type": "exception_pattern",
        "title": "差旅报销缺少事前申请时应升级人工复核",
        "summary": "当差旅报销缺少可追溯的事前申请记录时，不应直接放行，应升级人工复核。",
        "category": "travel",
        "applicable_when": [
            "费用类别为差旅",
            "附件中缺少有效的事前申请单或审批编号"
        ],
        "checkpoints": [
            "确认是否存在事前申请附件",
            "确认申请记录能否回链到本次报销事项",
            "若无法闭合规则链则升级人工复核"
        ],
        "policy_refs": ["expense.travel.012"],
        "recommended_verdict": "manual_review",
        "manual_review_reason": "pre_approval_mismatch",
        "rationale": "缺少事前申请依据时，规则链无法闭合，不能自动放行。",
        "tags": ["travel", "pre-approval", "manual-review"],
        "source_trace": {
            "request_id": "req-001",
            "result_file": "results/by-request/2026/04/21/req-001.json",
            "claim_id": "EXP-2026-001",
            "conversation_id": "conv-001",
            "claude_session_id": "session-001",
            "review_delta_file": None,
        },
        "distilled_by": "system-memory-distill",
        "distilled_at": "2026-04-21T10:00:00+08:00",
    }

    validate(payload, schema)


def test_case_memory_schema_requires_traceability_fields() -> None:
    schema = _load_schema()
    payload = {
        "memory_id": "expense.travel.example.v1",
        "domain": "expense",
        "memory_type": "case_pattern",
        "title": "示例",
        "summary": "示例摘要",
        "category": "travel",
        "applicable_when": [],
        "checkpoints": [],
        "policy_refs": [],
        "recommended_verdict": "manual_review",
        "manual_review_reason": "insufficient_evidence",
        "rationale": "示例原因",
        "tags": [],
        "source_trace": {
            "claim_id": "EXP-2026-001",
            "conversation_id": None,
            "claude_session_id": None,
            "review_delta_file": None,
        },
        "distilled_by": "system-memory-distill",
        "distilled_at": "2026-04-21T10:00:00+08:00",
    }

    with pytest.raises(ValidationError):
        validate(payload, schema)


def test_memory_skill_and_command_reference_schema_and_output_path() -> None:
    skill = SKILL_PATH.read_text(encoding="utf-8")
    command = COMMAND_PATH.read_text(encoding="utf-8")
    claude = CLAUDE_PATH.read_text(encoding="utf-8")

    assert "knowledge/_schema/case-memory.schema.json" in skill
    assert "knowledge/memory/{domain}/" in skill
    assert "/distill-memory" in command
    assert "system-memory-distill" in claude


def test_seed_memory_asset_matches_schema() -> None:
    schema = _load_schema()
    payload = json.loads(SEED_MEMORY_PATH.read_text(encoding="utf-8"))

    validate(payload, schema)
