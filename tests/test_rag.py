"""Synthetic tests for structured document retrieval."""

from __future__ import annotations

import sqlite3

from server.ocr.docstructure import build_doc_structure
from server.ocr.rag import index_document, search


def _body(text: str, file_name: str = "招标文件.pdf") -> str:
    return f"### 文件: {file_name} (kind=pdf_text, route=native)\n" + text.strip()


def test_index_document_returns_chunk_count_and_search_finds_it():
    body = _body(
        """
        【第 1 页】
        # 第一章 评标办法
        本章说明评标办法和评分标准。
        # 第二章 资格审查
        本章说明资格审查要求。
        """
    )
    structure = build_doc_structure(body)
    conn = sqlite3.connect(":memory:")

    assert index_document(structure, body, conn=conn) == 2
    hits = search("评标办法", conn=conn)

    assert hits[0]["chapter_title"] == "第一章 评标办法"
    assert "评标办法" in hits[0]["text"]


def test_bm25_ranking_orders_more_relevant_chunk_first():
    body = _body(
        """
        【第 1 页】
        # 第一章 评标办法
        评标办法评标办法评标办法评标办法。
        # 第二章 资格审查
        评标办法只有一次。
        """
    )
    conn = sqlite3.connect(":memory:")
    index_document(build_doc_structure(body), body, conn=conn)

    hits = search("评标办法", conn=conn)

    assert [hit["chunk_id"] for hit in hits[:2]] == ["招标文件.pdf#0", "招标文件.pdf#1"]
    assert hits[0]["score"] > hits[1]["score"]


def test_tag_filter_restricts_results_to_matching_tag():
    body = _body(
        """
        【第 1 页】
        # 第一章 评标办法
        项目说明内容相同。
        # 第二章 资格审查
        项目说明内容相同。
        """
    )
    conn = sqlite3.connect(":memory:")
    index_document(build_doc_structure(body), body, conn=conn)

    hits = search("项目说明", conn=conn, tag="evaluation_method")

    assert hits
    assert {hit["tag"] for hit in hits} == {"evaluation_method"}
    assert {hit["chapter_title"] for hit in hits} == {"第一章 评标办法"}


def test_hits_carry_page_anchor_provenance_and_invariant():
    body = _body(
        """
        【第 1 页】
        # 第一章 评标办法
        评标办法项目说明。
        【第 2 页】
        ## 一、评分标准
        评分标准项目说明。
        【第 3 页】
        # 第二章 资格审查
        资格审查项目说明。
        """
    )
    conn = sqlite3.connect(":memory:")
    index_document(build_doc_structure(body), body, conn=conn)

    hits = search("项目说明", conn=conn)
    by_title = {hit["chapter_title"]: hit for hit in hits}

    assert by_title["第一章 评标办法"]["page_start"] == 1
    assert by_title["第一章 评标办法"]["page_end"] == 3
    assert by_title["第一章 评标办法"]["page_anchor"] == "【第 1-3 页】"
    assert by_title["一、评分标准"]["page_anchor"] == "【第 2-3 页】"
    assert by_title["第二章 资格审查"]["page_anchor"] == "【第 3 页】"
    for hit in hits:
        if hit["page_start"] is not None:
            assert hit["page_end"] is not None
            assert hit["page_end"] >= hit["page_start"]


def test_search_no_match_returns_empty_list():
    body = _body("【第 1 页】\n# 第一章 评标办法\n评分标准内容。")
    conn = sqlite3.connect(":memory:")
    index_document(build_doc_structure(body), body, conn=conn)

    assert search("不存在的检索词", conn=conn) == []


def test_index_document_with_no_chapters_indexes_zero_chunks():
    body = _body("【第 1 页】\n这是一段没有任何章节标题的普通正文。", "plain.txt")
    conn = sqlite3.connect(":memory:")
    structure = build_doc_structure(body)

    assert structure["chapters"] == []
    assert index_document(structure, body, conn=conn) == 0
    assert search("普通正文", conn=conn) == []


def test_chunk_boundary_excludes_sibling_but_includes_subtree():
    body = _body(
        """
        【第 1 页】
        # 第一章 评标办法
        父章节说明。
        ## 一、评分细则
        子章节内容。
        # 第二章 资格审查
        兄弟章节内容。
        """
    )
    conn = sqlite3.connect(":memory:")
    index_document(build_doc_structure(body), body, conn=conn)

    hit = search("父章节说明", conn=conn)[0]

    assert hit["chapter_title"] == "第一章 评标办法"
    assert "子章节内容" in hit["text"]
    assert "兄弟章节内容" not in hit["text"]


def test_reindex_same_document_is_idempotent_and_deterministic():
    body = _body(
        """
        【第 1 页】
        # 第一章 评标办法
        项目说明。
        # 第二章 资格审查
        项目说明。
        """
    )
    structure = build_doc_structure(body)
    conn = sqlite3.connect(":memory:")

    assert index_document(structure, body, conn=conn) == 2
    first = [(hit["chunk_id"], hit["text"]) for hit in search("项目说明", conn=conn)]
    assert index_document(structure, body, conn=conn) == 2
    second = [(hit["chunk_id"], hit["text"]) for hit in search("项目说明", conn=conn)]

    assert conn.execute("SELECT count(*) FROM rag_chunks").fetchone()[0] == 2
    assert second == first


def test_search_query_with_fts5_special_characters_does_not_raise():
    body = _body("【第 1 页】\n# 第一章 评标办法\n评标办法内容。")
    conn = sqlite3.connect(":memory:")
    index_document(build_doc_structure(body), body, conn=conn)

    hits = search('评标:办法" AND *', conn=conn)

    assert isinstance(hits, list)


def test_search_respects_limit():
    body = _body(
        """
        【第 1 页】
        # 第一章 项目说明
        项目说明项目说明项目说明。
        # 第二章 项目说明
        项目说明项目说明。
        # 第三章 项目说明
        项目说明。
        """
    )
    conn = sqlite3.connect(":memory:")
    index_document(build_doc_structure(body), body, conn=conn)

    hits = search("项目说明", conn=conn, limit=2)

    assert len(hits) == 2
    assert hits[0]["chunk_id"] == "招标文件.pdf#0"
