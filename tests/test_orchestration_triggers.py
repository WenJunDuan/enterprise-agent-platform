from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_claude_router_defines_explicit_cross_domain_and_reviewer_triggers() -> None:
    claude = (PROJECT_ROOT / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    audit = (PROJECT_ROOT / ".claude" / "commands" / "audit.md").read_text(encoding="utf-8")

    assert "risk_score >= 70" in claude
    assert "expense-reviewer" in claude
    assert "attendance-checker" in claude
    assert "contract-reviewer" in claude
    assert "risk_score >= 70" in audit
    assert "周末" in audit or "考勤" in audit
    assert "合同" in audit
