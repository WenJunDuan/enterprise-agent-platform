"""SQLite FTS5 persistence primitives for structured document chunks."""

from __future__ import annotations

import sqlite3

TABLE_NAME = "rag_chunks"
# 子串扫描副本表（2026-08-15 S0-B 定案）。**为什么必须是普通表**：SQLite 会把 FTS5 表上的
# ``LIKE`` 优化成走 trigram 索引，于是 2 字中文词在 ``rag_chunks`` 上 ``MATCH`` 与 ``LIKE``
# 双双返回 0（实测原文含「报价」19 次、Python 侧 10 chunk 命中，SQL 两种查法都是 0）。
# 这是存储层能力边界，不是查询写法问题——只有非 FTS5 的普通表才能做真子串匹配。
SCAN_TABLE_NAME = "rag_chunk_scan"


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the structured-RAG FTS5 table + substring-scan copy when absent.

    本表仅用于 ``:memory:`` 连接（每次检索现建现用），故 ``IF NOT EXISTS`` 足够；
    改成持久化库后列增删必须 drop + rebuild —— FTS5 虚拟表不支持 ``ALTER TABLE``，
    老库会带着旧列静默存活。
    """
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
            page_artifact UNINDEXED,
            tokenize='trigram'
        )
        """
    )
    # 列与 rag_chunks 逐一对齐：两张表由同一次 insert 写入，检索结果的形状因此完全一致，
    # 上层（rag.search）不必知道命中来自哪个通道。
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SCAN_TABLE_NAME} (
            chunk_id      TEXT PRIMARY KEY,
            file          TEXT,
            chapter_path  TEXT,
            chapter_title TEXT,
            tag           TEXT,
            page_start    INTEGER,
            page_end      INTEGER,
            page_artifact TEXT,
            chunk_text    TEXT
        )
        """
    )


def delete_rows_for_file(conn: sqlite3.Connection, file: str) -> None:
    """Delete all indexed chunks belonging to ``file`` from **both** tables."""
    ensure_schema(conn)
    conn.execute("DELETE FROM rag_chunks WHERE file = ?", (file,))
    conn.execute(f"DELETE FROM {SCAN_TABLE_NAME} WHERE file = ?", (file,))


_COLUMNS = (
    "chunk_text, chunk_id, file, chapter_path, chapter_title, tag, page_start, page_end,"
    " page_artifact"
)
_PLACEHOLDERS = (
    ":chunk_text, :chunk_id, :file, :chapter_path, :chapter_title, :tag, :page_start,"
    " :page_end, :page_artifact"
)


def insert_rows(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """Insert structured-RAG chunks into the FTS5 table and its substring-scan copy.

    两表**同一次调用写入**（AC0b：chunk_id 一一对应无遗漏）。分开写会引入"某条只进了一张表"
    的漂移，而这种漂移在检索侧表现为随机漏检，极难定位。
    """
    ensure_schema(conn)
    conn.executemany(
        f"INSERT INTO rag_chunks ({_COLUMNS}) VALUES ({_PLACEHOLDERS})",
        rows,
    )
    conn.executemany(
        f"INSERT OR REPLACE INTO {SCAN_TABLE_NAME} ({_COLUMNS}) VALUES ({_PLACEHOLDERS})",
        rows,
    )


def scan_rows(
    conn: sqlite3.Connection, needle: str, *, tag: str | None, limit: int
) -> list[sqlite3.Row]:
    """Return chunks whose text literally contains ``needle``, in document order.

    子串通道（S0-B 定案）：给 <3 字查询用，FTS5 trigram 对它们恒零命中。

    Args:
        conn: 索引连接。
        needle: 原始查询串——``%``/``_``/``\\`` 在此转义，因为它来自 criteria（模型输出），
            未转义的 ``%`` 会匹配全部 chunk。
        tag: 章节语义标签过滤，语义与 :func:`query_rows` 一致。
        limit: 返回上限。

    Returns:
        按写入顺序（= 文档顺序）的行；``rank`` 恒为 0——子串命中没有 BM25 分，上层按出现
        顺序取，不伪造一个相关度。**按 rowid 而不是 chunk_id 排**：chunk_id 是字符串，
        ``"#10" < "#2"``，超过 9 块就开始错位，limit 截断时选到的块变成任意的。
    """
    ensure_schema(conn)
    if not needle:
        return []
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    sql = f"""
        SELECT chunk_id, file, chapter_path, chapter_title, tag, page_start, page_end,
               page_artifact, chunk_text, 0 AS rank
        FROM {SCAN_TABLE_NAME}
        WHERE chunk_text LIKE ? ESCAPE '\\'
    """
    params: list[object] = [f"%{escaped}%"]
    if tag is not None:
        sql += " AND tag = ?"
        params.append(tag)
    sql += " ORDER BY rowid LIMIT ?"
    params.append(limit)
    return cur.execute(sql, params).fetchall()


def query_rows(
    conn: sqlite3.Connection, match_query: str, *, tag: str | None, limit: int
) -> list[sqlite3.Row]:
    """Return FTS5 matches ordered by ascending BM25 rank."""
    ensure_schema(conn)
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    sql = """
        SELECT chunk_id, file, chapter_path, chapter_title, tag, page_start, page_end,
               page_artifact, chunk_text, bm25(rag_chunks) AS rank
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
