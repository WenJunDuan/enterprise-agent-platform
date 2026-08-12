"""H2 页锚溯源 · 锚点字符串协议单点化（KD0/KD1 收拢 + AC1b 有效性守卫）。

页锚是跨 6 个生产点 / 5 个解析点的字符串协议。本 sprint 把独立正则（pipeline._PAGE_ANCHOR_PATTERN /
boq._PAGE_RE / context_slim._PAGE_ANCHOR_RE）收拢到 ``server.common.corpus`` 单点，并扩展
``【转换稿第 M 页】`` 变体。测试按**行为**验证收拢（每个消费方都能识别新变体），不断言实现结构。
"""

from __future__ import annotations

import pytest

from server.common.corpus import (
    converted_page_anchor,
    page_anchor,
    parse_corpus,
    parse_page_anchor,
    source_page_kind,
)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("【第 3 页】", (3, "original")),
        ("【第3页】", (3, "original")),
        ("  【第 12 页】  ", (12, "original")),
        ("【转换稿第 7 页】", (7, "converted")),
        ("【转换稿第7页】", (7, "converted")),
    ],
)
def test_parse_page_anchor_recognizes_both_artifact_variants(line, expected):
    assert parse_page_anchor(line) == expected


@pytest.mark.parametrize(
    "line",
    ["普通正文", "【第 页】", "【第 3 页】正文跟在同一行", "", "### 文件: a.pdf"],
)
def test_parse_page_anchor_rejects_non_anchor_lines(line):
    assert parse_page_anchor(line) is None


def test_page_anchor_renderers_round_trip_through_parser():
    assert parse_page_anchor(page_anchor(4).strip()) == (4, "original")
    assert parse_page_anchor(converted_page_anchor(4).strip()) == (4, "converted")


def test_parse_corpus_marks_converted_pages_without_original_page():
    """转换稿锚：``page``（用户可回查的原文档页）为 None，页号只落在 artifact 坐标系。"""
    corpus = (
        "### 文件: 投标文件.docx (kind=pdf_text, route=convert, 已转换为PDF识别, 页号为转换稿页号)\n"
        "【转换稿第 2 页】\n拟派项目负责人张三\n"
    )
    segments = parse_corpus(corpus)
    assert len(segments) == 1
    seg = segments[0]
    assert seg["artifact"] == "converted"
    assert seg["artifact_page"] == 2
    assert seg["page"] is None


def test_parse_corpus_keeps_original_page_equal_to_artifact_page():
    segments = parse_corpus("### 文件: a.pdf (kind=pdf_text)\n【第 5 页】\n正文内容\n")
    assert segments[0]["artifact"] == "original"
    assert segments[0]["page"] == 5
    assert segments[0]["artifact_page"] == 5


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("投标文件.docx 转换稿第 3 页", "converted"),
        ("投标文件.pdf 第 3 页", "original"),
        (None, "original"),
    ],
)
def test_source_page_kind_detects_converted_citations(source, expected):
    assert source_page_kind(source) == expected


# ── AC1b：仅含转换稿锚行的底稿必须判无效（Round1-F4 回归闸）──────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "【转换稿第 1 页】",
        "### 文件: a.docx (kind=pdf_text, route=convert)\n【转换稿第 1 页】\n\n【转换稿第 2 页】",
        "### 文件: a.docx (kind=pdf_text, route=convert)\n【转换稿第 1 页】\n   ",
    ],
)
def test_is_ocr_text_valid_rejects_converted_anchors_without_content(text):
    from server.ocr.pipeline import is_ocr_text_valid

    assert is_ocr_text_valid(text) is False


def test_is_ocr_text_valid_accepts_content_under_converted_anchor():
    from server.ocr.pipeline import is_ocr_text_valid

    assert (
        is_ocr_text_valid(
            "### 文件: a.docx (kind=pdf_text, route=convert)\n【转换稿第 1 页】\n真实识别正文"
        )
        is True
    )


# ── 收拢的行为证据：三个既有解析点都识别新变体 ──────────────────────────────────


def test_boq_page_carry_recognizes_converted_anchor():
    from server.ocr.boq import extract_boq_summary

    body = "【转换稿第 4 页】\n投标总价（小写）：1,234,567.89\n"
    summary = extract_boq_summary("已标价工程量清单.pdf", body, max_chars=2000)
    assert summary is not None
    # 摘要重放锚点时必须保留 artifact 坐标系，不得把转换稿页冒充成原文档页
    assert "【转换稿第 4 页】" in summary
    assert "【第 4 页】" not in summary


def test_docstructure_reads_converted_anchor_page_numbers():
    from server.ocr.docstructure import build_doc_structure

    text = "### 文件: 招标文件.docx (kind=pdf_text, route=convert)\n【转换稿第 9 页】\n第一章 评标办法\n正文\n"
    structure = build_doc_structure(text, file_name="招标文件.docx")
    assert structure["chapters"]
    assert structure["chapters"][0]["page"] == 9


def test_context_slim_keeps_converted_anchor_above_selected_heading():
    from server.tender.context_slim import _PAGE_ANCHOR_RE

    assert _PAGE_ANCHOR_RE.match("【转换稿第 2 页】")
