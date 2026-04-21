from __future__ import annotations

import json
from pathlib import Path

from server.platform import asset_validation as asset_validation_module


def test_validate_knowledge_assets_reports_ok_for_current_repo() -> None:
    report = asset_validation_module.validate_knowledge_assets()

    assert report["status"] == "ok"
    assert report["rules"]["checked_files"] >= 1
    assert report["memory"]["checked_files"] >= 1


def test_validate_memory_assets_detects_filename_mismatch(tmp_path: Path) -> None:
    memory_root = tmp_path / "knowledge" / "memory" / "expense"
    memory_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "memory_id": "expense.travel.sample.manual-review.v1",
        "domain": "expense",
        "memory_type": "exception_pattern",
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
            "request_id": "req-1",
            "result_file": "results/by-request/2026/04/21/req-1.json",
            "claim_id": "EXP-1",
            "conversation_id": None,
            "claude_session_id": None,
            "review_delta_file": None,
        },
        "distilled_by": "system-memory-distill",
        "distilled_at": "2026-04-21T12:00:00+08:00",
    }
    bad_path = memory_root / "wrong-name.json"
    bad_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = asset_validation_module.validate_memory_assets(memory_root.parent.parent)

    assert report["status"] == "degraded"
    assert any("memory_id does not match filename" in error for error in report["errors"])
