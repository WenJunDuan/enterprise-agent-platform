"""横比结论的服务端兜底（模型返回**之后**的 fail-closed 改写）+ 失败详情脱敏。

与 ``server.tender.compare_input``（模型调用**之前**的判据与输入组装）分家：那边定"谁可比、
价格项是什么、哪家报价不可信"，这边负责"模型无视判据给了排名时怎么改回来"，以及把内部异常
文本收成能给前端看的一行说明。两侧共用 ``compare_input`` 里的排除原因取值，不各立一套。
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# 整池封锁时的逐家说明：按 **blocked_reason** 取（F9：旧实现无论何种原因都写"价格项满分未设"，
# 与实际原因不符，误导人工）。
_BLOCK_NOTES = {
    "insufficient_comparable_bidders": "可比投标人不足 2 家（评标依据版本不一致或报价无效），需人工处理后再横比。",
    "price_max_unknown": "招标评分标准中的价格项满分未设定，需人工确认后再横比。",
    "no_price_item": "招标评分标准中未找到需横向比较的价格项，需人工确认评标办法。",
    "bid_price_unit_mismatch": "各家报价数量级不一致（疑似万元/元混用），需人工核对口径后再横比。",
}
_EXCLUSION_NOTES = {
    "criteria_stale": "该家评标依据的评分标准版本不是当前项目规则，已不参与横比，建议重评后再比。",
    "bid_price_invalid": "该家投标报价缺失或数值非法，已不参与价格横比，需人工补录。",
}

# 未命中白名单时给用户看的固定文案（详情只进服务端日志）。
GENERIC_ERROR_DETAIL = "横比计算失败，请重试或联系管理员"

# 白名单：服务端自己抛出、本就写给用户看的业务原因，命中才原文透出。
# 新增服务端业务异常时，把它的用户可读消息一并登记到这里，否则前端只会看到固定文案。
COMPARE_TIMEOUT_REASON = "横比计算超时，请稍后重新横比"

KNOWN_BUSINESS_REASONS = (
    "参与横比的已完成投标人不足 2 家",
    COMPARE_TIMEOUT_REASON,
)

# 凭证兜底（防御纵深）：Bearer / sk-xxx / api_key= / token= 等形态一律抹掉。
_CREDENTIAL_PATTERN = re.compile(
    r"(?i)(?:bearer\s+\S+|sk-[\w\-]{6,}|(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S+)"
)

_DETAIL_MAX_CHARS = 200


def enforce_compare_guardrails(
    payload: dict[str, Any], compare_input: dict[str, Any]
) -> None:
    """按服务端判据改写模型结论（fail closed），并把服务端告警并入结论。

    整池封锁 → 全体 manual_review、不给排名与推荐，逐家 note 与 blocked_reason 一致；
    未封锁但个别家被排除 → 只降那几家，其余家的排名保留（不再一家有问题就封锁全池）。

    Args:
        payload: 模型返回的 compare 结论（原地改写）。
        compare_input: 服务端组装的输入（判据与逐家排除原因的唯一来源）。
    """
    if compare_input.get("price_comparison_blocked"):
        _block_whole_pool(payload, compare_input)
    else:
        _demote_excluded_bidders(payload, compare_input)
    server_warnings = [warning for warning in compare_input.get("warnings", []) if warning]
    existing = payload.get("warnings")
    payload["warnings"] = (
        [*existing, *server_warnings] if isinstance(existing, list) else list(server_warnings)
    )


def sanitize_error_detail(detail: Any, limit: int = _DETAIL_MAX_CHARS) -> str:
    """把内部异常文本收成可回前端的一行说明（**白名单**：只有已知业务原因原文出网）。

    compare 失败原因必须对用户可见（否则回到"静默失败"），但异常文本是不可控输入：
    traceback、SQL 片段、服务器路径、乃至上游调用带出的凭证都可能混在里面。透传 + 正则
    清洗是黑名单思路（漏一个模式就泄一次），故改白名单：只有服务端自己抛的、本就写给用户看的
    业务原因才原样返回，其余一律固定文案，完整详情落服务端日志供排障。

    Args:
        detail: 原始 error_detail（可能是多行 traceback）。
        limit: 已知业务原因的截断长度上限。

    Returns:
        面向用户的一行说明；无内容时空串。
    """
    if not detail:
        return ""
    raw = str(detail)
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return ""
    message = lines[-1] if lines[0].startswith("Traceback") else lines[0]
    known = _match_known_reason(message)
    if known is None:
        # 详情只留服务端：写进消息体（而非 extra 字段）才能被常规日志采集与本地排障看到。
        logger.warning("tender_compare_error_detail_masked: %s", raw)
        return GENERIC_ERROR_DETAIL
    # 已知业务原因也过一遍凭证兜底：上游可能把 token 拼进消息（防御纵深，不是重复校验）。
    known = _CREDENTIAL_PATTERN.sub("[已隐去]", known)
    return known if len(known) <= limit else known[:limit] + "…"


def _match_known_reason(message: str) -> str | None:
    """命中白名单则返回该业务原因原文（去掉异常类名前缀），否则 None。"""
    for reason in KNOWN_BUSINESS_REASONS:
        if reason in message:
            index = message.index(reason)
            return message[index:].strip()
    return None


def _block_whole_pool(payload: dict[str, Any], compare_input: dict[str, Any]) -> None:
    """整池转人工：清空价格分/总分/排名/推荐，逐家 note 按封锁原因或该家排除原因给。"""
    reason = compare_input.get("price_comparison_blocked_reason")
    note = _BLOCK_NOTES.get(reason, _BLOCK_NOTES["insufficient_comparable_bidders"])
    model_by_claim = _model_bidders_by_claim(payload)
    payload["bidders"] = [
        {
            "claim_id": entry.get("claim_id"),
            "bid_price": entry.get("bid_price"),
            "price_score": None,
            "other_score": (model_by_claim.get(entry.get("claim_id")) or {}).get("other_score"),
            "total_score": None,
            "rank": None,
            "status": "manual_review",
            "note": _EXCLUSION_NOTES.get(entry.get("exclusion_reason") or "", note),
        }
        for entry in compare_input.get("bidders", [])
        if isinstance(entry, dict)
    ]
    payload["recommended"] = None
    payload["provisional"] = True
    payload["explanation"] = note
    warnings = compare_input.setdefault("warnings", [])
    if note not in warnings:
        warnings.append(note)


def _demote_excluded_bidders(payload: dict[str, Any], compare_input: dict[str, Any]) -> None:
    """池可比但个别家被排除：只把那几家改人工，不动其余家的排名。"""
    excluded = {
        entry.get("claim_id"): entry.get("exclusion_reason")
        for entry in compare_input.get("bidders", [])
        if isinstance(entry, dict) and not entry.get("comparable")
    }
    if not excluded:
        return
    for bidder in payload.get("bidders") or []:
        if not isinstance(bidder, dict) or bidder.get("claim_id") not in excluded:
            continue
        bidder.update(
            price_score=None,
            total_score=None,
            rank=None,
            status="manual_review",
            note=_EXCLUSION_NOTES.get(excluded[bidder["claim_id"]] or "", ""),
        )


def _model_bidders_by_claim(payload: dict[str, Any]) -> dict[Any, dict[str, Any]]:
    model_bidders = payload.get("bidders")
    if not isinstance(model_bidders, list):
        return {}
    return {
        bidder.get("claim_id"): bidder for bidder in model_bidders if isinstance(bidder, dict)
    }


__all__ = [
    "COMPARE_TIMEOUT_REASON",
    "GENERIC_ERROR_DETAIL",
    "KNOWN_BUSINESS_REASONS",
    "enforce_compare_guardrails",
    "sanitize_error_detail",
]
