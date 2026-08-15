"""Structured document chunking and FTS5-backed retrieval."""

from __future__ import annotations

import sqlite3

from server.common.corpus import ARTIFACT_ORIGINAL, page_anchor_text
from server.ocr.docstructure import chapter_heading, scan_page_context
from server.stores import rag_store


def _flatten_tree(chapters: list[dict], ancestors: tuple[str, ...] = ()) -> list[dict]:
    """Flatten a chapter tree in DFS preorder and add each chapter path."""
    flat: list[dict] = []
    for node in chapters:
        path = ancestors + (node["title"],)
        flat.append({**node, "chapter_path": " > ".join(path)})
        flat.extend(_flatten_tree(node["children"], path))
    return flat


def _flatten_heading_lines(lines: list[str]) -> list[tuple[int, str, int]]:
    """Locate document headings by reusing the docstructure heading recognizer."""
    out: list[tuple[int, str, int]] = []
    for index, raw in enumerate(lines):
        if raw.strip().startswith("### 文件:"):
            continue
        heading = chapter_heading(raw)
        if heading is not None:
            title, level = heading
            out.append((index, title, level))
    return out


def _chunk_spans(structure: dict, body: str) -> list[dict]:
    """Build deterministic chapter-subtree chunks with real page provenance."""
    lines = body.splitlines()
    page_of, _ = scan_page_context(lines)
    flat_nodes = _flatten_tree(structure["chapters"])
    flat_headings = _flatten_heading_lines(lines)
    if len(flat_nodes) != len(flat_headings):
        raise ValueError(
            "structure/body 不匹配：章节数与 body 中标题行数不一致——"
            "index_document 要求 body 必须是构建 structure 时用的同一份原文"
        )
    chunks: list[dict] = []
    for i, (node, (line_index, _title, level)) in enumerate(zip(flat_nodes, flat_headings)):
        end_line = len(lines)
        for next_line_index, _next_title, next_level in flat_headings[i + 1 :]:
            if next_level <= level:
                end_line = next_line_index
                break
        span_lines = lines[line_index:end_line]
        page_candidates = [p for p in page_of[line_index:end_line] if p is not None]
        chunks.append(
            {
                "chunk_id": f"{structure['file']}#{i}",
                "file": structure["file"],
                "chapter_path": node["chapter_path"],
                "chapter_title": node["title"],
                "tag": node["tag"],
                "page_start": node["page"],
                "page_end": max(page_candidates) if page_candidates else None,
                "page_artifact": structure.get("page_artifact", ARTIFACT_ORIGINAL),
                "chunk_text": node["chapter_path"] + "\n" + "\n".join(span_lines).strip(),
            }
        )
    return chunks


def index_document(structure: dict, body: str, *, conn: sqlite3.Connection) -> int:
    """Index a document structure and return its number of stored chunks."""
    chunks = _chunk_spans(structure, body)
    rag_store.delete_rows_for_file(conn, structure["file"])
    if chunks:
        rag_store.insert_rows(conn, chunks)
    conn.commit()
    return len(chunks)


def _escape_match_query(query: str) -> str:
    """Wrap an untrusted FTS5 query in a phrase and escape embedded quotes."""
    return '"' + query.replace('"', '""') + '"'


def _format_page_anchor(
    page_start: int | None, page_end: int | None, artifact: str = ARTIFACT_ORIGINAL
) -> str:
    """Format a chunk's page span without inventing a page when both are absent.

    锚点字面量走 ``corpus.page_anchor_text`` 单点（H2 pass1 F3）：转换稿 chunk 渲染
    ``【转换稿第 M 页】``，否则 RAG-slim 链路会让转换页号继续冒充原文档页。
    """
    if page_start is None and page_end is None:
        return "页码未知"
    if page_start is None:
        page_start = page_end
    return page_anchor_text(page_start, artifact=artifact or ARTIFACT_ORIGINAL, page_end=page_end)


# trigram tokenizer 的最小 gram 长度。查询短于它时 FTS5 恒零命中——这是 tokenizer 的定义，
# 不是可调参数，故写死并注明出处：https://sqlite.org/fts5.html#the_trigram_tokenizer
_TRIGRAM_MIN_LENGTH = 3


def search(
    query: str, *, conn: sqlite3.Connection, tag: str | None = None, limit: int = 10
) -> list[dict]:
    """Search indexed chunks and return hits with page anchors.

    **双通道**（2026-08-15 S0-B 实测定案）：查询短于 3 字符时走普通表子串扫描，否则走
    FTS5 BM25。原因是 ``rag_chunks`` 用 trigram tokenizer，2 字中文词在其上 ``MATCH`` 与
    ``LIKE`` 双双为 0（SQLite 把 FTS5 表上的 LIKE 也优化成走 trigram 索引）；而
    「报价」「业绩」「工期」「资质」这类 2 字评分项名在评标里极常见，裸用 FTS5 时实测召回
    仅 38%。子串旁路实测 88% / 4ms，且**文档无关**——不猜任何具体标书的措辞。

    Args:
        query: 检索词（通常是 criteria 的评分项名或资格检查项）。
        conn: 索引连接。
        tag: 章节语义标签过滤。
        limit: 返回上限。

    Returns:
        命中 chunk（含 ``page_anchor``），两个通道形状一致。
    """
    if len(query.strip()) < _TRIGRAM_MIN_LENGTH:
        rows = rag_store.scan_rows(conn, query.strip(), tag=tag, limit=limit)
    else:
        rows = rag_store.query_rows(conn, _escape_match_query(query), tag=tag, limit=limit)
    return [
        {
            "chunk_id": row["chunk_id"],
            "file": row["file"],
            "chapter_path": row["chapter_path"],
            "chapter_title": row["chapter_title"],
            "tag": row["tag"],
            "page_start": row["page_start"],
            "page_end": row["page_end"],
            "page_artifact": row["page_artifact"] or ARTIFACT_ORIGINAL,
            "page_anchor": _format_page_anchor(
                row["page_start"], row["page_end"], row["page_artifact"]
            ),
            "text": row["chunk_text"],
            "score": -row["rank"],
        }
        for row in rows
    ]
