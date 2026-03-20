from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = PROJECT_ROOT / "knowledge" / "external" / "数睿员工手册.structured.md"
EXTERNAL_README_PATH = PROJECT_ROOT / "knowledge" / "external" / "README.md"


def test_handbook_summary_exists_with_expected_sections() -> None:
    assert SUMMARY_PATH.is_file()

    content = SUMMARY_PATH.read_text(encoding="utf-8")

    assert "# 数睿员工手册结构化梳理" in content
    assert "## 抽象字段" in content
    assert "## 规则清单" in content
    assert "travel_request" in content
    assert "leave_request" in content
    assert "expense_claim" in content
    assert "出差申请" in content
    assert "请假" in content
    assert "报销" in content
    assert "费控" in content
    assert "业务招待" in content
    assert "借款" in content


def test_external_knowledge_readme_documents_viewable_artifacts() -> None:
    assert EXTERNAL_README_PATH.is_file()

    content = EXTERNAL_README_PATH.read_text(encoding="utf-8")

    assert "knowledge/external/" in content
    assert "可查看" in content
    assert "抽取" in content
    assert "向量" in content
    assert "Markdown" in content
