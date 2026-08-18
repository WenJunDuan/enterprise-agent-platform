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
    kept = bound_draft_by_content(ocr_block, limit_bytes=limit)
    kept_bytes = len(kept.encode("utf-8"))
    return TruncatedDraft(
        text=kept + TRUNCATION_NOTICE.format(kept=kept_bytes, total=original_bytes),
        kept_bytes=kept_bytes,
        original_bytes=original_bytes,
        limit_bytes=limit,
    )


def truncation_warning(truncated: TruncatedDraft, *, stops_scoring: bool) -> dict[str, object]:
    """把截断账目渲染成**结论级**可见信号（KD4：降级不许静默）。

    ``TRUNCATION_NOTICE`` 只进模型上下文、``tender_context_truncated`` 只进运维日志——
    2026-08-18 生产事故里用户拿到的结论与界面上，"底稿 784,903 字节截到 178,641（砍 77%）"
    这件事一个字都没有，反查根因花掉一整天。三个字节数必须随结论落盘。

    Args:
        truncated: 本次截断的字节账。
        stops_scoring: 本次截断是否已导致停止自动评分（整份注入路径的 F7 归宿）。
            决定文案给出的是"按证据缺失处理"还是"已转人工复核 + 解法指引"。

    Returns:
        ``{"scope", "status", "files", "message", "original_bytes", "kept_bytes",
        "limit_bytes"}``——与其余 ocr_warnings 同形，落 ``extracted_data.ocr_warnings``。
    """
    account = (
        f"原始底稿 {truncated.original_bytes:,} 字节，"
        f"实际注入 {truncated.kept_bytes:,} 字节，"
        f"本次预算上限 {truncated.limit_bytes:,} 字节"
    )
    consequence = (
        "被截掉的内容不在模型视野内，其涉及的评分项是否达标无从判断，"
        "因此本次**不出分**、直接转人工复核。"
        "解法：本项目评分标准（criteria）解析就绪后，评标改走按评分项检索证据，"
        "不再整份注入，也就不会再有整体截断。"
        if stops_scoring
        else "被截材料对应的评分项按证据缺失处理（manual_review / 不得凭空判 0）。"
    )
    return {
        "scope": "底稿注入",
        "status": "draft_truncated",
        "files": [],
        "message": f"注入底稿超出上下文预算并已被截断：{account}。{consequence}",
        "original_bytes": truncated.original_bytes,
        "kept_bytes": truncated.kept_bytes,
        "limit_bytes": truncated.limit_bytes,
    }
