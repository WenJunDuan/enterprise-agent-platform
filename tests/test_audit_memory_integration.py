from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_common_memory_query_skill_exists_and_targets_knowledge_memory() -> None:
    content = (
        PROJECT_ROOT / ".claude" / "skills" / "common" / "memory-query" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "knowledge/memory/{domain}/" in content
    assert "source_trace.request_id" in content
    assert "source_trace.result_file" in content


def test_expense_auditor_and_expense_audit_consume_memory_as_secondary_signal() -> None:
    auditor = (PROJECT_ROOT / ".claude" / "agents" / "expense" / "auditor.md").read_text(
        encoding="utf-8"
    )
    skill = (PROJECT_ROOT / ".claude" / "skills" / "expense-audit" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "common-memory-query" in auditor
    assert "common-memory-query" in skill
    assert "不能替代结构化规则" in skill
    assert "memory:" in auditor


def test_evidence_chain_supports_memory_trace_sources() -> None:
    content = (
        PROJECT_ROOT / ".claude" / "skills" / "common" / "evidence-chain" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "memory:" in content


def test_audit_command_mentions_memory_as_secondary_evidence() -> None:
    content = (PROJECT_ROOT / ".claude" / "commands" / "audit.md").read_text(encoding="utf-8")

    assert "knowledge/memory/{domain}/" in content
    assert "memory:" in content
