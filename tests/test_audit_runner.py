"""Unit tests for server/audit/runner.py pure/IO functions.

全部使用 tmp_path + monkeypatch 隔离文件系统，不发起网络请求。
"""

from __future__ import annotations



from server.audit.runner import (
    AUDIT_INSTRUCTIONS,
    CASE_REQUEST_FILE,
    _resolve_case_dir,
    build_inline_audit_prompt,
    load_case_block,
    load_expense_rules,
)


# ═════════════════════════════════════════════════════════════════════════════
# _resolve_case_dir
# ═════════════════════════════════════════════════════════════════════════════


class TestResolveCaseDir:
    def test_valid_absolute_path_inside_project(self, tmp_path, monkeypatch):
        """项目根内的绝对路径，目录存在时返回 Path。"""
        # 把 PROJECT_ROOT 临时指向 tmp_path 使得任意子目录都 "在内"
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path)
        case_dir = tmp_path / "data" / "case001"
        case_dir.mkdir(parents=True)
        result = _resolve_case_dir(str(case_dir))
        assert result == case_dir.resolve()

    def test_relative_path_inside_project(self, tmp_path, monkeypatch):
        """相对路径会被拼到 PROJECT_ROOT 后 resolve。"""
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path)
        case_dir = tmp_path / "data" / "case002"
        case_dir.mkdir(parents=True)
        result = _resolve_case_dir("data/case002")
        assert result == case_dir.resolve()

    def test_path_outside_project_returns_none(self, tmp_path, monkeypatch):
        """路径穿越到项目根外时返回 None（防目录遍历攻击）。"""
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path / "project")
        (tmp_path / "project").mkdir()
        # 指向 tmp_path 本身——比 project/ 高一级
        result = _resolve_case_dir(str(tmp_path))
        assert result is None

    def test_traversal_via_dotdot_returns_none(self, tmp_path, monkeypatch):
        """../../ 风格路径穿越，返回 None。"""
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", project)
        result = _resolve_case_dir("../../etc")
        assert result is None

    def test_nonexistent_directory_returns_none(self, tmp_path, monkeypatch):
        """目录不存在时返回 None（而非抛异常）。"""
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path)
        result = _resolve_case_dir("data/no-such-dir")
        assert result is None

    def test_file_path_returns_none(self, tmp_path, monkeypatch):
        """路径指向文件（非目录）时返回 None。"""
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path)
        f = tmp_path / "data" / "file.json"
        f.parent.mkdir(parents=True)
        f.write_text("{}")
        result = _resolve_case_dir(str(f))
        assert result is None


# ═════════════════════════════════════════════════════════════════════════════
# load_expense_rules
# ═════════════════════════════════════════════════════════════════════════════


class TestLoadExpenseRules:
    def test_empty_string_when_dir_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("server.audit.runner.EXPENSE_RULES_DIR", tmp_path / "no-such-dir")
        assert load_expense_rules() == ""

    def test_concatenates_json_files(self, tmp_path, monkeypatch):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "a.json").write_text('{"rule": "a"}', encoding="utf-8")
        (rules_dir / "b.json").write_text('{"rule": "b"}', encoding="utf-8")
        monkeypatch.setattr("server.audit.runner.EXPENSE_RULES_DIR", rules_dir)
        result = load_expense_rules()
        assert "### a.json" in result
        assert "### b.json" in result
        assert '{"rule": "a"}' in result
        assert '{"rule": "b"}' in result

    def test_non_json_files_ignored(self, tmp_path, monkeypatch):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "rules.json").write_text('{"rule": "x"}', encoding="utf-8")
        (rules_dir / "notes.txt").write_text("ignore me", encoding="utf-8")
        monkeypatch.setattr("server.audit.runner.EXPENSE_RULES_DIR", rules_dir)
        result = load_expense_rules()
        assert "notes.txt" not in result
        assert "rules.json" in result

    def test_empty_dir_returns_empty_string(self, tmp_path, monkeypatch):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        monkeypatch.setattr("server.audit.runner.EXPENSE_RULES_DIR", rules_dir)
        assert load_expense_rules() == ""


# ═════════════════════════════════════════════════════════════════════════════
# load_case_block
# ═════════════════════════════════════════════════════════════════════════════


class TestLoadCaseBlock:
    def test_missing_case_dir_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path)
        assert load_case_block("nonexistent/dir") == ""

    def test_case_request_json_included(self, tmp_path, monkeypatch):
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path)
        case_dir = tmp_path / "data" / "case001"
        case_dir.mkdir(parents=True)
        (case_dir / CASE_REQUEST_FILE).write_text('{"amount": 100}', encoding="utf-8")
        result = load_case_block("data/case001")
        assert CASE_REQUEST_FILE in result
        assert '{"amount": 100}' in result

    def test_attachment_listing_included(self, tmp_path, monkeypatch):
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path)
        case_dir = tmp_path / "data" / "case002"
        case_dir.mkdir(parents=True)
        (case_dir / CASE_REQUEST_FILE).write_text("{}", encoding="utf-8")
        (case_dir / "invoice.pdf").write_bytes(b"fake")
        result = load_case_block("data/case002")
        assert "invoice.pdf" in result
        assert "附件文件清单" in result

    def test_missing_request_file_still_shows_attachments(self, tmp_path, monkeypatch):
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path)
        case_dir = tmp_path / "data" / "case003"
        case_dir.mkdir(parents=True)
        (case_dir / "receipt.jpg").write_bytes(b"img")
        result = load_case_block("data/case003")
        assert "receipt.jpg" in result

    def test_empty_case_dir_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path)
        case_dir = tmp_path / "data" / "empty"
        case_dir.mkdir(parents=True)
        result = load_case_block("data/empty")
        assert result == ""


# ═════════════════════════════════════════════════════════════════════════════
# build_inline_audit_prompt
# ═════════════════════════════════════════════════════════════════════════════


class TestBuildInlineAuditPrompt:
    def test_includes_instructions(self, tmp_path, monkeypatch):
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("server.audit.runner.EXPENSE_RULES_DIR", tmp_path / "no-rules")
        prompt = build_inline_audit_prompt("no/such/dir")
        assert AUDIT_INSTRUCTIONS in prompt

    def test_requires_all_five_risk_dimensions(self, tmp_path, monkeypatch):
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("server.audit.runner.EXPENSE_RULES_DIR", tmp_path / "no-rules")

        prompt = build_inline_audit_prompt("no/such/dir")

        assert "risk_dimensions" in prompt
        assert "invoice / amount / approval / budget / anomaly" in prompt
        assert "五项" in prompt
        assert "0-10" in prompt

    def test_missing_case_shows_placeholder(self, tmp_path, monkeypatch):
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("server.audit.runner.EXPENSE_RULES_DIR", tmp_path / "no-rules")
        prompt = build_inline_audit_prompt("no/such/dir")
        assert "未找到本案材料" in prompt

    def test_missing_rules_shows_placeholder(self, tmp_path, monkeypatch):
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path)
        monkeypatch.setattr("server.audit.runner.EXPENSE_RULES_DIR", tmp_path / "no-rules")
        prompt = build_inline_audit_prompt("no/such/dir")
        assert "本地规则缺失" in prompt

    def test_normal_assembly_contains_all_three_sections(self, tmp_path, monkeypatch):
        monkeypatch.setattr("server.audit.runner.PROJECT_ROOT", tmp_path)
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "expense.json").write_text('{"rule_id": "R001"}', encoding="utf-8")
        monkeypatch.setattr("server.audit.runner.EXPENSE_RULES_DIR", rules_dir)

        case_dir = tmp_path / "data" / "case001"
        case_dir.mkdir(parents=True)
        (case_dir / CASE_REQUEST_FILE).write_text('{"amount": 500}', encoding="utf-8")

        prompt = build_inline_audit_prompt("data/case001")
        assert "本案材料" in prompt
        assert "本地规则" in prompt
        assert '{"amount": 500}' in prompt
        assert '{"rule_id": "R001"}' in prompt
