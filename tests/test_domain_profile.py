"""Unit tests for server/common/domain_profile.py (域驱动 lean prompt 装配器).

核心 = critic F2「字节级回归」：装配器输出必须与重构前的 ``build_inline_audit_prompt``
逐字节一致。golden 快照由重构前的实现对固定 fixture 生成（见
``tests/fixtures/domain_profile/golden_*.txt``），重构后两条路径都必须匹配。

全部用 fixture + monkeypatch 隔离文件系统，不发起网络请求。
"""

from __future__ import annotations

from pathlib import Path

from server.common.domain_profile import (
    DomainProfile,
    assemble_domain_prompt,
    load_case_block,
    load_rules,
    resolve_case_dir,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "domain_profile"
CASE_DIR_NAME = "case_expense_golden"
RULES_DIR = FIXTURES / "rules_golden"


def _expense_fixture_profile() -> DomainProfile:
    """重建与 golden 生成时一致的 expense profile（指向 fixture）。"""
    from server.audit.runner import AUDIT_INSTRUCTIONS, CASE_REQUEST_FILE

    return DomainProfile(
        domain="expense",
        instructions=AUDIT_INSTRUCTIONS,
        rules_dir=RULES_DIR,
        request_file=CASE_REQUEST_FILE,
        case_missing_fallback="（未找到本案材料，请据此输出 manual_review）",
        rules_missing_fallback="（本地规则缺失，无适用规则时输出 manual_review / rule_gap）",
        result_contract="common/audit-result.schema.json",
    )


# ═════════════════════════════════════════════════════════════════════════════
# critic F2: 字节级回归（装配器 == 重构前 build_inline_audit_prompt）
# ═════════════════════════════════════════════════════════════════════════════


class TestGoldenByteIdentity:
    def test_assemble_matches_golden_no_ocr(self):
        golden = (FIXTURES / "golden_no_ocr.txt").read_text(encoding="utf-8")
        out = assemble_domain_prompt(
            _expense_fixture_profile(), CASE_DIR_NAME, project_root=FIXTURES
        )
        assert out == golden

    def test_assemble_matches_golden_with_ocr(self):
        golden = (FIXTURES / "golden_with_ocr.txt").read_text(encoding="utf-8")
        out = assemble_domain_prompt(
            _expense_fixture_profile(),
            CASE_DIR_NAME,
            project_root=FIXTURES,
            ocr_block="发票OCR底稿：金额500元 印章已检出",
        )
        assert out == golden

    def test_runner_wrapper_matches_golden(self, monkeypatch):
        """``build_inline_audit_prompt`` 经委托后仍与 golden 字节一致（公共面零变化）。"""
        from server.audit import runner

        monkeypatch.setattr(runner, "PROJECT_ROOT", FIXTURES)
        monkeypatch.setattr(runner, "EXPENSE_RULES_DIR", RULES_DIR)
        golden = (FIXTURES / "golden_no_ocr.txt").read_text(encoding="utf-8")
        assert runner.build_inline_audit_prompt(CASE_DIR_NAME) == golden

    def test_runner_wrapper_matches_golden_with_ocr(self, monkeypatch):
        from server.audit import runner

        monkeypatch.setattr(runner, "PROJECT_ROOT", FIXTURES)
        monkeypatch.setattr(runner, "EXPENSE_RULES_DIR", RULES_DIR)
        golden = (FIXTURES / "golden_with_ocr.txt").read_text(encoding="utf-8")
        out = runner.build_inline_audit_prompt(
            CASE_DIR_NAME, ocr_block="发票OCR底稿：金额500元 印章已检出"
        )
        assert out == golden


# ═════════════════════════════════════════════════════════════════════════════
# resolve_case_dir（路径穿越守卫）
# ═════════════════════════════════════════════════════════════════════════════


class TestResolveCaseDir:
    def test_valid_relative_inside_root(self, tmp_path):
        case = tmp_path / "data" / "c1"
        case.mkdir(parents=True)
        assert resolve_case_dir("data/c1", tmp_path) == case.resolve()

    def test_absolute_inside_root(self, tmp_path):
        case = tmp_path / "data" / "c2"
        case.mkdir(parents=True)
        assert resolve_case_dir(str(case), tmp_path) == case.resolve()

    def test_traversal_outside_root_returns_none(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        assert resolve_case_dir("../../etc", project) is None

    def test_path_above_root_returns_none(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        assert resolve_case_dir(str(tmp_path), project) is None

    def test_nonexistent_returns_none(self, tmp_path):
        assert resolve_case_dir("data/missing", tmp_path) is None

    def test_file_returns_none(self, tmp_path):
        f = tmp_path / "f.json"
        f.write_text("{}", encoding="utf-8")
        assert resolve_case_dir(str(f), tmp_path) is None


# ═════════════════════════════════════════════════════════════════════════════
# load_rules
# ═════════════════════════════════════════════════════════════════════════════


class TestLoadRules:
    def test_missing_dir_returns_empty(self, tmp_path):
        assert load_rules(tmp_path / "no-such") == ""

    def test_concatenates_sorted_json(self, tmp_path):
        (tmp_path / "b.json").write_text('{"r":"b"}', encoding="utf-8")
        (tmp_path / "a.json").write_text('{"r":"a"}', encoding="utf-8")
        out = load_rules(tmp_path)
        assert out == '### a.json\n{"r":"a"}\n\n### b.json\n{"r":"b"}'

    def test_non_json_ignored(self, tmp_path):
        (tmp_path / "rules.json").write_text('{"r":"x"}', encoding="utf-8")
        (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
        out = load_rules(tmp_path)
        assert "notes.txt" not in out and "rules.json" in out

    def test_empty_dir_returns_empty(self, tmp_path):
        assert load_rules(tmp_path) == ""


# ═════════════════════════════════════════════════════════════════════════════
# load_case_block
# ═════════════════════════════════════════════════════════════════════════════


class TestLoadCaseBlock:
    def test_missing_dir_returns_empty(self, tmp_path):
        assert load_case_block("missing/dir", tmp_path, "audit-request.json") == ""

    def test_request_json_included(self, tmp_path):
        case = tmp_path / "data" / "c"
        case.mkdir(parents=True)
        (case / "audit-request.json").write_text('{"amount":100}', encoding="utf-8")
        out = load_case_block("data/c", tmp_path, "audit-request.json")
        assert "### audit-request.json" in out and '{"amount":100}' in out

    def test_attachments_listed_with_directory_path_prefix(self, tmp_path):
        case = tmp_path / "data" / "c"
        case.mkdir(parents=True)
        (case / "audit-request.json").write_text("{}", encoding="utf-8")
        (case / "invoice.pdf").write_bytes(b"x")
        out = load_case_block("data/c", tmp_path, "audit-request.json")
        assert "附件文件清单" in out and "- data/c/invoice.pdf" in out

    def test_attachments_without_request_file(self, tmp_path):
        case = tmp_path / "data" / "c"
        case.mkdir(parents=True)
        (case / "receipt.jpg").write_bytes(b"x")
        out = load_case_block("data/c", tmp_path, "audit-request.json")
        assert "receipt.jpg" in out

    def test_empty_dir_returns_empty(self, tmp_path):
        case = tmp_path / "data" / "empty"
        case.mkdir(parents=True)
        assert load_case_block("data/empty", tmp_path, "audit-request.json") == ""


# ═════════════════════════════════════════════════════════════════════════════
# assemble_domain_prompt 兜底
# ═════════════════════════════════════════════════════════════════════════════


class TestAssembleFallbacks:
    def test_missing_case_and_rules_use_fallbacks(self, tmp_path):
        profile = DomainProfile(
            domain="x",
            instructions="INSTR",
            rules_dir=tmp_path / "no-rules",
            request_file="req.json",
            case_missing_fallback="NO_CASE",
            rules_missing_fallback="NO_RULES",
            result_contract="c.schema.json",
        )
        out = assemble_domain_prompt(profile, "missing/dir", project_root=tmp_path)
        assert "INSTR" in out and "NO_CASE" in out and "NO_RULES" in out

    def test_ocr_block_omitted_when_none(self, tmp_path):
        profile = DomainProfile(
            domain="x",
            instructions="INSTR",
            rules_dir=tmp_path / "no-rules",
            request_file="req.json",
            case_missing_fallback="NO_CASE",
            rules_missing_fallback="NO_RULES",
            result_contract="c.schema.json",
        )
        assert "OCR/直读底稿" not in assemble_domain_prompt(profile, "missing", project_root=tmp_path)
