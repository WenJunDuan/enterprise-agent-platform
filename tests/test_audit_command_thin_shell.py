"""D3 T1: `.claude/commands/audit.md` must be a thin shell over the Python single
source of truth for judgment discipline (``server/audit/runner.py:AUDIT_INSTRUCTIONS``).

Guards two things text-scan style (mirrors ``tests/test_layering.py`` pattern):
1. audit.md carries the definitional statement + a mandatory first-step Read of
   runner.py, so a CC session cannot silently improvise judgment discipline.
2. audit.md does not re-embed judgment-methodology prose that already lives in
   AUDIT_INSTRUCTIONS (the double-source drift D3 exists to kill) — this is not a
   full-text diff, just a spot check on the phrases design.md's Round-1 F5 flagged.

design ref: .ai_state/sprints/2026-07-18-prompt-single-source/design.md T1 段.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDIT_MD = PROJECT_ROOT / ".claude" / "commands" / "audit.md"
RUNNER_PY = PROJECT_ROOT / "server" / "audit" / "runner.py"


def _audit_md_text() -> str:
    return AUDIT_MD.read_text(encoding="utf-8")


class TestDefinitionalStatement:
    def test_declares_cc_channel_execution_entry(self):
        text = _audit_md_text()
        assert "执行入口" in text, "audit.md must state it is the CC channel's execution entry"

    def test_declares_runner_as_single_source_of_truth(self):
        text = _audit_md_text()
        assert "唯一真相源" in text
        assert "server/audit/runner.py" in text
        assert "AUDIT_INSTRUCTIONS" in text

    def test_does_not_claim_debug_only(self):
        """critic F5: 「仅供调试」定性与 CLAUDE.md 路由表矛盾（/audit 仍是生产入口）."""
        text = _audit_md_text()
        assert "仅供调试" not in text


class TestMandatoryFirstReadStep:
    def test_first_instruction_is_mandatory_read_of_runner(self):
        text = _audit_md_text()
        assert "必须" in text
        assert "Read server/audit/runner.py" in text or "Read `server/audit/runner.py`" in text
        # The mandatory Read instruction must precede any numbered procedural step
        # (it is the first thing the agent does, not an afterthought).
        read_idx = text.find("Read server/audit/runner.py")
        if read_idx == -1:
            read_idx = text.find("Read `server/audit/runner.py`")
        first_numbered_step_idx = text.find("\n1.")
        assert read_idx != -1
        assert first_numbered_step_idx == -1 or read_idx < first_numbered_step_idx

    def test_names_audit_instructions_as_the_judgment_discipline(self):
        text = _audit_md_text()
        assert "AUDIT_INSTRUCTIONS" in text
        assert "判断纪律" in text


class TestNoDuplicatedJudgmentMethodology:
    """Spot-checks phrases that are judgment methodology (not input parsing / output
    contract shape) and live verbatim in AUDIT_INSTRUCTIONS — these must not be
    re-embedded in the thin shell (design T1: 删除与 AUDIT_INSTRUCTIONS 重复的判断细节)."""

    def test_data_authenticity_heuristics_not_duplicated(self):
        text = _audit_md_text()
        assert "数据真实性快速核验" not in text
        assert "占位 / 测试值" not in text

    def test_wording_discipline_examples_not_duplicated(self):
        text = _audit_md_text()
        assert "硬伤、铁证、实锤" not in text

    def test_json_string_quoting_rule_not_duplicated(self):
        text = _audit_md_text()
        assert "一律使用中文引号" not in text

    def test_rule_priority_methodology_not_duplicated(self):
        text = _audit_md_text()
        assert "同优先级 `reject` 优先于 `approve`" not in text


class TestInputParsingAndOutputContractKept:
    """These are CC-channel-specific (tool usage) or contract-shape statements,
    not judgment methodology — design says keep them."""

    def test_still_explains_directory_vs_file_input_parsing(self):
        text = _audit_md_text()
        assert "Glob" in text
        assert "Read" in text

    def test_still_maps_category_to_local_rule_files(self):
        text = _audit_md_text()
        assert "knowledge/expense/travel.rules.json" in text

    def test_still_points_to_output_schema_contract(self):
        text = _audit_md_text()
        assert ".claude/contracts/common/audit-result.schema.json" in text


def test_runner_still_owns_audit_instructions():
    """Sanity: the single source itself must still exist with this exact name."""
    text = RUNNER_PY.read_text(encoding="utf-8")
    assert "AUDIT_INSTRUCTIONS = " in text
