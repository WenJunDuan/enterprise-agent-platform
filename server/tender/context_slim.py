"""D8 底稿瘦身：按项目 criteria 检索招标文件相关章节，替代全量灌注。

criteria.eligibility_rules[] 对应招标文件的"资格审查"章节（docstructure 语义标签
qualification_review），criteria.items[] 对应"评标办法/评分标准"章节（语义标签
evaluation_method）——两者都是 D6 docstructure._TAG_KEYWORDS 现成的固定标签，criteria
本身在抽取时就是从这两类章节里解析出来的（见 .claude/commands/tender-evaluate.md S1），
用它做检索 query 天然贴合真实定位需求。
"""

from __future__ import annotations

import sqlite3
from typing import Any

from server.common.corpus import (
    PAGE_ANCHOR_LINE_RE,
    split_head_tail_on_anchors,
    text_has_page_anchor,
)
from server.ocr.docstructure import build_doc_structure
from server.ocr.rag import index_document, search
from server.tender.context_budget import first_heading_index, select_review_spans
from server.tender.eval_signals import mark_context_truncated
from server.tender.injection_budget import chunks_per_query_budget, fallback_injection_tokens

_ELIGIBILITY_TAG = "qualification_review"
_EVALUATION_TAG = "evaluation_method"

# 首次 criteria 抽取尚无 criteria 可供检索，因此按 docstructure 的标题识别结果保留招标前置信息和
# 评标相关章节。关键词表与"命中标题→整章"的选区逻辑与注入预算闸共用单点
# （``server.tender.context_budget``，2026-08-14 Bug A 消重）：两处漏同一个关键词
# （事故里的「评审方法和程序」）就会同时丢掉评分标准。
# 页锚点解析统一走 server.common.corpus 单点（含【转换稿第M页】变体，H2 KD0）
_PAGE_ANCHOR_RE = PAGE_ANCHOR_LINE_RE


def _preextract_char_budget(model: str | None = None) -> int | None:
    """本模块可注入的字符预算（KD3 收编后转发单点）。

    旧实现自持 ``_DEFAULT_CHARS_PER_TOKEN=1.0`` 与 ``_DEFAULT_CONTEXT_MARGIN_TOKENS=4096``
    两个常量，并按 ``MODEL_CONTEXT_WINDOW`` 推导——与 ``context_budget`` 的 3 字节/token 假设
    直接冲突（一个模块按 1 算、另一个按 3 算），正是 64,000B 单位错的同型缺陷。现全部口径
    收敛到 ``server.tender.injection_budget``，且与模型窗口解耦。

    Args:
        model: 保留参数以维持既有调用形态；预算不再随模型窗口变化。

    Returns:
        字符上限。恒非 None——旧实现在部署未声明窗口时返回 None（等于闸整体失效），
        而事故当天正是这个状态。取**回落额度**而非有效上限（F2）：整窗额度不扣脚手架，
        加上 90K 脚手架必然爆窗。
    """
    del model  # 预算口径已与模型窗口解耦（AC6）
    return fallback_injection_tokens()


def _trim_context_block(block: str, limit: int) -> str:
    """Trim one selected block while retaining both its heading-side and tail evidence.

    KD3：切点吸附到页锚行边界、尾段前重放所属页锚——旧的按字符硬切会把尾段内容挂到 head 末锚
    （早得多的页），并可能把锚行切半，是"证据页码对不上"的主链路成因（评标主链路无条件套用）。
    无页锚的块（native word 等）按字符切，marker 里如实注明。
    """
    if len(block) <= limit:
        return block
    if limit <= 0:
        return ""
    has_anchor = text_has_page_anchor(block)
    marker = (
        "\n...[章节中间内容省略，章节首尾保留]...\n"
        if has_anchor
        else "\n...[章节中间内容省略，章节首尾保留；本文件无页锚，按字符切]...\n"
    )
    if limit <= len(marker):
        return block[:limit]
    body_limit = limit - len(marker)
    head_n = (body_limit * 2) // 3
    head, tail, replay = split_head_tail_on_anchors(block, head_n, body_limit - head_n)
    return head + marker + (f"{replay}\n" if replay else "") + tail


def build_preextract_tender_context(
    tender_text: str, *, file_name: str | None = None, model: str | None = None
) -> str | None:
    """Build a bounded first-pass context before ``criteria`` exists.

    ``None`` deliberately means "use the original OCR text": missing context-window config,
    small text, or unrecognized structure therefore keep the pre-existing extraction behavior.
    For a large structured document, keep the preface plus every title-matched review section;
    section-aware fitting avoids dropping the entire scoring chapter through a blind tail cut.
    """
    budget = _preextract_char_budget(model)
    if budget is None or len(tender_text) <= budget:
        return None

    lines = (tender_text or "").splitlines()
    selected = select_review_spans(lines)
    if not selected:
        return _trim_context_block(tender_text, budget)
    # 章首若紧跟在页锚行之后，把页锚一并带上——否则该章的证据全部挂到更早的页。
    merged = [
        (start - 1 if start > 0 and _PAGE_ANCHOR_RE.match(lines[start - 1]) else start, end)
        for start, end in selected
    ]

    heading_index = first_heading_index(lines)
    preface_end = heading_index if heading_index is not None else min(merged[0][0], 120)
    prefix = "\n".join(lines[:preface_end])
    sections = ["\n".join(lines[start:end]) for start, end in merged]
    parts = [prefix, *sections]
    full = "\n\n".join(part for part in parts if part)
    if len(full) <= budget:
        return full

    # If selected chapters themselves exceed the budget, allocate space to every part. This
    # preserves the preface and each relevant chapter instead of cutting at one global offset.
    part_count = len(parts)
    separator_budget = max(0, budget - max(0, part_count - 1) * 2)
    prefix_limit = min(len(prefix), separator_budget // max(5, part_count))
    remaining = separator_budget - prefix_limit
    fitted = [_trim_context_block(prefix, prefix_limit)] if prefix else []
    for index, section in enumerate(sections):
        sections_left = len(sections) - index
        limit = remaining // sections_left if sections_left else 0
        fitted.append(_trim_context_block(section, limit))
        remaining -= min(len(section), limit)
    return "\n\n".join(part for part in fitted if part)


def bound_tender_context(context: str, *, model: str | None = None) -> str | None:
    """Bound the complete tender prompt context using the selected model's deployment budget.

    The budget is intentionally configuration-only. When the deployment does not declare both
    the selected model's context window and output budget, this helper returns ``None`` so the
    caller keeps the existing full-context behavior instead of silently choosing a model limit.
    """
    budget = _preextract_char_budget(model)
    if budget is None or len(context) <= budget:
        return context

    # 下面每一条路径都会削掉材料（招标段 / 投标段 / 整体硬切）。与 ``draft_budget.bound_draft``
    # 同一理由记账：回填质量门要知道这次会话是不是只看了残卷（见 ``eval_signals``）。
    mark_context_truncated()
    tender_marker = "=== 招标文件底稿 ===\n"
    bid_marker_start = "\n=== 投标文件（"
    criteria_marker = "\n\n=== 已解析评分标准 criteria"
    tender_start = context.find(tender_marker)
    bid_start = context.find(bid_marker_start, tender_start + len(tender_marker))
    if tender_start < 0 or bid_start < 0:
        return _trim_context_block(context, budget)

    criteria_start = context.find(criteria_marker, bid_start)
    if criteria_start < 0:
        criteria_start = len(context)
    prefix = context[:tender_start]
    tender_block = context[tender_start:bid_start]
    bid_block = context[bid_start:criteria_start]
    criteria_block = context[criteria_start:]

    # Keep the deterministic scoring material and criteria intact whenever possible; only the
    # current bidder's evidence is reduced to fit the remaining configured budget.
    body_budget = budget - len(prefix) - len(criteria_block)
    if body_budget <= 0:
        return _trim_context_block(context, budget)
    if len(tender_block) <= body_budget:
        tender_budget = len(tender_block)
    else:
        tender_budget = (body_budget * 3) // 5
    bid_budget = max(0, body_budget - tender_budget)
    bounded_tender = _trim_context_block(tender_block, tender_budget)
    bounded_bid = _trim_context_block(bid_block, bid_budget)
    bounded = prefix + bounded_tender + bounded_bid + criteria_block
    if len(bounded) <= budget:
        return bounded
    return _trim_context_block(bounded, budget)


def _criteria_queries(criteria: dict[str, Any]) -> list[tuple[str, str, str]]:
    """把 criteria 的 eligibility_rules/items 转成 (query_text, tag, label) 三元组列表。"""
    queries: list[tuple[str, str, str]] = []
    for rule in criteria.get("eligibility_rules") or []:
        text = " ".join(filter(None, [rule.get("check"), rule.get("requirement")])).strip()
        if text:
            queries.append((text, _ELIGIBILITY_TAG, f"资格审查:{rule.get('check', '')}"))
    for item in criteria.get("items") or []:
        text = " ".join(filter(None, [item.get("item"), item.get("category")])).strip()
        if text:
            queries.append((text, _EVALUATION_TAG, f"评分项:{item.get('item', '')}"))
    return queries


def build_slim_tender_context(
    tender_text: str, criteria: dict[str, Any], *, file_name: str
) -> str | None:
    """按 criteria 检索招标文件相关章节，组装精简 context；无法安全精简时返回 None。

    None 的三种触发条件（调用方一律回退全量原文，绝不静默丢项）：
    1. criteria 不含任何可用于检索的 eligibility_rules/items 文本；
    2. tender_text 没有可识别的章节（build_doc_structure 产物 chapters 为空）；
    3. 任一检索项零命中——宁可整份回退全量，不做"部分精简、部分静默缺失"。
    """
    queries = _criteria_queries(criteria)
    if not queries:
        return None

    structure = build_doc_structure(tender_text, file_name=file_name)
    if not structure["chapters"]:
        return None

    # KD3：每项取几个 chunk 不再是写死的 3，而是由闭式账目派生——项数越多每项额度越小，
    # 总注入量恒受标定上限约束（旧常量的问题是项数一多，去重后仍逼近全量）。
    chunks_per_query = chunks_per_query_budget(criteria=criteria, query_count=len(queries))

    conn = sqlite3.connect(":memory:")
    index_document(structure, tender_text, conn=conn)

    collected: dict[str, dict[str, Any]] = {}
    for query_text, tag, _label in queries:
        hits = search(query_text, conn=conn, tag=tag, limit=chunks_per_query)
        if not hits:
            conn.close()
            return None
        for hit in hits:
            collected.setdefault(hit["chunk_id"], hit)

    conn.close()
    blocks = [f"{hit['page_anchor']}\n{hit['text']}" for hit in collected.values()]
    return "\n\n".join(blocks)
