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
from server.tender import evidence_retrieval as er


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


def test_章节结构必须真的被用上():
    """回归守卫：章节级切分曾因 ``dict(tuple)`` 抛 ValueError 被 except 吞掉，导致**每一份
    文档都静默退化成整份单 chunk**——章节切分形同虚设，只在日志里留一行 warning。

    这正是本 sprint 要根治的形态（静默降级），故用"一章一 chunk"直接断言，不看日志。
    """
    text = (
        "# 第一章 评标办法\n技术方案评分章节内容。\n"
        "# 第二章 资格审查\n营业执照资格章节内容。\n"
        "# 第三章 商务条款\n商务条款章节独有内容。"
    )
    chunks = ch.build_chunks(text, file_name="__tender__", tag=None)

    assert len(chunks) == 3, f"应按章节切成 3 个 chunk，实得 {len(chunks)}"
    assert not any("商务条款章节独有内容" in c["chunk_text"] for c in chunks[:2])
    assert {c["chapter_title"] for c in chunks} == {
        "第一章 评标办法",
        "第二章 资格审查",
        "第三章 商务条款",
    }


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
    result = er.retrieve_evidence(_criteria(), conn=indexed_conn, query_count_hint=None)

    assert result.unresolved == [], f"不应有零命中项：{result.unresolved}"
    assert all(block.page_anchor for block in result.blocks)


def test_两字项名也能命中(indexed_conn):
    """「报价」这类 2 字项名正是裸用 FTS5 时全军覆没的一类。"""
    result = er.retrieve_evidence(
        {"items": [{"item": "报价", "max": 40}]}, conn=indexed_conn, query_count_hint=None
    )
    assert result.unresolved == []
    assert any("报价" in block.text for block in result.blocks)


def test_basis_指向招标章节的项带出招标chunk(indexed_conn):
    """KD1-F5：criteria 只有项名和满分，装不下技术参数表；该类项必须带出招标原文。"""
    result = er.retrieve_evidence(
        {"items": [{"item": "技术参数偏差", "max": 30, "basis": "逐条响应招标文件第三章技术参数"}]},
        conn=indexed_conn,
        query_count_hint=None,
    )
    assert any(block.scope == "tender" for block in result.blocks), "应带出招标侧 chunk"


def test_零命中项记录实际用过的查询串(indexed_conn):
    """AC2/AC7：零命中不判 0，且要告诉用户检索了什么——便于分辨漏检还是真没有。"""
    result = er.retrieve_evidence(
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
    result = er.retrieve_evidence(criteria, conn=indexed_conn, query_count_hint=None)
    ids = [block.chunk_id for block in result.blocks]
    assert len(ids) == len(set(ids)), "同一 chunk 不得重复注入"


def test_注入量受闭式账目约束(indexed_conn, monkeypatch):
    """AC5：组装产物必须落在预算内——账目在这里从公式变成可断言的事实。"""
    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", "200000")
    result = er.retrieve_evidence(_criteria(), conn=indexed_conn, query_count_hint=None)
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
        result = er.retrieve_evidence(_criteria(), conn=conn, query_count_hint=None)
        # 反"trivially 通过"：两边都必须真的检出证据。全部 unresolved 时注入量也"相等"，
        # 那是检索失效而不是脱钩成功。
        assert result.unresolved == [], f"投标 {len(bid_text)} 字时漏检：{result.unresolved}"
        assert result.blocks, "必须真的检出证据"
        sizes.append(result.total_tokens)
        conn.close()

    assert max(sizes) <= min(sizes) * 1.2, f"注入量随投标体量漂移：{sizes}"
    # 400 页那份的原文是 40 页那份的 100 倍量级——注入量却不随之增长，这才是 KD1 的目标。
    assert max(sizes) < len(large) / 10


# ── F5：预算耗尽不得逐项静默饿死 ────────────────────────────────────────────


def test_额度耗尽的项被记为truncated而不是静默消失(monkeypatch):
    """F5：额度用尽后有命中的项其块被丢，此前既不进 unresolved 也无 warning。

    排序靠前的项有证据、靠后的既无证据也无痕迹——用户看到的是一份"证据齐全"的注入块，
    实际上后半截项全是空的。这违反 AC2「无静默路径」。

    本条自建索引而不用 ``indexed_conn``：P0.1 给证据额度加了下界（不得低于 criteria 实测
    额度），故"饿死排序靠后的项"必须靠**把 chunk 做大**来构造，而不能靠把额度压到近零——
    后者现在是 ``InjectionBudgetExhausted``，是另一条路径。
    """
    from server.tender import injection_budget as budget

    criteria = _criteria()
    total = 200_000
    margin = total // 4
    # 下界 = criteria 实测额度；每块做成下界的 2/3，于是一块装得下、两块装不下。
    floor = budget.criteria_tokens(criteria)
    body = "本项应答正文。" * (floor * 2 // 3 // len("本项应答正文。"))
    conn = sqlite3.connect(":memory:")
    ev.build_evidence_index(
        conn,
        tender_text=f"# 第三章 技术参数\n技术参数偏差表：额定功率不小于 50kW。{body}",
        bid_text=(
            f"# 商务标\n投标报价：壹佰贰拾万元整。{body}\n"
            f"# 技术标\n施工组织设计详见本章。{body}\n"
            f"# 资格证明\n营业执照副本附后。{body}"
        ),
        project_id="tp-1",
    )
    scaffold = total - margin - floor - floor
    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", str(total))
    monkeypatch.setenv("TENDER_SCAFFOLD_RESERVE_TOKENS", str(scaffold))

    result = er.retrieve_evidence(criteria, conn=conn)
    conn.close()

    all_items = {name for name, _ in er._item_queries(criteria)}
    starved = set(result.truncated)
    assert result.blocks, "至少排序靠前的项要拿到证据"
    assert starved, "被额度饿死的项必须留痕，不能既不出块也不出声"
    assert starved <= all_items
    assert all_items - starved, "不该整批都被饿死（那是预算不可达，由 InjectionBudgetExhausted 管）"


def test_额度充足时没有任何项被记为truncated(indexed_conn):
    """反向守卫：正常路径不得凭空报 truncated，否则这条信号会被无视。"""
    result = er.retrieve_evidence(_criteria(), conn=indexed_conn)

    assert result.truncated == []


def test_跨项去重命中的项不算被饿死(indexed_conn):
    """去重把本项的块归给了前一项——证据仍在注入块里，不构成"这项没证据"。"""
    criteria = {"items": [{"item": "投标报价", "max": 40}, {"item": "投标报价", "max": 10}]}

    result = er.retrieve_evidence(criteria, conn=indexed_conn)

    assert result.truncated == []


# ── F6：structure/body 不匹配要有专用异常，归因面不得罩住整段 ────────────────


def test_structure_body_不匹配抛专用异常类型():
    """F6：mismatch 有自己的类型，调用方才能只捕它而不误伤别的 ValueError。"""
    from server.ocr import rag
    from server.ocr.docstructure import build_doc_structure

    structure = build_doc_structure("# 第一章 甲\n甲正文。\n# 第二章 乙\n乙正文。", file_name="x")

    with pytest.raises(rag.StructureBodyMismatchError):
        rag._chunk_spans(structure, "换了一份没有任何标题行的正文。")


def test_专用异常仍是ValueError子类():
    """向后兼容：既有 ``except ValueError`` 的调用方行为不变。"""
    from server.ocr import rag

    assert issubclass(rag.StructureBodyMismatchError, ValueError)


def test_真mismatch仍退回整份切分(monkeypatch):
    """行为保持：确属 structure/body 不匹配时退回整份切分，不让整层索引失灭。"""
    from server.ocr import rag

    def boom(*_a, **_kw):
        raise rag.StructureBodyMismatchError("structure/body 不匹配")

    monkeypatch.setattr(ch, "index_document", boom)

    chunks = ch.build_chunks("# 第一章 甲\n正文。", file_name="__bid__", tag="bid")

    assert len(chunks) == 1, "退回整份单 chunk"


def test_其它ValueError不再被误当成mismatch静默吞掉(monkeypatch):
    """F6 核心：``except ValueError`` 罩住 index_document + dict(row) 全段时，任何别的
    ValueError 都会被当成"结构不匹配"静默退化——章节级切分形同虚设，只在日志留一行。
    """
    def boom(*_a, **_kw):
        raise ValueError("完全无关的解析失败")

    monkeypatch.setattr(ch, "index_document", boom)

    with pytest.raises(ValueError, match="完全无关"):
        ch.build_chunks("# 第一章 甲\n正文。", file_name="__bid__", tag="bid")


# ── S5/KD6：出处保真 + 索引去重 + 证据取满（2026-08-17 第四轮实跑） ──────────


def _paged(page: int, text: str) -> str:
    return f"【第{page}页】\n{text}"


def test_切片标签跟着自身小节标题走():
    """KD6-a：切片自带小节标题时，``chapter_path`` 末端必须是它自己。

    实测形态（第四轮）：投标用 ``4.8.`` 十进制编号，``chapter_heading`` 不认，于是
    「十、雷击事故应急预案」一路吞到 p349，业绩表的出处行渲染成 `【…雷击事故应急预案】
    【第317页】`——内容对、出处错，回查闸失去依据。切片首行是**直接观测到的事实**，
    祖先链是结构解析的**推断**；推断失效时不该让它继续冒充出处。
    """
    body = "# 十、雷击事故应急预案\n" + "\n".join(
        [
            _paged(307, "雷击应急处置流程。" * 600),
            _paged(317, "4.8.类似业绩\n序号 项目名称 合同金额\n1 某视听系统建设项目 375000 元"),
        ]
    )
    chunks = ch.build_chunks(body, file_name="__bid__", tag="bid")

    hit = next(c for c in chunks if "4.8.类似业绩" in c["chunk_text"])
    assert hit["chapter_path"].endswith("4.8.类似业绩"), (
        f"出处末端应是切片自身的小节标题，实得 {hit['chapter_path']!r}"
    )
    # 没有自带标题的切片仍沿用继承来的路径（有什么说什么，不留空）。
    other = next(c for c in chunks if "雷击应急处置流程" in c["chunk_text"])
    assert "雷击事故应急预案" in other["chapter_path"]


def test_父子节点产出的重复正文被去重():
    """KD6-b：``_chunk_spans`` 对每个树节点各出一块，父节点 span 含子孙正文，
    切片又在页锚处重新对齐 → 产出逐字相同、仅 chunk_id 不同的块。

    实测：真实投标 645 chunk / 不同文本仅 509 / 冗余 61,790 字 = 20%。按 chunk_id 去重
    看不见这种重复，放开取量后它会直接吃掉扩出来的额度。
    """
    body = "# 一、总体方案\n" + "\n".join(
        [
            _paged(1, "总体方案概述。" * 300),
            "（一）子方案\n" + _paged(2, "子方案正文。" * 300),
            _paged(3, "子方案续页正文。" * 300),
        ]
    )
    chunks = ch.build_chunks(body, file_name="__bid__", tag="bid")

    texts = [c["chunk_text"] for c in chunks]
    assert len(texts) == len(set(texts)), (
        f"同一段正文不得入索引两次：{len(texts)} 块 / {len(set(texts))} 份不同正文"
    )


def test_chunk按页码升序入库使rowid等于文档顺序():
    """KD6-b：``scan_rows`` 注释里写着"ORDER BY rowid = 文档顺序"，但 DFS 先序 + 父子
    交错会让 rowid 与页码脱节。续接取"后续块"依赖这条，故由排序**构造保证**它成立。
    """
    body = "# 一、甲章\n" + "\n".join(
        [
            _paged(1, "甲章正文。" * 300),
            "（一）甲子节\n" + _paged(2, "甲子节正文。" * 300),
            _paged(3, "甲子节续页。" * 300),
        ]
    )
    chunks = ch.build_chunks(body, file_name="__bid__", tag="bid")

    pages = [c["page_start"] for c in chunks if c["page_start"] is not None]
    assert pages == sorted(pages), f"入库顺序必须是文档顺序，实得页码序列 {pages}"


def _tech_bid() -> str:
    """项名只出现在小节标题里、正文不含该词——第四轮实测的真实形态。"""
    return "# 技术标\n" + "\n".join(
        [
            _paged(1, "投标文件商务部分正文。" * 300),
            _paged(2, "4.10.技术参数指标\n技术部分产品常规参数正负偏离表"),
            _paged(3, "核心影像参数：分辨率不低于 4K，帧率不低于 50fps。" + "参数明细。" * 280),
            _paged(4, "屏幕与交互：显示器不小于 21.5 寸液晶显示屏。" + "参数明细。" * 280),
        ]
    )


def test_命中小节标题时续接后续正文():
    """KD6-c：评分项名只出现在小节标题里，正文（偏离表行/业绩表/方案正文）不含该词，
    **因此加大检索 limit 一定无效**——实测 `技术参数指标` 全文字面命中仅 2 块且互为重复。

    第四轮实测后果：25 分的项只拿到 221 字（标题 + 表头，零行参数），模型据此评分必然错判。
    """
    conn = sqlite3.connect(":memory:")
    ev.build_evidence_index(
        conn, tender_text="# 第三章 技术参数\n额定功率不小于 50kW。", bid_text=_tech_bid(),
        project_id="tp-1",
    )
    result = er.retrieve_evidence(
        {"items": [{"item": "技术参数指标", "max": 25}]}, conn=conn, query_count_hint=None
    )
    conn.close()

    injected = "\n".join(block.text for block in result.blocks)
    assert "4.10.技术参数指标" in injected, "命中块本身要在"
    assert "核心影像参数" in injected, "后续正文必须随命中块一起注入，否则只有表头可评"
    assert "屏幕与交互" in injected


def test_单项续接不得吃光全局额度():
    """KD6-c：续接必须按**每项**额度封顶。否则排序靠前的项会把 ``evidence_tokens``
    吃光，后面的项全部 truncated——那正是 F5 要防的静默饿死，只是换成由续接引发。
    """
    conn = sqlite3.connect(":memory:")
    ev.build_evidence_index(
        conn,
        tender_text="# 第三章 技术参数\n额定功率不小于 50kW。",
        bid_text=_tech_bid()
        + "\n"
        + "\n".join(
            [
                _paged(5, "投标报价：壹佰贰拾万元整。" + "报价明细。" * 280),
                _paged(6, "营业执照副本附后。" + "资格材料。" * 280),
            ]
        ),
        project_id="tp-1",
    )
    criteria = {
        "items": [
            {"item": "技术参数指标", "max": 25},
            {"item": "投标报价", "max": 40},
            {"item": "营业执照", "max": 10},
        ]
    }
    result = er.retrieve_evidence(criteria, conn=conn, query_count_hint=None)
    conn.close()

    assert result.unresolved == [], f"不该有零命中项：{result.unresolved}"
    assert result.truncated == [], f"排序靠后的项被前面的项吃光额度：{result.truncated}"
    assert result.total_tokens <= result.plan.evidence_tokens


def _section(page: int, heading: str, filler: str) -> str:
    """一页：小节标题 + 足量正文（让整份超过 MAX_CHUNK_CHARS 而在页锚处切开）。"""
    return _paged(page, heading + "\n" + filler * 200)


def test_续接止于下一个被命中的块():
    """S7/hit-stop：终点是**下一个被任何评分项命中的块**，不是靠编号排版认出来的小节。

    改写自 ``test_续接止于同族同级的下一小节``（S5 的排版边界语义）。要防的坏形态没变：
    第四轮实测不设边界时「企业综合实力」一路吃进「类似业绩」整节共 39 块，模型会在错误的
    小节里给企业实力打分，**比证据少更糟**。变的是判据——各项的命中点天然把文档分了段，
    用它当终点不需要对编号风格作任何假设（``4.7.x`` 子节仍跟着命中块来，因为没有项命中它）。

    「谁吃了那一块」在 ``blocks`` 里看不出来（跨项去重后同一块只出现一次），故判据落在
    逐项注入量上：邻项自己还留得住证据，就说明边界收在它前面。
    """
    conn = sqlite3.connect(":memory:")
    ev.build_evidence_index(
        conn,
        tender_text="# 第三章 技术参数\n额定功率不小于 50kW。",
        bid_text="# 十、雷击事故应急预案\n"
        + "\n".join(
            [
                _section(315, "4.7.企业综合实力", "企业资质与荣誉说明。"),
                _section(316, "4.7.2.具有有效期内的企业安全生产许可证", "许可证明细。"),
                _section(317, "4.8.类似业绩", "业绩明细表内容。"),
            ]
        ),
        project_id="tp-1",
    )
    result = er.retrieve_evidence(
        {"items": [{"item": "企业综合实力", "max": 6}, {"item": "类似业绩", "max": 9}]},
        conn=conn,
        query_count_hint=9,
    )
    conn.close()

    injected = "\n".join(block.text for block in result.blocks)
    assert "4.7.企业综合实力" in injected
    assert "安全生产许可证" in injected, "命中块与下一个停止点之间的正文必须跟着来"
    volume = dict(result.item_tokens)
    assert volume["类似业绩"] > 0, (
        f"下一个被命中的块归它自己，不得被前一项吃掉：{result.item_tokens}"
    )


def test_无实质内容的块不作为证据注入():
    """实测：投标 p319-344 是合同扫描件，PDF 文本层只剩一个页码（14 字），
    而每块还要带一行出处抬头——注入它们等于用噪音挤掉真证据。

    判据不设字数阈值：**正文除页锚外没有任何文字**（只剩页码数字）即无实质内容。
    """
    conn = sqlite3.connect(":memory:")
    ev.build_evidence_index(
        conn,
        tender_text="# 第三章 技术参数\n额定功率不小于 50kW。",
        bid_text="# 十、雷击事故应急预案\n"
        + "\n".join(
            [
                _section(317, "4.8.类似业绩", "业绩表：某视听系统建设项目 375000 元。"),
                _paged(318, "318"),
                _paged(319, "319"),
                _section(320, "4.8.1.示例中心视听系统建设项目", "合同要点摘录。"),
            ]
        ),
        project_id="tp-1",
    )
    result = er.retrieve_evidence(
        {"items": [{"item": "类似业绩", "max": 9}]}, conn=conn, query_count_hint=9
    )
    conn.close()

    anchors = [block.page_anchor for block in result.blocks]
    assert not any("318" in anchor for anchor in anchors), f"空白扫描页不该进注入：{anchors}"
    assert not any("319" in anchor for anchor in anchors), f"空白扫描页不该进注入：{anchors}"
    assert any("合同要点摘录" in block.text for block in result.blocks), (
        "跳过空白页后仍须继续取到后面的真内容"
    )


# ── S6/KD7：零命中时按「共享连续原文」回退 ──────────────────────────────────


def _scoring_response_bid() -> str:
    """投标的评分应答节：小节标题用招标的措辞，但与**项名**词序相反（实测形态）。

    招标项名 `视听系统总体方案设计` / 招标细则 `需求及总体设计方案…` / 投标标题
    `4.1.项目需求及总体设计方案`——项名与投标只共享「总体」「设计」「方案」这些 2 字碎片
    （方案设计 vs 设计方案），而细则与投标共享**连续 9 个字**。
    """
    return "# 4.综合评审评分项\n" + "\n".join(
        [
            _section(21, "4.1.项目需求及总体设计方案", "演播室建设需求与设计说明。"),
            _section(30, "4.2.关键技术、工艺", "关键技术难点与工艺说明。"),
        ]
    )


_BASIS = "需求及总体设计方案优化完美，产品选型合理的得5分；未提供不得分。"


def _indexed(bid_text: str) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    ev.build_evidence_index(
        conn,
        tender_text="# 第三章 技术参数\n额定功率不小于 50kW。",
        bid_text=bid_text,
        project_id="tp-1",
    )
    return conn


def test_整串零命中时按连续原文重合回退():
    """KD7：项名整串必然零命中（投标不含该串），而 basis 与投标标题共享连续 9 个字。

    现状为什么捞不到：``_escape_match_query`` 只按**空白**拆 OR，中文句子没有空白 →
    整段 basis 被包成单个 phrase，trigram 索引上等价于要求整段逐字出现 → 恒 0。
    这一项在真实标书上值 **15 分**，零命中即整单无法自动完成。
    """
    conn = _indexed(_scoring_response_bid())
    result = er.retrieve_evidence(
        {"items": [{"item": "视听系统总体方案设计", "max": 15, "basis": _BASIS}]},
        conn=conn,
        query_count_hint=9,
    )
    conn.close()

    assert result.unresolved == [], f"应由回退通道命中：{result.unresolved}"
    injected = "\n".join(block.text for block in result.blocks)
    assert "4.1.项目需求及总体设计方案" in injected, "回退要拿到 4.1 节本身，不是别处"


def test_回退要求连续原文重合_碎片不算证据():
    """噪音比缺失更危险：项名拆出的短碎片在正文里随处可见。

    实测（`/tmp/diag_ngram.py`）：命中块与查询串的最长公共连续子串，噪音 ≤5 字、真证据
    7-9 字，故取 6 字为窗口。**criteria 没有 basis 时该项应保持 unresolved**——拿碎片凑证据
    会让模型在错误证据上给分，而 unresolved 走人工。
    """
    conn = _indexed(_scoring_response_bid())
    result = er.retrieve_evidence(
        {"items": [{"item": "视听系统总体方案设计", "max": 15}]},  # 无 basis
        conn=conn,
        query_count_hint=9,
    )
    conn.close()

    assert result.blocks == [], "只共享 2 字碎片的块不得当证据"
    assert len(result.unresolved) == 1
    assert any("部分重合" in query for query in result.unresolved[0].queries), (
        f"回退尝试过也要留痕，否则用户分不清是整串没中还是连部分重合都没有：{result.unresolved[0].queries}"
    )


def test_整串能命中时不触发回退():
    """回退只在零命中时跑，故对已命中的项零影响——否则会把相关度更低的块混进来。

    判据落在 ``_search_item`` 的尝试记录上：注入块里含续接段（本来就不字面含查询串），
    按块判断分不出"回退跑了"还是"续接带进来的"。
    """
    conn = _indexed(_scoring_response_bid())
    hits, used = er._search_item(["关键技术、工艺"], conn=conn, limit=3)
    conn.close()

    assert hits, "整串应能命中"
    assert not any("部分重合" in query for query in used), f"整串命中就不该跑回退：{used}"


# ── S8：招标评分表抢位（两层同入索引后的通用缺陷） ──────────────────────────


_SCORING_TABLE_TENDER = (
    "# 第四章 评审方法和程序\n"
    "评分表：类似业绩 9 分；实施方案 5 分；培训方案 3 分。评审委员会按下表逐项打分。"
)


def _rivalry_conn() -> sqlite3.Connection:
    """两层都字面含项名的语料：招标评分表短、投标应答长 → BM25 天然偏向招标块。

    这正是 2026-08-17 第六轮实测的形态（`类似业绩` 首块 = 招标「第四章 评审方法和程序」，
    投标 755 字掉到 248 字）。三个要素缺一不可，否则复现不出抢位：项名在投标里**只出现在
    小节标题**一次（正文用别的措辞）、投标块比招标评分表长得多、两层同入一个索引。
    **语料必须真的复现抢位**，否则守卫测试"未红即绿"——上一版就是这么被删掉的。
    """
    conn = sqlite3.connect(":memory:")
    ev.build_evidence_index(
        conn,
        tender_text=_SCORING_TABLE_TENDER,
        bid_text="# 4.综合评审评分项\n"
        + "\n".join(
            [
                _paged(
                    317,
                    "4.8.类似业绩\n序号 项目名称 合同金额：某视听系统建设项目 375000 元。\n"
                    + "本项目已完成同类演播室建设，合同金额与工期均满足招标要求。" * 60,
                ),
                _paged(
                    330,
                    "4.9.实施方案\n实施步骤与进度安排说明。\n"
                    + "分阶段推进设备进场、系统集成与联调验收。" * 60,
                ),
            ]
        ),
        project_id="tp-1",
    )
    return conn


def test_语料确实复现抢位():
    """守住上一条测试的前提：不受修复影响的裸检索里，招标块**确实**压过投标块。

    这条断言走 ``rag.search``（不带层过滤），故修复前后都成立；它一旦转绿失效，说明
    ``_rivalry_conn`` 已不再复现缺陷，抢位守卫测试也就退化成永真式。
    """
    from server.ocr.rag import search

    conn = _rivalry_conn()
    hits = search("类似业绩", conn=conn, tag=None, limit=5)
    conn.close()

    assert hits, "两层都含该词，不该零命中"
    assert hits[0]["file"] == ev.TENDER_FILE, (
        f"语料没能复现抢位，守卫测试将失去意义：{[h['file'] for h in hits]}"
    )


def test_投标层优先_招标评分表不得抢占评分项证据():
    """评标判的是**投标应答**；招标评分表含全部项名，BM25 上压过投标应答就会顶掉真证据。

    第六轮实测：`类似业绩` 首块变成招标「第四章 评审方法和程序」、注入从 755 字掉到 248 字。
    招标规定本身已由 criteria 注入过，再占一次证据额度是净损失——模型据招标原文给投标打分。
    """
    conn = _rivalry_conn()
    result = er.retrieve_evidence(
        {"items": [{"item": "类似业绩", "max": 9}]}, conn=conn, query_count_hint=9
    )
    conn.close()

    assert result.blocks, "投标侧有应答，不该零命中"
    assert result.blocks[0].scope == "bid", (
        f"首块必须是投标应答，实得 {result.blocks[0].scope}：{result.blocks[0].chapter_path}"
    )
    assert all(block.scope == "bid" for block in result.blocks), (
        f"投标层有命中时招标块不得参与：{[(b.scope, b.chapter_path) for b in result.blocks]}"
    )
    assert any("375000" in block.text for block in result.blocks), "要拿到投标的业绩正文"


def test_投标层零命中时招标层仍参与():
    """投标层优先不等于把招标层关掉：投标里根本没有的项，招标原文仍是唯一可用证据。

    与 :func:`test_basis_指向招标章节的项带出招标chunk` 是同一条口径的两面——那条从
    ``basis`` 侧进，这条从"投标零命中"侧进。
    """
    conn = _rivalry_conn()
    result = er.retrieve_evidence(
        {"items": [{"item": "评审委员会", "max": 5}]}, conn=conn, query_count_hint=9
    )
    _, used = er._search_item(["评审委员会"], conn=conn, limit=3)
    conn.close()

    assert result.unresolved == [], f"招标层含该词，不该记零命中：{result.unresolved}"
    assert any(block.scope == "tender" for block in result.blocks), "投标零命中时招标层必须参与"
    # AC2：证据来自哪一层要留痕，否则用户分不清"投标里就是没有"与"检索没查投标"。
    assert any("招标层" in query for query in used), f"招标层兜底必须留痕：{used}"


# ── S7：续接边界改 hit-stop（去排版假设）+ 逐项注入量留痕 ────────────────────


_GAP_PAGE = "人员配置与荣誉证书续页说明。" * 200


def _unrecognized_numbering_bid(gap_pages: int = 1) -> str:
    """小节编号用半角 ``(一)``——**两个识别器都不认**（真实标书里这类写法很常见）。

    ``docstructure.chapter_heading`` 只认「第X章」「一、」「（一）」（全角括号），
    ``_DECIMAL_HEADING_RE`` 只认十进制且必须以点收尾。故本语料下"命中块是不是小节标题"
    这个问题恒答"不是"，S5 的排版边界在此**静默失效**。

    Args:
        gap_pages: 两个命中块之间垫几页正文。加大它就把下一个命中块推到前瞻额度之外
            （F2 复现形态），其余要素不变。
    """
    return "# 综合评审\n" + "\n".join(
        [
            _section(11, "(一) 企业综合实力", "企业资质与荣誉说明。"),
            *[_paged(page, _GAP_PAGE) for page in range(12, 12 + gap_pages)],
            _section(11 + gap_pages + 1, "(二) 类似业绩", "业绩明细表内容。"),
        ]
    )


def test_编号风格不被识别时仍按邻项命中续接():
    """AC14：续接的终点不该依赖"认得出编号风格"——认不出时旧代码**静默不续接**。

    旧行为（S5 排版边界）：命中块自身不是可识别小节标题 → 直接不续接。证据从"整节"缩成
    "一个标题块"，而这条路径既不进 ``unresolved`` 也不进 ``truncated``——**证据变薄且无痕**，
    正是本 sprint 要根治的静默降级形态。评分项名只出现在小节标题里是实测常态
    （``技术参数指标`` 全文字面命中仅 2 块且互为重复），所以这一变薄直接等于错判。

    新行为（hit-stop）：各项的命中点天然把文档分段，续接止于**下一个被任何项命中的块**，
    对编号风格零假设。
    """
    conn = _indexed(_unrecognized_numbering_bid())
    result = er.retrieve_evidence(
        {"items": [{"item": "企业综合实力", "max": 6}, {"item": "类似业绩", "max": 9}]},
        conn=conn,
        query_count_hint=9,
    )
    conn.close()

    injected = "\n".join(block.text for block in result.blocks)
    assert "(一) 企业综合实力" in injected, "命中块本身要在"
    assert "人员配置与荣誉证书续页说明" in injected, (
        "编号风格不被识别时续接静默不发生：25 分的项只拿得到一个标题块"
    )
    volume = dict(result.item_tokens)
    assert volume["类似业绩"] > 0, (
        f"续接必须止于邻项命中块，不得把下一个评分项的证据吃进上一项：{result.item_tokens}"
    )


def test_邻项命中块超出前瞻额度时续接不得归零():
    """pass3/F2：下一个命中块落在前瞻额度之外时，已收集的续接被**整批丢弃**。

    与上一条同语料形态（编号风格两个识别器都不认），只把两个命中块之间的正文撑到超过每项
    额度。旧实现在 ``used >= budget`` 处返回"没收在命中块上"，于是走排版兜底，而兜底在标题
    认不出时返回空——已取到的正文全丢，该项又只剩一个标题块。reviewer 实测：中间正文放大后
    该项 item_tokens 从 2873 掉到 28，且既不进 ``unresolved`` 也不进 ``truncated``。

    这条路径在生产口径下是**常态而非极端**：9 项时 per_item ≈ 6.6K token，而真实投标 163K
    字里相邻命中块的间隔通常远大于它（F7 记的 ``chunks_per_item`` 恒为 1 更放大该影响）。

    额度本身就是上界，故"保留到额度为止"不等于越预算——账目闭式仍由末两条断言咬住。
    """
    gap_pages = 6
    conn = _indexed(_unrecognized_numbering_bid(gap_pages))
    result = er.retrieve_evidence(
        {"items": [{"item": "企业综合实力", "max": 6}, {"item": "类似业绩", "max": 9}]},
        conn=conn,
        query_count_hint=9,
    )
    conn.close()

    # 语料前提守卫（同 test_语料确实复现抢位 的用意）：两个前提缺一条，这条测试就退化成
    # 上一条的副本而"未红即绿"——① 中间正文真的超出前瞻额度；② 命中块的编号确实不被识别。
    per_item = result.plan.per_item_tokens
    assert gap_pages * len(_GAP_PAGE) > per_item, (
        f"语料没把下一个命中块推到额度之外：{gap_pages} 页 × {len(_GAP_PAGE)} 字 vs 额度 {per_item}"
    )
    assert ch.slice_heading(result.blocks[0].text.splitlines()) is None, (
        f"语料前提失效：命中块的编号被识别出来了，走的是排版边界那条路：{result.blocks[0].text[:40]!r}"
    )

    volume = dict(result.item_tokens)
    injected = "\n".join(block.text for block in result.blocks)
    assert "人员配置与荣誉证书续页说明" in injected, "预算耗尽不得把已收集的续接整批丢弃"
    assert volume["企业综合实力"] >= per_item // 2, (
        f"续接归零：该项只剩标题块，注入量远低于它自己的额度 {per_item}：{result.item_tokens}"
    )
    assert volume["类似业绩"] > 0, f"邻项自己的证据不得被顺带吃掉：{result.item_tokens}"
    assert sum(tokens for _, tokens in result.item_tokens) == result.total_tokens
    assert result.total_tokens <= result.plan.evidence_tokens, "保留到额度为止不得越预算"


def test_逐项注入量逐项留痕含零值(indexed_conn):
    """AC15：``item_tokens`` 是"证据变薄"的唯一可见量纲，故**每一项都要有一行**。

    hit-stop 自身也有变薄面（邻项 unresolved 导致边界后移 / 噪音命中制造伪边界提前截断 /
    末项收尾），三者都不产生 unresolved 或 truncated。只有逐项注入量能让它们被看见——
    零命中项记 0 而不是从清单里消失，否则读者分不清"这项没证据"与"这项没被检索"。
    """
    criteria = {
        "eligibility_rules": [{"check": "营业执照", "requirement": "有效期内"}],
        "items": [{"item": "报价", "max": 40}, {"item": "现场答辩得分", "max": 10}],
    }

    result = er.retrieve_evidence(criteria, conn=indexed_conn, query_count_hint=None)

    volume = dict(result.item_tokens)
    assert [name for name, _ in result.item_tokens] == [
        name for name, _ in er._item_queries(criteria)
    ], "逐项留痕必须覆盖全部检索项且保持检索顺序"
    assert volume["报价"] > 0
    assert volume["现场答辩得分"] == 0, "零命中项必须显式记 0，不能从清单里消失"
    assert sum(tokens for _, tokens in result.item_tokens) == result.total_tokens, (
        "逐项之和必须等于总注入量，否则这本账对不上就没有可信度"
    )

