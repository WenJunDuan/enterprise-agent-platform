"""SQLite FTS5 persistence primitives for structured document chunks."""

from __future__ import annotations

import sqlite3

TABLE_NAME = "rag_chunks"


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the structured-RAG FTS5 table when it does not already exist."""
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS rag_chunks USING fts5(
            chunk_text,
            chunk_id UNINDEXED,
            file UNINDEXED,
            chapter_path UNINDEXED,
            chapter_title UNINDEXED,
            tag UNINDEXED,
            page_start UNINDEXED,
            page_end UNINDEXED,
            tokenize='trigram'
        )
        """
    )


def delete_rows_for_file(conn: sqlite3.Connection, file: str) -> None:
    """Delete all indexed chunks belonging to ``file``."""
    ensure_schema(conn)
    conn.execute("DELETE FROM rag_chunks WHERE file = ?", (file,))


def insert_rows(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """Insert structured-RAG chunks into the FTS5 table."""
    ensure_schema(conn)
    conn.executemany(
        """
        INSERT INTO rag_chunks (
            chunk_text, chunk_id, file, chapter_path, chapter_title, tag, page_start, page_end
        ) VALUES (
            :chunk_text, :chunk_id, :file, :chapter_path, :chapter_title, :tag, :page_start, :page_end
        )
        """,
        rows,
    )


def query_rows(
    conn: sqlite3.Connection, match_query: str, *, tag: str | None, limit: int
) -> list[sqlite3.Row]:
    """Return FTS5 matches ordered by ascending BM25 rank."""
    ensure_schema(conn)
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    sql = """
        SELECT chunk_id, file, chapter_path, chapter_title, tag, page_start, page_end,
               chunk_text, bm25(rag_chunks) AS rank
        FROM rag_chunks
        WHERE rag_chunks MATCH ?
    """
    params: list[object] = [match_query]
    if tag is not None:
        sql += " AND tag = ?"
        params.append(tag)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    return cur.execute(sql, params).fetchall()
