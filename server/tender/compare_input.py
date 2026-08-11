"""横比输入组装与护栏（判据侧）——``compare_worker`` 只留任务生命周期。

本模块回答三个问题，全部**只认项目级权威 criteria**（``tender_project_docs.criteria``）：

1. **谁可比**（KD1）：结论 ``extracted_data.criteria_ref.version`` 是否等于项目权威版本。
   ``criteria_version`` 是权威副本的内容 hash，**compute-on-read**（读时现算，免 DB 迁移，
   存量项目重评即解锁横比）。旧判据"各家转录副本 hash 字节等价"已废除——模型换版即漂移。
2. **拿什么算价格分**（KD3）：价格项与评标方法从**权威副本单源提取一次**供全池使用，
   各家结论里的 criteria 快照仅作审计，不再参与取值（否则 ref 同版本而快照漂移时会拿漂移值算分）。
3. **哪些数据不可信**（KD4）：``bid_price`` 数值校验（缺失 / 非有限 / ≤0 均非法）、
   各家金额数量级差 ≥100 倍疑似单位不一致、比较池按投标人取最新一条结论。
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

from server.stores.result_store import list_latest_results_by_project
from server.stores.tender_compare_store import CompareSignature, compute_criteria_hash
from server.stores.tender_doc_store import get_project_doc

logger = logging.getLogger(__name__)

PRICE_ITEM_TAG = "requires_cross_bid_comparison"

# 各家报价金额最大/最小比值达此倍数 → 疑似万元与元混用。绝不自动换算（错一个数量级不可接受），
# 整池转人工（KD4）。
UNIT_MISMATCH_RATIO = 100.0


def resolve_project_criteria(project_id: str, tenant: str) -> tuple[dict[str, Any] | None, str | None]:
    """取项目级权威 criteria 及其版本（compute-on-read 内容 hash）。

    版本不落列、每次读时现算：幂等、免 DB 迁移，存量 ``tender_project_docs.criteria``
    （有内容无版本字段）自然获得版本。内容缺失 / 非 JSON / 非对象 → ``(None, None)``。

    Args:
        project_id: 招标项目 ID。
        tenant: 租户作用域。

    Returns:
        ``(criteria, version)``；无权威副本时为 ``(None, None)``。
    """
    doc = get_project_doc(project_id, tenant)
    raw = (doc or {}).get("criteria")
    if not raw:
        return None, None
    criteria = raw
    if isinstance(raw, str):
        try:
            criteria = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning(
                "tender_project_criteria_unparsable",
                extra={"project_id": project_id, "tenant": tenant or "default"},
            )
            return None, None
    if not isinstance(criteria, dict):
        return None, None
    return criteria, compute_criteria_hash(criteria)


def build_criteria_ref(
    injected_version: str | None, own_criteria: Any
) -> dict[str, str] | None:
    """结论的 criteria 引用：注入过权威版本 → ``project``；否则按本家解析副本记 ``self_parsed``。

    与 ``resolve_project_criteria`` 共用同一 hash 计算（禁止两处各算一套）。
    ``self_parsed`` 结论在横比时会被排除并提示重评，不再直接封锁全池。

    Args:
        injected_version: 评标时注入给模型的项目权威版本；未注入为 None。
        own_criteria: 模型自行解析出的 criteria 副本。

    Returns:
        ``{"version", "source"}``；无版本可记（既未注入、模型也没给 criteria）时为 None。
    """
    if injected_version:
        return {"version": injected_version, "source": "project"}
    if own_criteria:
        return {"version": compute_criteria_hash(own_criteria), "source": "self_parsed"}
    return None


def find_price_item(criteria: Any) -> tuple[dict[str, Any] | None, str | None]:
    """从权威 criteria 找可横比的价格项，三态返回（KD3）。

    遍历**全部** ``tag=requires_cross_bid_comparison`` 项，满分非法（缺失 / 非数 / 非有限 /
    负数）的项跳过继续找 —— 旧实现命中首个 cross-bid 项后 max 非法即 ``return None``，
    模型把某个横比项标成 manual/null 就锁死整池（0730 自锁）。

    Args:
        criteria: 项目权威 criteria。

    Returns:
        ``(price_item, reason)``：找到 → ``(item, None)``；有 cross-bid 项但满分全未知 →
        ``(None, "price_max_unknown")``；没有 cross-bid 项 → ``(None, "no_price_item")``。
    """
    if not isinstance(criteria, dict):
        return None, "no_price_item"
    cross_bid_seen = False
    legal: list[dict[str, Any]] = []
    for item in criteria.get("items") or []:
        if not (isinstance(item, dict) and item.get("tag") == PRICE_ITEM_TAG):
            continue
        cross_bid_seen = True
        max_score = item.get("max")
        if not _is_valid_max(max_score):
            continue
        legal.append(
            {
                "item": item.get("item"),
                "max": max_score,
                "scoring_rule": item.get("scoring_rule"),
            }
        )
    if not legal:
        return None, ("price_max_unknown" if cross_bid_seen else "no_price_item")
    if len(legal) > 1:
        logger.warning(
            "tender_multiple_cross_bid_price_items",
            extra={"items": [entry["item"] for entry in legal]},
        )
    return legal[0], None


def collect_compare_input(
    tenant: str, project_id: str, project: dict[str, Any]
) -> tuple[dict[str, Any], CompareSignature] | None:
    """组装 ``/tender-compare`` 输入 + 输入签名（stale 用）。

    池 = 该招标下每个投标人的**最新**一条结论（KD4，同家重评不双行）。可比性、价格项、
    报价合法性、单位一致性四道判据全在此定，命令侧只按已给判据算分。

    Args:
        tenant: 租户作用域。
        project_id: 招标项目 ID。
        project: 招标项目行（取 funding_type / control_price）。

    Returns:
        ``(compare_input, signature)``；池内结论 < 2 条（横比无意义）时 None。
    """
    criteria, criteria_version = resolve_project_criteria(project_id, tenant)
    rows = list_latest_results_by_project(tenant, project_id, limit=200)
    bidders = [entry for entry in (_bidder_entry(row, criteria_version) for row in rows) if entry]
    if len(bidders) < 2:
        return None
    warnings = _apply_bidder_guardrails(bidders, criteria_version)
    price_item, price_reason = find_price_item(criteria)
    blocked_reason = price_reason or _pool_blocked_reason(bidders, warnings)
    signature = CompareSignature(
        input_result_ids=[str(entry.pop("_request_id")) for entry in bidders],
        # 版本变了（项目规则改版）→ 旧横比结果 stale。
        criteria_hash=criteria_version or "",
    )
    compare_input = {
        "project_id": project_id,
        "method": (criteria or {}).get("method"),
        "criteria_version": criteria_version,
        "funding_type": project.get("funding_type") or "unknown",
        "control_price": project.get("control_price"),
        "criteria_price_item": None if blocked_reason else price_item,
        "price_comparison_blocked": blocked_reason is not None,
        "price_comparison_blocked_reason": blocked_reason,
        "warnings": warnings,
        "bidders": bidders,
    }
    return compare_input, signature


def _bidder_entry(row: dict[str, Any], criteria_version: str | None) -> dict[str, Any] | None:
    """一行结论 → 一个横比参与者（含可比性判定）；payload 不可用时返回 None。"""
    payload = row.get("payload")
    if isinstance(payload, str):
        # list_results_by_project 的 payload 列是未解析 JSON 字符串（SELECT *），需 loads。
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            return None
    response = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response, dict):
        return None
    extracted = response.get("extracted_data") or {}
    ref = extracted.get("criteria_ref")
    ref_version = ref.get("version") if isinstance(ref, dict) else None
    ref_source = ref.get("source") if isinstance(ref, dict) else None
    return {
        "claim_id": response.get("claim_id") or row.get("claim_id"),
        "bid_price": extracted.get("bid_price"),
        "scoring": extracted.get("scoring", []),
        "verdict": response.get("verdict"),
        # 存量结论无 ref → ref_source 为 None → 按 self_parsed 处理（不走旧 hash 判据）。
        "comparable": bool(
            criteria_version and ref_source == "project" and ref_version == criteria_version
        ),
        "exclusion_reason": None,
        "_request_id": row["request_id"],
    }


def _apply_bidder_guardrails(
    bidders: list[dict[str, Any]], criteria_version: str | None
) -> list[str]:
    """逐家标注排除原因（criteria 版本过期 / 报价非法）并生成**指名**告警。"""
    warnings: list[str] = []
    for entry in bidders:
        name = entry["claim_id"]
        if not entry["comparable"]:
            entry["exclusion_reason"] = "criteria_stale"
            warnings.append(
                f"投标人「{name}」的评标依据不是当前项目规则版本"
                f"（{criteria_version or '项目规则尚未定稿'}），已排除出横比，建议重评该家后再横比。"
            )
            continue
        if _bid_price_amount(entry.get("bid_price")) is None:
            entry["comparable"] = False
            entry["exclusion_reason"] = "bid_price_invalid"
            warnings.append(
                f"投标人「{name}」的投标报价缺失或数值非法（须为大于 0 的有限数），"
                "已排除出价格横比，需人工补录后重算。"
            )
    return warnings


def _pool_blocked_reason(bidders: list[dict[str, Any]], warnings: list[str]) -> str | None:
    """整池级封锁判定：可比家数不足 / 报价数量级疑似单位不一致。"""
    comparable = [entry for entry in bidders if entry["comparable"]]
    if len(comparable) < 2:
        return "insufficient_comparable_bidders"
    amounts = [
        amount
        for amount in (_bid_price_amount(entry.get("bid_price")) for entry in comparable)
        if amount is not None
    ]
    if amounts and max(amounts) / min(amounts) >= UNIT_MISMATCH_RATIO:
        warnings.append(
            "各投标人报价数量级相差 100 倍以上，疑似万元与元单位不一致；"
            "平台不做自动换算，已停止排名，请人工核对报价口径。"
        )
        return "bid_price_unit_mismatch"
    return None


def _is_valid_max(value: Any) -> bool:
    """满分是否为合法非负有限数（bool 不算数：True 会被 int 判定误收）。"""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _bid_price_amount(bid_price: Any) -> float | None:
    """取本家报价金额；缺失 / 非数 / 非有限 / **≤0** 一律非法（0 与负数同判，兼防比值除零）。"""
    if not isinstance(bid_price, dict):
        return None
    amount = bid_price.get("amount")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool):
        return None
    if not math.isfinite(amount) or amount <= 0:
        return None
    return float(amount)


__all__ = [
    "PRICE_ITEM_TAG",
    "UNIT_MISMATCH_RATIO",
    "build_criteria_ref",
    "collect_compare_input",
    "find_price_item",
    "resolve_project_criteria",
]
