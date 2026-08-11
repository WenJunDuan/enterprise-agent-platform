"""D8 底稿瘦身：按项目 criteria 检索招标文件相关章节，替代全量灌注。

criteria.eligibility_rules[] 对应招标文件的"资格审查"章节（docstructure 语义标签
qualification_review），criteria.items[] 对应"评标办法/评分标准"章节（语义标签
evaluation_method）——两者都是 D6 docstructure._TAG_KEYWORDS 现成的固定标签，criteria
本身在抽取时就是从这两类章节里解析出来的（见 .claude/commands/tender-evaluate.md S1），
用它做检索 query 天然贴合真实定位需求。
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from server.common.corpus import PAGE_ANCHOR_LINE_RE
from server.ocr.docstructure import build_doc_structure, chapter_heading
from server.ocr.rag import index_document, search
from server.platform.config import resolve_model_context_window, resolve_model_max_output_tokens

_ELIGIBILITY_TAG = "qualification_review"
_EVALUATION_TAG = "evaluation_method"
# 每条 criteria 项检索几个 chunk：给到"整章+相邻子节"的量级，过大会让去重后仍逼近全量。
_CHUNKS_PER_QUERY = 3

# 首次 criteria 抽取尚无 criteria 可供检索，因此按 docstructure 的标题识别结果保留
# 招标前置信息和评标相关章节。额外的"废标/否决"关键词不能只依赖现有语义 tag：它们
# 常出现在资格/符合性章节的标题或条款标题中，但属于首次抽取的关键证据。
_PREEXTRACT_KEYWORDS = (
    "评标办法",
    "评分标准",
    "评分细则",
    "评审办法",
    "资格审查",
    "资格评审",
    "资格要求",
    "初步评审",
    "符合性审查",
    "响应性审查",
    "废标",
    "否决",
)
# 页锚点解析统一走 server.common.corpus 单点（含【转换稿第M页】变体，H2 KD0）
_PAGE_ANCHOR_RE = PAGE_ANCHOR_LINE_RE
# OCR 文本以中文为主，按 1 字符≈1 token 估算，宁可少送也不让网关再次超窗。
_DEFAULT_CHARS_PER_TOKEN = 1.0
_DEFAULT_CONTEXT_MARGIN_TOKENS = 4096


def _positive_float_env(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError:
        return default
    return value if value > 0 else default


def _non_negative_int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        return default
    return value if value >= 0 else default


def _preextract_char_budget(model: str | None = None) -> int | None:
    """Return a conservative OCR character budget, or None when the guard is disabled."""
    window = resolve_model_context_window(model=model)
    if window <= 0:
        return None
    reserved_output = resolve_model_max_output_tokens(model=model)
    if reserved_output is None:
        return None
    # 留出命令/系统提示和估算误差空间；窗口越大，至少保留 2% 的 token 余量。
    configured_margin = _non_negative_int_env(
        "TENDER_CONTEXT_MARGIN_TOKENS", _DEFAULT_CONTEXT_MARGIN_TOKENS
    )
    margin = max(configured_margin, window // 50)
    available_tokens = window - reserved_output - margin
    chars_per_token = _positive_float_env(
        "TENDER_CONTEXT_CHARS_PER_TOKEN", _DEFAULT_CHARS_PER_TOKEN
    )
    return max(0, int(available_tokens * chars_per_token))


def _trim_context_block(block: str, limit: int) -> str:
    """Trim one selected block while retaining both its heading-side and tail evidence."""
    if len(block) <= limit:
        return block
    if limit <= 0:
        return ""
    marker = "\n...[章节中间内容省略，章节首尾保留]...\n"
    if limit <= len(marker):
        return block[:limit]
    body_limit = limit - len(marker)
    head = (body_limit * 2) // 3
    return block[:head] + marker + block[-(body_limit - head) :]


def _keyword_windows(lines: list[str]) -> list[tuple[int, int]]:
    """Return small line windows around review-related OCR hits."""
    hits = [
        index
        for index, line in enumerate(lines)
        if any(keyword in line for keyword in _PREEXTRACT_KEYWORDS)
    ]
    windows: list[list[int]] = []
    for index in hits:
        start, end = max(0, index - 40), min(len(lines), index + 81)
        if windows and start <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], end)
        else:
            windows.append([start, end])
    return [(start, end) for start, end in windows]


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
    headings: list[tuple[int, str, int]] = []
    for index, raw in enumerate(lines):
        if raw.strip().startswith("### 文件:"):
            continue
        heading = chapter_heading(raw)
        if heading is not None:
            title, level = heading
            headings.append((index, title, level))

    selected: list[tuple[int, int]] = []
    for heading_index, title, level in headings:
        if any(keyword in title for keyword in _PREEXTRACT_KEYWORDS):
            end = len(lines)
            for next_index, _next_title, next_level in headings:
                if next_index > heading_index and next_level <= level:
                    end = next_index
                    break
            start = heading_index
            if start > 0 and _PAGE_ANCHOR_RE.match(lines[start - 1]):
                start -= 1
            selected.append((start, end))

    # OCR often loses heading markers while retaining the actual review terms. Keep local
    # windows around those hits so a huge unstructured document still gets bounded instead
    # of falling through to the original over-sized prompt.
    if not selected:
        selected = _keyword_windows(lines)
    if not selected:
        return _trim_context_block(tender_text, budget)

    merged: list[list[int]] = []
    for start, end in sorted(selected):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    preface_end = headings[0][0] if headings else min(selected[0][0], 120)
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

    conn = sqlite3.connect(":memory:")
    index_document(structure, tender_text, conn=conn)

    collected: dict[str, dict[str, Any]] = {}
    for query_text, tag, _label in queries:
        hits = search(query_text, conn=conn, tag=tag, limit=_CHUNKS_PER_QUERY)
        if not hits:
            conn.close()
            return None
        for hit in hits:
            collected.setdefault(hit["chunk_id"], hit)

    conn.close()
    blocks = [f"{hit['page_anchor']}\n{hit['text']}" for hit in collected.values()]
    return "\n\n".join(blocks)
