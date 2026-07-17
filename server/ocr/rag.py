"""Structured document chunking and FTS5-backed retrieval."""

from __future__ import annotations

import sqlite3

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


def _format_page_anchor(page_start: int | None, page_end: int | None) -> str:
    """Format a chunk's page span without inventing a page when both are absent."""
    if page_start is None and page_end is None:
        return "页码未知"
    if page_end is None or page_start == page_end:
        return f"【第 {page_start} 页】"
    return f"【第 {page_start}-{page_end} 页】"


def search(
    query: str, *, conn: sqlite3.Connection, tag: str | None = None, limit: int = 10
) -> list[dict]:
    """Search indexed chunks by escaped FTS5 phrase and return BM25 hits."""
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
            "page_anchor": _format_page_anchor(row["page_start"], row["page_end"]),
            "text": row["chunk_text"],
            "score": -row["rank"],
        }
        for row in rows
    ]
