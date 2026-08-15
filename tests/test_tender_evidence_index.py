"""S3b · 证据层：投标入索引 + chunk 二次切分 + 按项检索组装（AC4/AC5/AC2）。

缺口（2026-08-15 实测）：``context_slim.py`` 只索引招标文件，**投标文件从未入索引**；
而投标底稿 370,529 字，"全塞进单次会话"这个前提早已破产——分给谁都不够。

S0-B 实测的两个形态约束：
- chunk 字数 min 21 / 中位 212 / p90 3,453 / **max 26,107**，10 个超 8,000 → 二次切分必需；
- ``build_doc_structure`` 对投标能出 60 章节，但 OCR 认不出结构时会退化成单个巨 chunk。
"""

from __future__ import annotations

import sqlite3

import pytest

from server.tender import evidence_chunks as ch
from server.tender import evidence_index as ev


def _criteria() -> dict:
    return {
        "eligibility_rules": [{"check": "营业执照", "requirement": "有效期内"}],
        "items": [
            {"item": "报价", "max": 40},
            {"item": "施工组织设计", "max": 30},
            {"item": "技术参数偏差", "max": 30, "basis": "逐条响应招标文件第三章技术参数"},
        ],
    }


# ── chunk 二次切分 ──────────────────────────────────────────────────────────


def test_oversized_chunk_is_split_with_page_anchors():
    """26,107 字的巨 chunk 必须切开，且每片带得回页锚——证据链页码不能靠模型推算。"""
    body = "\n".join(f"【第{page}页】\n" + "投标正文内容。" * 400 for page in range(1, 6))
    chunk = {
        "chunk_id": "投标.pdf#0",
        "file": "投标.pdf",
        "chapter_path": "技术标",
        "chapter_title": "技术标",
        "tag": "bid",
        "page_start": 1,
        "page_end": 5,
        "page_artifact": "original",
        "chunk_text": body,
    }
    pieces = ch.split_oversized_chunks([chunk])

    assert len(pieces) > 1, "超限 chunk 必须切开"
    assert all(len(p["chunk_text"]) <= ch.MAX_CHUNK_CHARS for p in pieces)
    assert len({p["chunk_id"] for p in pieces}) == len(pieces), "切片 chunk_id 必须唯一"
    assert all(p["page_start"] is not None for p in pieces), "每片都要带页锚"
    # 页锚必须**跟着内容走**，不能整片都挂到原 chunk 的首页。
    assert {p["page_start"] for p in pieces} != {1}


def test_small_chunks_pass_through_untouched():
    """未超限的 chunk 原样透传——不制造无谓切分（S0-B 中位仅 212 字）。"""
    chunk = {
        "chunk_id": "投标.pdf#1",
        "file": "投标.pdf",
        "chapter_path": "商务标",
        "chapter_title": "商务标",
        "tag": "bid",
        "page_start": 2,
        "page_end": 2,
        "page_artifact": "original",
        "chunk_text": "投标报价：壹佰贰拾万元。",
    }
    assert ch.split_oversized_chunks([chunk]) == [chunk]


def test_structureless_text_still_produces_page_anchored_chunks():
    """OCR 认不出章节时按页级 + 定长切，绝不退化成 0 chunk 或单个巨 chunk。"""
    body = "\n".join(f"【第{page}页】\n" + "无结构正文。" * 300 for page in range(1, 4))
    chunks = ch.build_chunks(body, file_name="投标.pdf", tag="bid")

    assert len(chunks) >= 3
    assert all(len(c["chunk_text"]) <= ch.MAX_CHUNK_CHARS for c in chunks)
    assert {c["page_start"] for c in chunks} >= {1, 2, 3}


def test_empty_text_produces_no_chunks():
    assert ch.build_chunks("", file_name="投标.pdf", tag="bid") == []


# ── 投标 + 招标同入索引 ──────────────────────────────────────────────────────


def test_both_layers_are_indexed(tmp_path):
    """AC4/KD1-F5：投标入索引（此前完全缺失），招标索引同样参与检索。"""
    conn = sqlite3.connect(":memory:")
    stats = ev.build_evidence_index(
        conn,
        tender_text="# 第三章 技术参数\n技术参数表：额定功率不小于 50kW。",
        bid_text="# 商务标\n投标报价：壹佰贰拾万元。\n# 技术标\n施工组织设计详见本章。",
        project_id="tp-1",
    )
    assert stats.bid_chunks > 0, "投标必须入索引"
    assert stats.tender_chunks > 0, "招标索引同样参与检索"

    files = {r[0] for r in conn.execute("SELECT DISTINCT file FROM rag_chunks")}
    assert len(files) == 2, "两层必须是不同 file，否则重建时会互相清掉"
    conn.close()


def test_index_is_rebuilt_idempotently():
    """现场补建可能重复触发——重建必须幂等，不能把同一份文本累积成两份 chunk。"""
    conn = sqlite3.connect(":memory:")
    args = {"tender_text": "# 第一章 评标办法\n评分标准。", "bid_text": "# 商务标\n报价表。"}
    first = ev.build_evidence_index(conn, project_id="tp-1", **args)
    second = ev.build_evidence_index(conn, project_id="tp-1", **args)
    assert first.total_chunks == second.total_chunks
    assert (
        conn.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0] == second.total_chunks
    )
    conn.close()


# ── 按项检索组装 ────────────────────────────────────────────────────────────


@pytest.fixture
def indexed_conn():
    conn = sqlite3.connect(":memory:")
    ev.build_evidence_index(
        conn,
        tender_text=(
            "# 第三章 技术参数\n技术参数偏差表：额定功率不小于 50kW，防护等级 IP54。"
        ),
        bid_text=(
            "# 商务标\n投标报价：壹佰贰拾万元整。报价一览表见附表。\n"
            "# 技术标\n施工组织设计详见本章，施工组织设计要点如下。\n"
            "# 资格证明\n营业执照副本附后，有效期至 2030 年。"
        ),
        project_id="tp-1",
    )
    yield conn
    conn.close()


def test_每项都拿到证据且带页锚(indexed_conn):
    """AC7：证据链页锚来自检索结果，不靠模型从大段底稿自己数页码。"""
    result = ev.retrieve_evidence(_criteria(), conn=indexed_conn, query_count_hint=None)

    assert result.unresolved == [], f"不应有零命中项：{result.unresolved}"
    assert all(block.page_anchor for block in result.blocks)


def test_两字项名也能命中(indexed_conn):
    """「报价」这类 2 字项名正是裸用 FTS5 时全军覆没的一类。"""
    result = ev.retrieve_evidence(
        {"items": [{"item": "报价", "max": 40}]}, conn=indexed_conn, query_count_hint=None
    )
    assert result.unresolved == []
    assert any("报价" in block.text for block in result.blocks)


def test_basis_指向招标章节的项带出招标chunk(indexed_conn):
    """KD1-F5：criteria 只有项名和满分，装不下技术参数表；该类项必须带出招标原文。"""
    result = ev.retrieve_evidence(
        {"items": [{"item": "技术参数偏差", "max": 30, "basis": "逐条响应招标文件第三章技术参数"}]},
        conn=indexed_conn,
        query_count_hint=None,
    )
    assert any(block.scope == "tender" for block in result.blocks), "应带出招标侧 chunk"


def test_零命中项记录实际用过的查询串(indexed_conn):
    """AC2/AC7：零命中不判 0，且要告诉用户检索了什么——便于分辨漏检还是真没有。"""
    result = ev.retrieve_evidence(
        {"items": [{"item": "现场答辩得分", "max": 10}]},
        conn=indexed_conn,
        query_count_hint=None,
    )
    assert len(result.unresolved) == 1
    unresolved = result.unresolved[0]
    assert unresolved.item == "现场答辩得分"
    assert unresolved.queries, "必须记录实际用过的查询串"
    assert unresolved.hit_count == 0


def test_跨项去重按chunk_id(indexed_conn):
    """多个评分项常命中同一 chunk（如同一张报价表）——组装期必须先去重再计账。"""
    criteria = {
        "items": [
            {"item": "报价", "max": 40},
            {"item": "投标报价", "max": 20},
            {"item": "报价一览表", "max": 10},
        ]
    }
    result = ev.retrieve_evidence(criteria, conn=indexed_conn, query_count_hint=None)
    ids = [block.chunk_id for block in result.blocks]
    assert len(ids) == len(set(ids)), "同一 chunk 不得重复注入"


def test_注入量受闭式账目约束(indexed_conn, monkeypatch):
    """AC5：组装产物必须落在预算内——账目在这里从公式变成可断言的事实。"""
    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", "200000")
    result = ev.retrieve_evidence(_criteria(), conn=indexed_conn, query_count_hint=None)
    assert result.total_tokens <= result.plan.evidence_tokens


def test_注入量与投标体量脱钩(monkeypatch):
    """AC5 的判据句：同一招标 + 40 页 / 400 页两份投标，注入量差异 ≤20%。"""
    tender = "# 第三章 技术参数\n技术参数偏差表：额定功率不小于 50kW。"
    small = (
        "# 商务标\n投标报价：壹佰贰拾万元。\n"
        "# 技术标\n施工组织设计详见本章。技术参数偏差表逐条响应。\n"
        "# 资格证明\n营业执照副本附后，有效期至 2030 年。"
    )
    large = small + "\n" + "\n".join(f"【第{p}页】\n附件正文。" * 20 for p in range(2, 400))

    sizes = []
    for bid_text in (small, large):
        conn = sqlite3.connect(":memory:")
        ev.build_evidence_index(conn, tender_text=tender, bid_text=bid_text, project_id="tp-1")
        result = ev.retrieve_evidence(_criteria(), conn=conn, query_count_hint=None)
        # 反"trivially 通过"：两边都必须真的检出证据。全部 unresolved 时注入量也"相等"，
        # 那是检索失效而不是脱钩成功。
        assert result.unresolved == [], f"投标 {len(bid_text)} 字时漏检：{result.unresolved}"
        assert result.blocks, "必须真的检出证据"
        sizes.append(result.total_tokens)
        conn.close()

    assert max(sizes) <= min(sizes) * 1.2, f"注入量随投标体量漂移：{sizes}"
    # 400 页那份的原文是 40 页那份的 100 倍量级——注入量却不随之增长，这才是 KD1 的目标。
    assert max(sizes) < len(large) / 10
