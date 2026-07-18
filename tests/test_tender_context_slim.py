"""Tests for criteria-driven tender context slimming."""

from __future__ import annotations

from server.tender.context_slim import build_slim_tender_context


def _body(text: str, file_name: str = "招标文件.pdf") -> str:
    return f"### 文件: {file_name} (kind=pdf_text, route=native)\n" + text.strip()


def test_includes_expected_chapters_and_excludes_irrelevant():
    body = _body(
        """
        【第 1 页】
        # 第一章 评标办法
        技术方案章节独有内容。
        # 第二章 资格审查
        营业执照章节独有内容。
        # 第三章 商务条款
        商务条款章节独有内容。
        """
    )
    criteria = {
        "eligibility_rules": [{"check": "营业执照"}],
        "items": [{"item": "技术方案"}],
    }

    result = build_slim_tender_context(body, criteria, file_name="招标文件.pdf")

    assert result is not None
    assert "技术方案章节独有内容" in result
    assert "营业执照章节独有内容" in result
    assert "商务条款章节独有内容" not in result


def test_preserves_page_anchors():
    body = _body(
        """
        【第 2 页】
        # 第一章 评标办法
        技术方案评分章节内容。
        【第 8 页】
        # 第二章 资格审查
        营业执照资格章节内容。
        """
    )
    criteria = {
        "eligibility_rules": [{"check": "营业执照"}],
        "items": [{"item": "技术方案"}],
    }

    result = build_slim_tender_context(body, criteria, file_name="招标文件.pdf")

    assert result is not None
    assert "【第 2 页】" in result
    assert "【第 8 页】" in result


def test_returns_none_when_any_query_finds_nothing():
    body = _body(
        """
        【第 1 页】
        # 第一章 评标办法
        技术方案评分章节内容。
        """
    )
    criteria = {
        "eligibility_rules": [],
        "items": [{"item": "完全不存在的评分项"}],
    }

    assert build_slim_tender_context(body, criteria, file_name="招标文件.pdf") is None


def test_returns_none_when_document_has_no_chapters():
    body = _body("【第 1 页】\n这是一段没有任何章节标题的普通正文。")
    criteria = {"eligibility_rules": [], "items": [{"item": "普通正文"}]}

    assert build_slim_tender_context(body, criteria, file_name="招标文件.pdf") is None


def test_returns_none_when_criteria_has_no_usable_queries():
    body = _body(
        """
        【第 1 页】
        # 第一章 评标办法
        评分标准内容。
        """
    )
    criteria = {"eligibility_rules": [], "items": []}

    assert build_slim_tender_context(body, criteria, file_name="招标文件.pdf") is None


def test_dedupes_chunk_shared_by_multiple_criteria_queries(monkeypatch):
    body = _body(
        """
        【第 1 页】
        # 第一章 评标办法
        共享章节内容。
        """
    )
    criteria = {
        "eligibility_rules": [{"check": "资格关键词"}],
        "items": [{"item": "评分关键词"}],
    }
    hit = {
        "chunk_id": "招标文件.pdf#0",
        "page_anchor": "【第 1 页】",
        "text": "共享章节内容",
    }

    import server.tender.context_slim as context_slim

    monkeypatch.setattr(context_slim, "search", lambda *args, **kwargs: [hit])

    result = build_slim_tender_context(body, criteria, file_name="招标文件.pdf")

    assert result is not None
    assert result.count("共享章节内容") == 1
