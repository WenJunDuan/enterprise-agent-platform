"""底稿注入的**无条件**字节上限与截断标记（纯计算部分）。

2026-08-14 生产事故：inline_ocr 回落把整个 case 目录的 OCR 全文无上限注入 → "Prompt is
too long"，整单无结论。默认额度由 ``injection_budget`` 单点标定（KD3）；显式设
``TENDER_CONTEXT_MAX_BYTES`` 仍以其为准。

**为什么从 runner 搬出来**：runner 因本轮延时治理（服务端注规则 / 锁工具面 / resume 修补轮）
涨到 347 行，超 300 行上限。搬走的是纯计算；``tender_context_truncated`` 这条按 logger 名
``server.tender.runner`` 可检索的运维日志**留在 runner**，挪家会改记录里的 logger 名。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from server.tender.context_budget import bound_draft_by_content, derive_default_max_bytes
from server.tender.eval_signals import mark_context_truncated

# 让模型**看见**底稿被截，从而对被截材料走证据缺失规则，而不是当成"材料未提供"判 0。
# 标记本身（~160 B）附加在上限之外，故意保证"被截了"这件事一定进上下文。
TRUNCATION_NOTICE = (
    "\n【底稿超出上下文预算，已截断：按内容优先保留（评标办法/评分标准/资格审查等关键章节优先），"
    "共保留 {kept} 字节 / 原始 {total} 字节；被省略区段在正文中以 ...[已省略…]... 标出，"
    "涉及被截材料的评分项按证据缺失处理】\n"
)


@dataclass(frozen=True, slots=True)
class TruncatedDraft:
    """被截断的底稿及其字节账（供调用方记运维日志）。"""

    text: str
    kept_bytes: int
    original_bytes: int
    limit_bytes: int


def context_max_bytes(model: str | None = None) -> int:
    """Return the OCR draft byte budget (reads ``TENDER_CONTEXT_MAX_BYTES`` live)."""
    configured = os.getenv("TENDER_CONTEXT_MAX_BYTES")
    if configured:
        return int(configured)
    return derive_default_max_bytes(model)


def bound_draft(ocr_block: str, *, model: str | None = None) -> TruncatedDraft | None:
    """Fit the OCR draft into the byte budget, keeping review-critical sections first.

    Args:
        ocr_block: 待注入的 OCR/直读底稿全文（doc 层复用或 inline OCR 均经此）。
        model: 本次评标实际使用的模型名，用于按其窗口推导默认预算。

    Returns:
        未超限时返回 ``None``（调用方原样用底稿）；超限时返回含截断标记的
        :class:`TruncatedDraft`。
    """
    limit = context_max_bytes(model)
    original_bytes = len(ocr_block.encode("utf-8"))
    if original_bytes <= limit:
        return None
    # 削之前先记账：截断这件事只有这里知道，而回填质量门要据它判"这次会话看全了没有"
    # （见 ``eval_signals``）。调用方那条 ``tender_context_truncated`` 日志是给运维的，
    # 进不了判断；两者同源同时机，不是重复。
    mark_context_truncated()
    kept = bound_draft_by_content(ocr_block, limit_bytes=limit)
    kept_bytes = len(kept.encode("utf-8"))
    return TruncatedDraft(
        text=kept + TRUNCATION_NOTICE.format(kept=kept_bytes, total=original_bytes),
        kept_bytes=kept_bytes,
        original_bytes=original_bytes,
        limit_bytes=limit,
    )
