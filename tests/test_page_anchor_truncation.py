"""H2 页锚溯源 · 截断按锚切（KD3，AC2）。

旧行为按字符硬切：tail 段截断点到下一锚点之间的内容，在模型视角归属 head 末锚（早得多的页），
且锚点行可能被切半。大标书必触发，是"证据页码对不上"最吻合的主链路机制。
"""

from __future__ import annotations

import re

import pytest

from server.common.corpus import split_head_tail_on_anchors, text_has_page_anchor

# 被切半的锚点残片：行尾出现「【第」「【转换稿第」开头但没闭合的片段
_SPLIT_ANCHOR_RE = re.compile(r"【(?:转换稿)?第[^】]*$", re.MULTILINE)


def _paged_text(pages: int, line_per_page: int = 6) -> str:
    parts = []
    for page in range(1, pages + 1):
        body = "\n".join(f"第{page}页第{i}行内容填充填充填充" for i in range(line_per_page))
        parts.append(f"【第 {page} 页】\n{body}")
    return "\n".join(parts)


def test_no_split_anchor_fragments_anywhere_in_output():
    """AC2：任何输出中不存在被切半的锚（正则扫描残片数 = 0）。"""
    text = _paged_text(40)
    for head_n in range(200, 600, 37):
        head, tail, replay = split_head_tail_on_anchors(text, head_n, 300)
        composed = head + "\n" + (f"{replay}\n" if replay else "") + tail
        assert not _SPLIT_ANCHOR_RE.search(composed), (head_n, composed[-80:])


def test_head_cut_snaps_back_to_anchor_line_start():
    text = _paged_text(20)
    head, _tail, _replay = split_head_tail_on_anchors(text, 500, 300)
    assert head.endswith("\n") or head == ""
    # head 结束处正好是下一页锚行之前 → head 里的最后一行是正文，不是半个锚
    assert not head.rstrip("\n").endswith("【")


def test_tail_replays_owning_page_anchor_when_cut_lands_mid_page():
    """切点落在页中 → tail 首行必须是重放锚，消除"tail 内容挂到 head 末锚"的错挂。"""
    page_body = "\n".join(f"正文行{i}" * 6 for i in range(10))
    text = f"【第 1 页】\n{page_body}\n【第 2 页】\n{page_body}"
    tail_n = len(page_body) // 2
    head, tail, replay = split_head_tail_on_anchors(text, 40, tail_n)
    assert replay == "【第 2 页】"
    assert "【第 1 页】" not in tail


def test_tail_starting_at_anchor_needs_no_replay():
    """切点正好落在锚行 → tail 自带锚，不重复插入。"""
    text = _paged_text(6, line_per_page=2)
    anchor_pos = text.index("【第 5 页】")
    tail_n = len(text) - anchor_pos
    _head, tail, replay = split_head_tail_on_anchors(text, 30, tail_n)
    assert tail.startswith("【第 5 页】")
    assert replay is None


def test_converted_anchor_is_replayed_in_its_own_coordinate_system():
    body = "\n".join(f"转换稿正文{i}" * 8 for i in range(10))
    text = f"【转换稿第 3 页】\n{body}\n【转换稿第 4 页】\n{body}"
    _head, tail, replay = split_head_tail_on_anchors(text, 40, len(body) // 2)
    assert replay == "【转换稿第 4 页】"
    assert "【第 4 页】" not in tail


def test_text_without_anchors_falls_back_to_char_cut():
    text = "无任何页锚的纯文本内容。" * 200
    head, tail, replay = split_head_tail_on_anchors(text, 300, 200)
    assert replay is None
    assert text_has_page_anchor(text) is False
    assert head and tail
    assert len(head) <= 300 and len(tail) <= 200


def test_total_output_never_exceeds_requested_budget():
    text = _paged_text(30)
    for head_n, tail_n in ((400, 120), (1000, 45), (77, 300), (0, 200), (300, 0)):
        head, tail, replay = split_head_tail_on_anchors(text, head_n, tail_n)
        total = len(head) + len(tail) + (len(replay) + 1 if replay else 0)
        assert total <= head_n + tail_n, (head_n, tail_n, total)


# ── 两个消费方：pipeline._truncate_body 与 context_slim._trim_context_block ──────


def test_pipeline_head_tail_truncation_replays_anchor(monkeypatch):
    from server.ocr import pipeline

    monkeypatch.setenv("OCR_TRUNCATE_HEAD_TAIL", "1")
    monkeypatch.setattr(pipeline, "MAX_FILE_BLOCK_CHARS", 600)
    text = _paged_text(30)
    out = pipeline._truncate_body(text)
    assert not _SPLIT_ANCHOR_RE.search(out)
    tail_part = out.split("]\n\n", 1)[1]
    assert re.match(r"^【(?:转换稿)?第 \d+ 页】", tail_part), tail_part[:40]


def test_pipeline_truncation_marker_notes_missing_anchors(monkeypatch):
    from server.ocr import pipeline

    monkeypatch.setenv("OCR_TRUNCATE_HEAD_TAIL", "1")
    monkeypatch.setattr(pipeline, "MAX_FILE_BLOCK_CHARS", 300)
    out = pipeline._truncate_body("无锚正文" * 500)
    assert "本文件无页锚" in out


def test_pipeline_default_head_truncation_unchanged(monkeypatch):
    """默认（不开首尾截）行为逐字节不变——KD3 只改首尾截路径。"""
    from server.ocr import pipeline

    monkeypatch.delenv("OCR_TRUNCATE_HEAD_TAIL", raising=False)
    monkeypatch.setattr(pipeline, "MAX_FILE_BLOCK_CHARS", 100)
    text = "甲" * 500
    out = pipeline._truncate_body(text)
    assert out.startswith("甲" * 100)
    assert "仅保留前 100" in out


@pytest.mark.parametrize("limit", [400, 700, 1200])
def test_context_slim_trim_keeps_anchor_lines_intact(limit):
    from server.tender.context_slim import _trim_context_block

    text = _paged_text(30)
    trimmed = _trim_context_block(text, limit)
    assert len(trimmed) <= limit
    assert not _SPLIT_ANCHOR_RE.search(trimmed)


def test_context_slim_trim_replays_anchor_for_tail_segment():
    from server.tender.context_slim import _trim_context_block

    text = _paged_text(30)
    trimmed = _trim_context_block(text, 900)
    tail_part = trimmed.split("]...\n", 1)[1]
    assert re.match(r"^【第 \d+ 页】", tail_part), tail_part[:40]


def test_context_slim_trim_notes_missing_anchors():
    from server.tender.context_slim import _trim_context_block

    trimmed = _trim_context_block("无锚正文内容" * 300, 400)
    assert "无页锚" in trimmed
    assert len(trimmed) <= 400
