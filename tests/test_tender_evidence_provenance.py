"""review pass3 F1/F3 · 证据层注入块必须自带来源文件，出处回查闸才读得回正确归属。

F1 的形态：证据块按**检索顺序**拼接，而 ``corpus.parse_corpus`` 是**流式状态机**——遇到
``### 文件: X`` 后其后所有页锚一路归 X，直到下一个文件头。块自己不带文件头时，
``### 文件:`` 行是否落在某个 chunk 里完全取决于切分位置：招标块排在含投标文件头的块之后
就被整段记到投标文件名下，``tier`` 同时退化成 ``whole``；排在第一个文件头之前的块则连段
都不产（``flush`` 只在 ``cur_file is not None`` 时产段）——那一整块证据对回查闸不存在。

一家投标常含多份文件、每份页码各自从 1 重置，**file 级归属正是页号回查的前提**
（``page_status`` / ``locate_quote_pages`` 都按 file 分桶）。

F3 同根：块抬头没有文件名时，命令要求的「出处写文件名 + 第N页」在证据片段形态下写不出来。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from server.common.corpus import parse_corpus
from server.tender import evidence_chunks as ch
from server.tender import evidence_context as ec
from server.tender import evidence_index as ev
from server.tender import evidence_retrieval as er

PROJECT_ROOT = Path(__file__).resolve().parents[1]

_BUSINESS = "商务标.pdf"
_TECH = "技术标.pdf"
_TENDER_DOC = "招标文件.pdf"


def _head(name: str) -> str:
    """底稿文件头（与 ``pipeline.build_extraction_block`` 同形）。"""
    return f"### 文件: {name} (kind=pdf, route=native)"


# 招标层：评分表本身字面含全部项名——它排在投标块**之后**正是 F1 的误归属形态。
_TENDER_CORPUS = "\n".join(
    [
        _head(_TENDER_DOC),
        "【第 3 页】",
        "# 第四章 评审方法和程序",
        "评审委员会按下表逐项打分：类似业绩 9 分，实施方案 5 分。",
    ]
)

# 投标层：**一家投标两份文件**，两份页码都从第 1 页起（真实形态）。
_BID_CORPUS = "\n".join(
    [
        _head(_BUSINESS),
        "【第 1 页】",
        "# 商务标",
        "投标报价：壹佰贰拾万元整，报价一览表见附表。",
        _head(_TECH),
        "【第 1 页】",
        "# 技术标",
        "4.8.类似业绩",
        "本项目已完成同类演播室建设，合同金额 375000 元。",
    ]
)

# 检索顺序 = criteria 顺序：两个投标项在前、只有招标层才有的项在后。
_CRITERIA = {
    "items": [
        {"item": "投标报价", "max": 40},
        {"item": "类似业绩", "max": 9},
        {"item": "评审委员会", "max": 5},
    ]
}


def _context() -> str:
    result = ec.build_evidence_context(
        tender_text=_TENDER_CORPUS,
        bid_text=_BID_CORPUS,
        criteria=_CRITERIA,
        project_id="tp-1",
    )
    assert result.context is not None, f"证据层应接管本次评标：{result.warnings}"
    return result.context


def _segment_with(segments: list[dict[str, Any]], marker: str) -> dict[str, Any]:
    """取含 ``marker`` 的那一段；命中 0 段或多段都是归属出了问题，直接失败并报现场。"""
    hits = [seg for seg in segments if marker in seg["text"]]
    assert len(hits) == 1, (
        f"标记 {marker!r} 应恰好落在一段里，实得 {len(hits)} 段："
        f"{[(seg['tier'], seg['file'], seg['page']) for seg in hits]}"
    )
    return hits[0]


def test_证据层context逐段归属回它真正的来源文件():
    """F1 主判据：``parse_corpus`` 读回来的 ``(tier, file)`` 必须与块的真实来源一致。

    旧行为实测：三块拼在一起只解析出**一段**——第一块（商务标）落在任何文件头之前被整段
    丢弃，第二、三块被 chunk 里偶然带到的 ``### 文件: 技术标.pdf`` 一并收编，招标块因此
    挂在投标文件名下。
    """
    segments = parse_corpus(_context())

    for marker, source_file, tier in (
        ("壹佰贰拾万元整", _BUSINESS, "bid"),
        ("375000", _TECH, "bid"),
        ("评审委员会", _TENDER_DOC, "tender"),
    ):
        segment = _segment_with(segments, marker)
        assert (segment["file"], segment["tier"]) == (source_file, tier), (
            f"{marker!r} 的归属错了：实得 {(segment['file'], segment['tier'])}"
        )


def test_证据层context不产生whole兜底tier():
    """tier 退化成 ``whole`` 时 ``corpus_for`` 退回全量语料、``_files_for_tier`` 跨层找文件，
    「招标里有 / 投标里没有」这条区分当场消失——回查闸还在跑，判据已经不是原来那个。
    """
    tiers = {seg["tier"] for seg in parse_corpus(_context())}

    assert tiers == {"bid", "tender"}, f"tier 不得退化成 whole：{tiers}"


def test_同一家多份文件的页号各自归属自己的文件():
    """两份投标文件的页码都从 1 开始——file 级归属一错，页号就会在错的文件里核实。"""
    segments = parse_corpus(_context())

    business = _segment_with(segments, "壹佰贰拾万元整")
    tech = _segment_with(segments, "375000")

    assert (business["file"], business["page"]) == (_BUSINESS, 1)
    assert (tech["file"], tech["page"]) == (_TECH, 1)


def test_每个chunk带回自己的源文件名且不丢层标识():
    """索引侧的落点：``file`` 列仍是层标识（S8 限层过滤依赖它），真实文件名另存一列。"""
    chunks = ch.build_chunks(_BID_CORPUS, file_name=ev.BID_FILE, tag=ev.BID_TAG)

    assert {chunk["file"] for chunk in chunks} == {ev.BID_FILE}, "层标识不能丢"
    grouped: dict[str, str] = {}
    for chunk in chunks:
        grouped[chunk["source_file"]] = grouped.get(chunk["source_file"], "") + chunk["chunk_text"]
    assert set(grouped) == {
        f"{_BUSINESS} (kind=pdf, route=native)",
        f"{_TECH} (kind=pdf, route=native)",
    }, f"每块要带回自己那份文件的原始头串：{sorted(grouped)}"
    assert "壹佰贰拾万元整" in grouped[f"{_BUSINESS} (kind=pdf, route=native)"]
    assert "375000" in grouped[f"{_TECH} (kind=pdf, route=native)"]


def test_单块render自带文件头页锚与降级标记():
    """每块自洽 = 误归属在构造上不可能，不再取决于 ``### 文件:`` 落在哪一刀里。

    头串**原样带回**（含 ``[⚠清晰度低]`` 等标记）：回查闸的 clarity / 页号存疑降级都从这
    一行解析，只回填纯文件名等于把降级信号丢在检索这一步。
    """
    block = er.EvidenceBlock(
        chunk_id="__bid__@1#0",
        scope="bid",
        chapter_path="技术标 > 4.8.类似业绩",
        page_anchor="【第 317 页】",
        text="业绩表：某演播室建设项目 375000 元。",
        source_file=f"{_TECH} (kind=pdf, route=image) [⚠清晰度低：OCR 部分文本置信度低]",
    )

    segments = parse_corpus(block.render())

    assert len(segments) == 1, f"单块应解析成一段：{segments}"
    assert segments[0]["file"] == _TECH
    assert segments[0]["tier"] == "bid"
    assert segments[0]["page"] == 317
    assert segments[0]["clarity"] == "low", "清晰度降级标记必须原样带回"


def test_底稿没有文件头时按层名兜底而不是让归属漂移():
    """inline OCR / 单文件底稿没有 ``### 文件:`` 行——此时块仍须自带一个层名文件头。

    否则整份证据在回查闸眼里 ``cur_file is None``、一段都不产，出处全判 unresolved。
    """
    result = ec.build_evidence_context(
        tender_text="# 第三章 技术参数\n技术参数偏差表：额定功率不小于 50kW。",
        bid_text="# 商务标\n投标报价：壹佰贰拾万元整。",
        criteria={"items": [{"item": "投标报价", "max": 40}, {"item": "额定功率", "max": 10}]},
        project_id="tp-1",
    )
    assert result.context is not None

    segments = parse_corpus(result.context)

    assert {seg["tier"] for seg in segments} == {"bid", "tender"}
    assert _segment_with(segments, "壹佰贰拾万元整")["file"] == "投标文件"
    assert _segment_with(segments, "额定功率")["file"] == "招标文件"


def test_命令的取材纪律与证据层头部口径一致():
    """F3：命令写「底稿即全部材料 / 清单从 ``### 文件:`` 行读取」，而证据片段形态下注入的
    是按项检出的片段——两处口径相反时，模型会把"没检出"当成"投标人没提供"直接判 0。

    判据落在**同一句口径**是否两边都在：措辞可以改，但不能只改一边（F3 就是只改了一边）。
    """
    command = (PROJECT_ROOT / ".claude/commands/tender-evaluate.md").read_text(encoding="utf-8")

    assert "证据片段" in command, "命令必须认「服务端按项检出的证据片段」这条底稿形态"
    assert "不等于投标人未提供" in ec._EVIDENCE_HEADER
    assert "不等于投标人未提供" in command, "未检出≠未提供的口径必须与证据层头部同源"
