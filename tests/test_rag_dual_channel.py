"""S3a · 双通道检索（AC0b/AC4）：<3 字走普通表子串扫描，≥3 字走 FTS5 BM25。

根因（2026-08-15 S0-B 部署机实测，非查询写法问题而是存储层能力边界）：
``rag_chunks`` 是 trigram tokenizer 的 FTS5 虚拟表。原文含「报价」19 次、Python 侧 10 个
chunk 命中，而 SQL 侧 ``MATCH`` 与 ``LIKE`` **双双返回 0**——SQLite 会把 FTS5 表上的 LIKE
优化成走 trigram 索引，因此 2 字中文词两条路都不通。「报价」「业绩」「工期」「资质」这类
2 字评分项名在评标里极常见，裸用 rag.search 时它们全部零命中（实测召回 38%）。

定案方案（不得改）：新增一张**普通表**存 chunk 文本副本，与 rag_chunks 同源写入、chunk_id
一一对应；<3 字查询走该表子串扫描（实测 88% / 4ms），≥3 字仍走 FTS5 BM25。
**严禁**用硬编码词缀把 2 字词扩成 ≥3 字短语——该路线实测仅 62%，且依赖猜具体标书的措辞，
换一份标书即失效。
"""

from __future__ import annotations

import sqlite3

import pytest

from server.ocr import rag
from server.stores import rag_store


def _row(chunk_id: str, text: str, *, tag: str = "bid", file: str = "投标.pdf") -> dict:
    return {
        "chunk_id": chunk_id,
        "file": file,
        "chapter_path": "商务标 > 报价一览表",
        "chapter_title": "报价一览表",
        "tag": tag,
        "page_start": 1,
        "page_end": 2,
        "page_artifact": "original",
        "chunk_text": text,
    }


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    rag_store.ensure_schema(connection)
    yield connection
    connection.close()


# ── 副本表与 rag_chunks 同源（AC0b 后半） ────────────────────────────────────


def test_plain_copy_table_is_written_from_the_same_insert(conn):
    """AC0b：普通表副本与 rag_chunks 同源写入，chunk_id 一一对应无遗漏。"""
    rows = [_row(f"c{i}", f"第{i}段投标报价内容") for i in range(5)]
    rag_store.insert_rows(conn, rows)

    fts_ids = {r[0] for r in conn.execute("SELECT chunk_id FROM rag_chunks")}
    plain_ids = {r[0] for r in conn.execute(f"SELECT chunk_id FROM {rag_store.SCAN_TABLE_NAME}")}
    assert fts_ids == plain_ids == {f"c{i}" for i in range(5)}


def test_delete_for_file_clears_both_tables(conn):
    """重建索引时两表必须同步清——只清一张会留下永远命中的幽灵副本。"""
    rag_store.insert_rows(conn, [_row("a1", "甲文本", file="甲.pdf")])
    rag_store.insert_rows(conn, [_row("b1", "乙文本", file="乙.pdf")])
    rag_store.delete_rows_for_file(conn, "甲.pdf")

    assert {r[0] for r in conn.execute("SELECT chunk_id FROM rag_chunks")} == {"b1"}
    assert {
        r[0] for r in conn.execute(f"SELECT chunk_id FROM {rag_store.SCAN_TABLE_NAME}")
    } == {"b1"}


# ── 通道选择 ────────────────────────────────────────────────────────────────


def test_two_char_chinese_query_hits_via_substring_channel(conn):
    """S0-B 的核心反例：「报价」在 FTS5 侧 MATCH/LIKE 双双为 0，必须由子串通道兜住。"""
    rag_store.insert_rows(
        conn, [_row("c1", "投标报价：人民币壹佰贰拾万元整。报价一览表见附件。")]
    )
    assert rag_store.query_rows(conn, rag._escape_match_query("报价"), tag=None, limit=5) == []

    hits = rag.search("报价", conn=conn, limit=5)
    assert [hit["chunk_id"] for hit in hits] == ["c1"]
    assert hits[0]["page_anchor"], "子串通道也必须带出页锚"


@pytest.mark.parametrize("query", ["业绩", "工期", "资质", "报价"])
def test_common_two_char_item_names_are_all_reachable(conn, query):
    """这四个 2 字评分项名在评标里极常见——任一零命中就是"可见但不可用"。"""
    rag_store.insert_rows(
        conn, [_row("c1", "投标报价、类似业绩、计划工期、企业资质均详见后附材料。")]
    )
    assert [hit["chunk_id"] for hit in rag.search(query, conn=conn, limit=5)] == ["c1"]


def test_three_char_query_still_uses_fts_bm25_ranking(conn):
    """≥3 字维持既有 FTS5 BM25 行为——招标侧检索零回归风险。"""
    rag_store.insert_rows(
        conn,
        [
            _row("weak", "施工组织设计一处提及。"),
            _row("strong", "施工组织设计详述：施工组织设计方案，施工组织设计要点。"),
        ],
    )
    hits = rag.search("施工组织设计", conn=conn, limit=5)
    assert [hit["chunk_id"] for hit in hits] == ["strong", "weak"], "BM25 应把高密度块排前"


def test_substring_channel_respects_tag_and_limit(conn):
    """两个通道的过滤语义必须一致，否则按 tag 取招标/投标会串。"""
    rag_store.insert_rows(
        conn,
        [
            _row("t1", "报价说明在招标文件", tag="evaluation_method"),
            _row("b1", "报价一览表在投标文件", tag="bid"),
            _row("b2", "报价明细表在投标文件", tag="bid"),
        ],
    )
    assert [h["chunk_id"] for h in rag.search("报价", conn=conn, tag="bid", limit=5)] == [
        "b1",
        "b2",
    ]
    assert len(rag.search("报价", conn=conn, tag="bid", limit=1)) == 1


def test_zero_hit_stays_zero_hit(conn):
    """不得为了凑命中率放宽匹配——查不到就是查不到，由上层记 evidence_unresolved。"""
    rag_store.insert_rows(conn, [_row("c1", "本段与查询词无关。")])
    assert rag.search("报价", conn=conn, limit=5) == []
    assert rag.search("施工组织设计", conn=conn, limit=5) == []


# ── 反过度设计 / 安全 ────────────────────────────────────────────────────────


def test_like_wildcards_in_query_are_escaped(conn):
    """查询串来自 criteria（模型输出）——``%``/``_`` 必须转义，否则 ``%`` 匹配一切。"""
    rag_store.insert_rows(conn, [_row("c1", "本段不含百分号。")])
    assert rag.search("%", conn=conn, limit=5) == []
    assert rag.search("_", conn=conn, limit=5) == []


def test_no_hardcoded_phrase_expansion_table(conn):
    """守卫：S0-B 已证伪"词缀扩展"路线（62% 且换标书失效），不得偷偷加回来。

    判据取自那条路线的形态——把 2 字词映射到一串猜测短语的静态表。
    """
    import inspect

    source = inspect.getsource(rag)
    for banned in ("报价一览", "投标报价\"", "_PHRASE_EXPANSIONS", "_QUERY_SYNONYMS"):
        assert banned not in source, f"检索层不得出现硬编码词缀扩展：{banned}"
