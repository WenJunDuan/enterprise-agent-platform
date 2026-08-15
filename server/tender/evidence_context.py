"""证据层接入主链路：组装注入块 + 降级可见 + 不可用时强制人工复核（KD1/KD2/KD4）。

**降级归宿为什么是"不出分"而不是"回落旧路径"**（critic F7）：旧路径对 400 页投标产出的是
**带 warning 的错误评分**——2026-08-15 那单模型自述 "The rest was cut… this makes the bid
evaluation largely impossible"，却仍然逐项给了分。错评分比失败危险得多：失败会被人看见并
重跑，错评分会被当成结论用。所以证据层不可用时本模块强制 ``manual_review`` 且清空 scoring。
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from server.common.agent_bridge import AgentRunMeta
from server.platform.sqlite_store import utc_now
from server.stores.result_store import archive_result_payload
from server.stores.session_store import new_conversation_id
from server.tender.evidence_index import build_evidence_index, retrieve_evidence
from server.tender.injection_budget import CALIBRATION_DOC_PATH, InjectionBudgetExhausted
from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME

logger = logging.getLogger(__name__)

# 证据块在 prompt 里的头部。明写"按项检索"是给模型的行为约束：它据此知道手里的是**选出来的
# 片段**而不是全文，从而对没给到的材料走证据缺失规则，而不是当成"投标人未提供"判 0。
_EVIDENCE_HEADER = (
    "=== 按评分项检索到的证据片段（服务端确定性检索，含出处与页锚）===\n"
    "说明：以下片段由服务端按 criteria 逐项从招标/投标底稿索引中检出，已跨项去重。"
    "未出现在此处的材料**不等于投标人未提供**——若某项证据不足，按 evidence 缺失规则处理"
    "（manual_review / 不得凭空判 0）。\n\n"
)


@dataclass
class EvidenceContext:
    """证据层对本次评标的产出。

    ``context is None`` 有两种截然不同的含义，靠 ``force_manual_review`` 区分：
    本路径不适用（交回调用方走既有路径）vs 证据层不可用（必须停在人工复核）。
    """

    context: str | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)
    force_manual_review: bool = False


def _criteria_has_items(criteria: Any) -> bool:
    """本路径是否适用：至少要有一个带名字的评分项或资格规则可供检索。"""
    if not isinstance(criteria, dict):
        return False
    items = criteria.get("items")
    rules = criteria.get("eligibility_rules")
    return bool(
        (isinstance(items, list) and any((i or {}).get("item") for i in items if isinstance(i, dict)))
        or (
            isinstance(rules, list)
            and any((r or {}).get("check") for r in rules if isinstance(r, dict))
        )
    )


def _warning(status: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"scope": "证据检索", "status": status, "files": [], "message": message, **extra}


def build_evidence_context(
    *,
    tender_text: str,
    bid_text: str,
    criteria: Any,
    project_id: str,
) -> EvidenceContext:
    """按 criteria 检索两层索引并组装注入块。

    索引在这里**现场同步构建**（S0-B 实测 146 chunk / 0.02s，对 37 万字是秒级），因此不存在
    "索引缺失"这个稳态——建不出来就是底稿本身有问题，直接进人工复核。

    Args:
        tender_text: 招标底稿全文。
        bid_text: 当前被评标这一家的投标底稿全文。
        criteria: 项目规则；不含可检索项时返回"本路径不适用"。
        project_id: 日志定位用。

    Returns:
        :class:`EvidenceContext`。
    """
    if not _criteria_has_items(criteria):
        # 不是失败：没有 criteria 时评标会自行 S1 解析，交回既有路径。
        return EvidenceContext()

    conn = sqlite3.connect(":memory:")
    try:
        stats = build_evidence_index(
            conn, tender_text=tender_text or "", bid_text=bid_text or "", project_id=project_id
        )
        if stats.bid_chunks == 0:
            logger.warning(
                "tender_evidence_index_unavailable",
                extra={"project_id": project_id, "bid_chars": len(bid_text or "")},
            )
            return EvidenceContext(
                force_manual_review=True,
                warnings=[
                    _warning(
                        "evidence_index_unavailable",
                        "本家投标底稿无法建立证据索引（底稿为空或无可切分内容），"
                        "已停止自动评分并转人工复核——带着残缺证据出分比不出分危险得多。",
                    )
                ],
            )
        result = retrieve_evidence(criteria, conn=conn)
    except InjectionBudgetExhausted as exc:
        logger.error("tender_evidence_budget_exhausted", extra={"project_id": project_id})
        return EvidenceContext(
            force_manual_review=True,
            warnings=[
                _warning(
                    "evidence_budget_exhausted",
                    f"注入预算不足以承载本次评标的规则层，已转人工复核：{exc}"
                    f"（标定档 {CALIBRATION_DOC_PATH}）",
                )
            ],
        )
    finally:
        conn.close()

    if not result.blocks:
        # F4：索引建成了却一条证据都检不出，是**结构性异常**（底稿与本项目 criteria 对不上），
        # 不是"这单证据少一点"。旧归宿是回落整份注入——对超预算大标书等于截断错评（复演
        # 08-15），对小标书等于把异常信号消化成一次照常出分。两种情形都是"带残缺证据出分"，
        # 而接管同样不行（模型只会拿到一个空的证据头）。唯一安全归宿是停下来交人工。
        logger.warning(
            "tender_evidence_all_unresolved",
            extra={"project_id": project_id, "items": len(result.unresolved)},
        )
        return EvidenceContext(
            force_manual_review=True,
            warnings=[
                _warning(
                    "evidence_all_unresolved",
                    f"按 criteria 检索本家投标底稿未命中任何证据（{len(result.unresolved)} 项全空）。"
                    "索引已建成却一条都检不出，说明底稿与本项目评分标准对不上（错传文件 / OCR "
                    "失真 / criteria 解析串项），已停止自动评分并转人工复核。",
                )
            ],
        )

    warnings = [
        _warning(
            "evidence_unresolved",
            f"评分项「{item.item}」未检索到证据（已尝试 {len(item.queries)} 个查询串），"
            "该项按证据缺失处理：**不得判 0**，需人工调阅原件确认是真没有还是漏检。",
            queries=item.queries,
        )
        for item in result.unresolved
    ]
    if result.truncated:
        # F5：这些项**检索到了证据**，只是额度被排序靠前的项吃光而没装进注入块。此前它们
        # 既不出块也不进 unresolved，整条路径静默——用户拿到的是一份看似证据齐全的结论。
        warnings.append(
            _warning(
                "evidence_truncated",
                f"{len(result.truncated)} 个项检索到证据但注入额度已用尽，未能进入本次上下文"
                f"（{'、'.join(result.truncated)}）。这些项按证据缺失处理：**不得判 0**，"
                f"需人工调阅原件；若反复出现，说明项数与额度不匹配，按标定档 "
                f"{CALIBRATION_DOC_PATH} 复核 TENDER_EFFECTIVE_CONTEXT_TOKENS。",
                items=list(result.truncated),
            )
        )
    logger.info(
        "tender_evidence_context_built",
        extra={
            "project_id": project_id,
            "blocks": len(result.blocks),
            "tokens": result.total_tokens,
            "unresolved": len(result.unresolved),
        },
    )
    return EvidenceContext(context=_EVIDENCE_HEADER + result.render(), warnings=warnings)


def enforce_manual_review(payload: Any, *, reason: str) -> None:
    """把结论强制改成 ``manual_review`` 并清空 scoring（F7 降级归宿）。

    清空 scoring 是关键：只改 verdict 而留着分数，下游横比与报表照样会把那些分当真。

    Args:
        payload: 模型结论对象；非 dict 直接忽略（信任边界：模型偶发返回非对象）。
        reason: 机器码，写进日志与结论说明。
    """
    if not isinstance(payload, dict):
        return
    payload["verdict"] = "manual_review"
    # rule_gap 是既有枚举里"规则/证据缺位导致无法判定"的那一档（见 tender-evaluate 契约）。
    payload["manual_review_reason"] = "rule_gap"
    extracted = payload.get("extracted_data")
    if isinstance(extracted, dict):
        extracted["scoring"] = []
    logger.warning("tender_evidence_forced_manual_review", extra={"reason": reason})


# 服务端直出结论的 reviewed_by：让人一眼看出这条 manual_review 不是模型判的，而是链路在证据
# 不可用时主动停下来的。两者的后续处置不同（前者复核证据，后者查底稿/索引），不可混为一谈。
_SERVER_REVIEWER = "server.tender.evidence_context"


def build_manual_review_result(
    *,
    request_id: str,
    tenant: str,
    project_id: str | None,
    bid_id: str | None,
    warnings: list[dict[str, Any]],
) -> tuple[dict[str, Any], AgentRunMeta]:
    """证据层不可用时**不发 prompt** 直接产出并归档 manual_review 结论（F7 降级归宿）。

    为什么要走 ``archive_result_payload``：前端拿结论走的是
    ``get_result_payload_by_request_id``（``server/routes/tender/tasks.py:250``）——不归档就等于
    任务显示 completed 却没有任何结论可看，那是又一条静默路径，与本 sprint 要治的病同型。

    Args:
        request_id: 本次评标请求 id。
        tenant: 租户作用域。
        project_id: 招标项目 ID（归档分组键）。
        bid_id: 当前被评标的投标文件 ID（results↔bids join key）。
        warnings: 读层与证据层产出的全部可见信号，随结论落盘。

    Returns:
        ``(payload, meta)``，与 :func:`run_tender_evaluation` 正常返回同形。
    """
    reasons = [str(warning.get("message") or warning.get("status") or "") for warning in warnings]
    payload: dict[str, Any] = {
        "claim_id": bid_id or request_id,
        "verdict": "manual_review",
        "explanation": (
            "证据层不可用，服务端已在发起模型评标前停止本次自动评分并转人工复核："
            "带着残缺证据出分比不出分危险得多（2026-08-15 事故的直接教训）。"
        ),
        "reasons": reasons or ["证据层不可用"],
        "policy_refs": [],
        "risk_score": 0,
        "extracted_data": {"scoring": [], "ocr_warnings": list(warnings)},
        "evidence_chain": [],
        "reviewed_by": _SERVER_REVIEWER,
        "timestamp": utc_now(),
    }
    enforce_manual_review(payload, reason="evidence_layer_unavailable")
    conversation_id = new_conversation_id()
    record = archive_result_payload(
        request_id=request_id,
        tenant=tenant,
        project_id=project_id,
        bid_id=bid_id,
        conversation_id=conversation_id,
        claude_session_id=None,
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=TENDER_OUTPUT_SCHEMA_NAME,
        request_mode="server_short_circuit",
        result_subtype="evidence_layer_unavailable",
        cost_usd=0.0,
        prompt_preview=None,
        response=payload,
    )
    meta = AgentRunMeta(
        request_id=request_id,
        conversation_id=conversation_id,
        claude_session_id=None,
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=TENDER_OUTPUT_SCHEMA_NAME,
        log_file="",
        result_file=record.result_file,
        result_subtype="evidence_layer_unavailable",
        cost_usd=0.0,
        finished_at=utc_now(),
    )
    return payload, meta
