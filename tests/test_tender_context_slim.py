"""Tests for criteria-driven tender context slimming."""

from __future__ import annotations

from server.tender.context_slim import (
    bound_tender_context,
    build_preextract_tender_context,
    build_slim_tender_context,
)
from server.tender.injection_budget import fallback_injection_tokens


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
        # 第二章 资格审查
        【第 8 页】
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

    from server.tender import context_slim

    monkeypatch.setattr(context_slim, "search", lambda *args, **kwargs: [hit])

    result = build_slim_tender_context(body, criteria, file_name="招标文件.pdf")

    assert result is not None
    assert result.count("共享章节内容") == 1


def test_preextract_context_keeps_preface_and_review_related_chapters(monkeypatch):
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "100000")
    monkeypatch.setenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "2000")
    body = _body(
        """
        项目名称：城市更新项目
        招标人：某市建设局
        预算金额：1200万元
        【第 1 页】
        # 第一章 项目说明
        """
        + "无关正文\n" * 40000
        + """
        # 第二章 评标办法
        评分标准：技术方案最高得 60 分。
        # 第三章 资格审查与符合性审查
        资格条件和符合性审查要求。
        # 第四章 废标与否决条款
        废标情形和否决投标条款。
        # 第五章 合同条款
        不应进入首次评分标准抽取的合同内容。
        """
    )

    result = build_preextract_tender_context(body)

    assert result is not None
    assert "项目名称：城市更新项目" in result
    assert "招标人：某市建设局" in result
    assert "评分标准：技术方案最高得 60 分" in result
    assert "资格条件和符合性审查要求" in result
    assert "废标情形和否决投标条款" in result
    assert "不应进入首次评分标准抽取的合同内容" not in result
    assert len(result) < len(body)


def test_preextract_context_returns_none_for_small_or_unstructured_text(monkeypatch):
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "100000")
    monkeypatch.setenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "2000")

    assert build_preextract_tender_context("项目名称：小项目\n评分标准：按总价评分。") is None
    assert build_preextract_tender_context("### 文件: 招标文件.pdf\n普通 OCR 正文") is None


def test_preextract_context_still_bounded_when_model_window_is_undeclared(monkeypatch):
    """AC6 改写：部署未声明模型窗口时，闸**不再整体失效**。

    旧行为在这种配置下返回 None（=注入全文），而 2026-08-14 事故当天正是这个状态。
    预算现在只由标定常量决定，与 MODEL_CONTEXT_WINDOW 无关。
    """
    monkeypatch.delenv("MODEL_CONTEXT_WINDOW", raising=False)
    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", "5000")
    body = _body("\n".join(["# 第一章 评标办法", "评分标准内容。"] + ["大段正文"] * 5000))

    result = build_preextract_tender_context(body)
    assert result is not None
    assert len(result) <= 5000


def test_preextract_context_caps_large_unstructured_ocr(monkeypatch):
    # F2：可注入额度 = 标定上限 − 脚手架 − 循环余量（200000-60000-50000=90000），
    # 不再等于整个窗口——那样加上脚手架必然爆窗。
    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", "200000")
    monkeypatch.setenv("TENDER_SCAFFOLD_RESERVE_TOKENS", "60000")
    budget = fallback_injection_tokens()
    body = "项目名称：超大文件\n" + ("无结构 OCR 正文\n" * 50000)

    result = build_preextract_tender_context(body)

    assert result is not None
    assert len(result) <= budget
    assert result.startswith("项目名称：超大文件")
    assert "章节中间内容省略" in result


def test_bound_tender_context_follows_the_calibrated_ceiling(monkeypatch):
    """AC6 改写：上限来自标定常量单点，不再从 MODEL_PROFILES_JSON 的窗口推导。"""
    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", "1000")
    monkeypatch.setenv("TENDER_SCAFFOLD_RESERVE_TOKENS", "650")
    budget = fallback_injection_tokens()

    result = bound_tender_context("x" * 150, model="small-model")

    assert result is not None
    assert len(result) <= budget
    assert "章节中间内容省略" in result


def test_bound_tender_context_preserves_tender_and_criteria_before_bid_trim(monkeypatch):
    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", "1000")
    monkeypatch.setenv("TENDER_SCAFFOLD_RESERVE_TOKENS", "630")
    budget = fallback_injection_tokens()
    context = (
        "=== OCR/直读底稿 ===\n"
        "=== 招标文件底稿 ===\n评分标准核心条款\n"
        "\n=== 投标文件（甲公司）底稿 ===\n"
        + "投标证据中段\n" * 60
        + "\n\n=== 已解析评分标准 criteria\ncriteria核心条款"
    )

    result = bound_tender_context(context, model="small-model")

    assert result is not None
    assert len(result) <= budget
    assert "评分标准核心条款" in result
    assert "criteria核心条款" in result
