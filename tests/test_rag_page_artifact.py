"""H2 pass1 F3：RAG-slim 链路的页锚也必须走 corpus 单点 + 带 artifact。

`rag._format_page_anchor` 是第 6 个自有锚点生产点：硬编码 `【第 M 页】`，于是 D8 底稿瘦身
（context_slim.build_slim_tender_context）产出的 context 里，转换稿页号继续冒充原文档页；
区间锚 `【第 3-5 页】` 又不在协议里，下游解析全部落空。
"""

from __future__ import annotations

import sqlite3

from server.common.corpus import page_anchor_text, parse_page_anchor
from server.ocr.docstructure import build_doc_structure
from server.ocr.rag import index_document, search

_CONVERTED_DOC = (
    "### 文件: 招标文件.docx (kind=pdf_text, route=convert, 已转换为PDF识别, 页号为转换稿页号)\n"
    "【转换稿第 3 页】\n第一章 评标办法\n综合评估法，满分 100 分，价格分 40 分。\n"
    "【转换稿第 4 页】\n第二章 资格审查\n投标人须具备市政公用工程施工总承包一级资质。\n"
)


def test_range_anchor_is_part_of_the_protocol():
    """区间锚纳入协议：可渲染、可解析（解析取起始页）。"""
    assert page_anchor_text(3, page_end=5) == "【第 3-5 页】"
    assert parse_page_anchor("【第 3-5 页】") == (3, "original")
    assert parse_page_anchor("【转换稿第 3-5 页】") == (3, "converted")


def test_single_page_rendering_unchanged():
    assert page_anchor_text(3, page_end=3) == "【第 3 页】"
    assert page_anchor_text(3) == "【第 3 页】"


def test_doc_structure_records_page_artifact():
    structure = build_doc_structure(_CONVERTED_DOC, file_name="招标文件.docx")
    assert structure["page_artifact"] == "converted"


def test_doc_structure_defaults_to_original_artifact():
    structure = build_doc_structure(
        "### 文件: 招标文件.pdf (kind=pdf_text)\n【第 3 页】\n第一章 评标办法\n正文\n",
        file_name="招标文件.pdf",
    )
    assert structure["page_artifact"] == "original"


def test_rag_hits_carry_converted_page_anchor():
    """AC1 的 RAG 分支：转换稿文档检索命中，page_anchor 必须是转换稿坐标。"""
    structure = build_doc_structure(_CONVERTED_DOC, file_name="招标文件.docx")
    conn = sqlite3.connect(":memory:")
    index_document(structure, _CONVERTED_DOC, conn=conn)

    hits = search("资格审查", conn=conn)
    conn.close()
    assert hits
    anchors = {hit["page_anchor"] for hit in hits}
    assert all(anchor.startswith("【转换稿第") for anchor in anchors), anchors
    assert all("【第" not in anchor.replace("【转换稿第", "") for anchor in anchors)
