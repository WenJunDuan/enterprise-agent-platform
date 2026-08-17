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
            source_file UNINDEXED,
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
            source_file   TEXT,
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


# ``file`` 是**层/文档标识**（证据层用 ``__bid__`` / ``__tender__``，限层检索按它过滤）；
# ``source_file`` 是该 chunk 在底稿里的**真实来源文件头串**（``### 文件:`` 之后的原串）。
# 两者必须并存：只留层标识，注入块就写不出真实出处，回查闸按 file 分桶的页号核实随之落空
# （review pass3 F1）；只留真实文件名，S8 的投标层优先过滤就没得过滤。
_COLUMNS = (
    "chunk_text, chunk_id, file, source_file, chapter_path, chapter_title, tag, page_start,"
    " page_end, page_artifact"
)
_PLACEHOLDERS = (
    ":chunk_text, :chunk_id, :file, :source_file, :chapter_path, :chapter_title, :tag,"
    " :page_start, :page_end, :page_artifact"
)
# 三条检索通道共用的返回列（必须与 ``rag._as_hit`` 读的键一一对应）。
_SELECT_COLUMNS = (
    "chunk_id, file, source_file, chapter_path, chapter_title, tag, page_start, page_end,"
    " page_artifact, chunk_text"
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


def _scope_filter(*, tag: str | None, file: str | None) -> tuple[str, list[object]]:
    """Build the ``AND`` clause shared by both retrieval channels.

    单点构造（DRY）：两个通道的过滤条件必须逐字一致，否则同一次检索在 <3 字与 ≥3 字两条
    路径上会取到不同的行集合，而这种漂移在上层表现为"换个项名就漏检"。

    Args:
        tag: 章节语义标签过滤；``None`` 不过滤。
        file: 文档层过滤（招标层 / 投标层各一个 file 标识）；``None`` 不过滤。

    Returns:
        ``(sql 片段, 参数)``，按出现顺序对齐。
    """
    sql = ""
    params: list[object] = []
    if tag is not None:
        sql += " AND tag = ?"
        params.append(tag)
    if file is not None:
        sql += " AND file = ?"
        params.append(file)
    return sql, params


def scan_rows(
    conn: sqlite3.Connection,
    needle: str,
    *,
    tag: str | None,
    limit: int,
    file: str | None = None,
) -> list[sqlite3.Row]:
    """Return chunks whose text literally contains ``needle``, in document order.

    子串通道（S0-B 定案）：给 <3 字查询用，FTS5 trigram 对它们恒零命中。

    Args:
        conn: 索引连接。
        needle: 原始查询串——``%``/``_``/``\\`` 在此转义，因为它来自 criteria（模型输出），
            未转义的 ``%`` 会匹配全部 chunk。
        tag: 章节语义标签过滤，语义与 :func:`query_rows` 一致。
        limit: 返回上限。
        file: 只在该 file 内检索；``None`` 表示全库。

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
        SELECT {_SELECT_COLUMNS}, 0 AS rank
        FROM {SCAN_TABLE_NAME}
        WHERE chunk_text LIKE ? ESCAPE '\\'
    """
    params: list[object] = [f"%{escaped}%"]
    scope_sql, scope_params = _scope_filter(tag=tag, file=file)
    sql += scope_sql
    params.extend(scope_params)
    sql += " ORDER BY rowid LIMIT ?"
    params.append(limit)
    return cur.execute(sql, params).fetchall()


def following_rows(
    conn: sqlite3.Connection, chunk_id: str, *, limit: int
) -> list[sqlite3.Row]:
    """Return the chunks that follow ``chunk_id`` in document order, same file only.

    只查普通副本表：``rag_chunks`` 是 FTS5 虚表，两表的 rowid 并不保证一一对应，跨表按
    rowid 续接会在删改后错位。副本表的 rowid = 写入顺序，而写入顺序由
    ``evidence_chunks.dedupe_in_document_order`` 排成文档顺序（构造保证，见该函数）。

    限定 ``file`` 相同：招标层与投标层同库不同 file，续接不得从投标末尾滑进招标正文。

    Args:
        conn: 索引连接。
        chunk_id: 命中块的 id；不存在时返回空列表（调用方据此停止续接）。
        limit: 本次取多少块。

    Returns:
        紧随其后的行，按文档顺序。
    """
    ensure_schema(conn)
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    anchor = cur.execute(
        f"SELECT rowid, file FROM {SCAN_TABLE_NAME} WHERE chunk_id = ?", (chunk_id,)
    ).fetchone()
    if anchor is None:
        return []
    return cur.execute(
        f"""
        SELECT {_SELECT_COLUMNS}, 0 AS rank
        FROM {SCAN_TABLE_NAME}
        WHERE file = ? AND rowid > ?
        ORDER BY rowid LIMIT ?
        """,
        (anchor["file"], anchor["rowid"], limit),
    ).fetchall()


def query_rows(
    conn: sqlite3.Connection,
    match_query: str,
    *,
    tag: str | None,
    limit: int,
    file: str | None = None,
) -> list[sqlite3.Row]:
    """Return FTS5 matches ordered by ascending BM25 rank.

    Args:
        conn: 索引连接。
        match_query: 已转义的 FTS5 MATCH 表达式。
        tag: 章节语义标签过滤；``None`` 不过滤。
        limit: 返回上限。
        file: 只在该 file 内检索；``None`` 表示全库。

    Returns:
        命中行，BM25 升序（rank 越小越相关）。
    """
    ensure_schema(conn)
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    sql = f"""
        SELECT {_SELECT_COLUMNS}, bm25(rag_chunks) AS rank
        FROM rag_chunks
        WHERE rag_chunks MATCH ?
    """
    params: list[object] = [match_query]
    scope_sql, scope_params = _scope_filter(tag=tag, file=file)
    sql += scope_sql
    params.extend(scope_params)
    sql += " ORDER BY rank LIMIT ?"
    params.append(limit)
    return cur.execute(sql, params).fetchall()
