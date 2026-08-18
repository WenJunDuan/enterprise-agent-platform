"""底稿层决策与完整性告警：预热底稿的取用，以及"底稿有洞"的两个消费面。

从 ``server/tender/runner.py`` 纯移动而来（2026-08-14，runner.py 419 行拆分）：整函数搬家 +
import 接线，函数体、命名、日志文案、注释语义逐字未改。runner.py 保留 ``run_tender_evaluation``
主流程（底稿获取 / 预算闸 / 模型调用 + 契约重试）与 ``_ocr_integrity_warnings`` 的 re-export。

一个变更理由：**底稿层（tender_doc_store 预热）的取用与降级表达**。同一批 warning 有两个消费面
——注入给模型的上下文块（``_ocr_warning_block``）与随结论落盘的字段（``_inject_ocr_warnings``）
——两者必须同源同文案，故同处一家。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from server.stores.tender_doc_store import decode_failed_files
from server.tender import doc_layer, doc_rerun
from server.tender.evidence_context import EvidenceContext, build_evidence_context

logger = logging.getLogger(__name__)


def _ocr_integrity_warnings(
    project_doc: dict | None, bid_doc: dict | None
) -> list[dict[str, object]]:
    """把"底稿降级/部分缺失"渲染成结构化 warning（H3 KD2：不静默）。

    Returns:
        每条形如 ``{"scope", "status", "files", "message"}``；无问题时空列表。
    """
    warnings: list[dict[str, object]] = []
    for scope, row in (("招标文件", project_doc), ("投标文件", bid_doc)):
        status = doc_layer.doc_ocr_status(row)
        if status not in doc_layer.DOC_LAYER_IMPAIRED_STATUSES:
            continue
        # 列解析走 store 的 decode（编解码同处一家）；"没记清单"与"清单为空"在 warning 里同义，
        # 故 None 归一成 []（warning 照发，只是不点名文件）。
        files = decode_failed_files((row or {}).get("ocr_failed_files")) or []
        detail = "部分文件识别失败或缺页" if status == "partial" else "含降级识别段（本地兜底引擎）"
        named = f"：{'、'.join(files)}" if files else ""
        warnings.append(
            {
                "scope": scope,
                "status": status,
                "files": files,
                "message": f"{scope}底稿{detail}{named}；依赖这些材料的评分项证据可能不完整。",
            }
        )
    return warnings


def _inject_ocr_warnings(payload: object, warnings: list[dict[str, object]]) -> None:
    """把底稿完整性 warning 强制写进结论（``extracted_data.ocr_warnings``）。

    落在 ``extracted_data`` 而非顶层：``audit-result.schema.json`` 顶层是
    ``additionalProperties: false``，而 ``extracted_data`` 显式允许自由字段——既不动共享 schema，
    也保证 warning 随结论一起持久化、可回溯。
    """
    if not warnings or not isinstance(payload, dict):
        return
    extracted = payload.get("extracted_data")
    if not isinstance(extracted, dict):
        extracted = {}
        payload["extracted_data"] = extracted
    existing = extracted.get("ocr_warnings")
    extracted["ocr_warnings"] = (existing if isinstance(existing, list) else []) + warnings


@dataclass
class DocLayerOutcome:
    """读层对本次评标的完整决策结果。

    三个信号必须一起返回：pass1 的 REWORK 正是因为只回传了 ``text``，
    ``warnings`` 与 ``force_manual_review`` 落地即丢，降级归宿形同虚设。

    ``from_evidence_layer`` 回答的是"``text`` 是**按评分项检出的片段**还是**整份底稿**"。
    调用方据此裁定字节闸触发时的归宿：整份底稿被腰斩 = 评分失去权威性（转人工），而证据层
    片段的体量由 ``injection_budget`` 闭式账目保证，不该被同一条闸判死。**不能靠嗅探文本
    特征反推**——那等于把归宿判定挂在注入头的措辞上。
    """

    text: str | None = None
    warnings: list[dict[str, object]] = field(default_factory=list)
    force_manual_review: bool = False
    from_evidence_layer: bool = False


async def _resolve_doc_layer(
    project_id: str, bid_id: str | None, tenant: str
) -> DocLayerOutcome:
    """评标入口对预热底稿的完整决策（H3 KD2 + KD5 + S3 证据层）。

    顺序：等预热到终态（in-flight 才等，不再无条件超时回落 inline）→ 对 degraded/partial 自动
    重跑一次预热 → **先试证据层按项检索**（带出 warnings / force_manual_review）→ 不适用才
    回落既有拼接底稿 → 按最终状态生成结论 warning。

    Returns:
        :class:`DocLayerOutcome`。``force_manual_review`` 为真时调用方**不得**回落 inline，
        必须直接产出 manual_review 结论（F7：错评分比失败危险）。
    """
    warnings: list[dict[str, object]] = []
    waited_from = time.monotonic()
    if bid_id:
        outcome = await doc_layer.wait_doc_layer_ready(project_id, bid_id, tenant)
        if outcome == "wait_cap_reached":
            warnings.append(
                {
                    "scope": "预热 OCR",
                    "status": "prewarm_timeout",
                    "files": [],
                    "message": "预热 OCR 在评标等待上限内未完成，已改用即时 OCR；底稿可能不完整。",
                }
            )
        elif outcome == "terminal":
            rows = await doc_layer.read_doc_rows(project_id, bid_id, tenant)
            if any(
                doc_layer.doc_ocr_status(row) in doc_layer.DOC_LAYER_IMPAIRED_STATUSES
                for row in rows
            ):
                # 等预热花掉的时间要计入补跑预算（review N3）——否则等满上限后还能再放一段
                # 全尺寸补跑，把整单继续往 TENDER_TIMEOUT 推。
                await doc_rerun.rerun_prewarm_for_degraded_docs(
                    project_id, bid_id, tenant, rows, spent_sec=time.monotonic() - waited_from
                )
    if doc_layer.slim_context_enabled():
        evidence = await asyncio.to_thread(load_evidence_context, project_id, bid_id, tenant)
        if evidence is not None:
            # 证据层的四类信号无论走哪个分支都必须落结论（AC2 无静默路径）。
            warnings.extend(evidence.warnings)
            if evidence.context is not None:
                warnings.extend(await _integrity_warnings_now(project_id, bid_id, tenant))
                return DocLayerOutcome(
                    text=evidence.context, warnings=warnings, from_evidence_layer=True
                )
            if evidence.force_manual_review:
                return DocLayerOutcome(warnings=warnings, force_manual_review=True)

    loader = (
        doc_layer.load_doc_layer_context_slim
        if doc_layer.slim_context_enabled()
        else doc_layer.load_doc_layer_context
    )
    doc_layer_text = await asyncio.to_thread(loader, project_id, bid_id, tenant)
    if doc_layer_text is None:
        # KD4：掉落 inline 此前只在日志里留一行 INFO——三次事故的共同放大器就是这种静默。
        warnings.append(await _doc_layer_fallback_warning(project_id, bid_id, tenant))
    else:
        warnings.extend(await _integrity_warnings_now(project_id, bid_id, tenant))
    return DocLayerOutcome(text=doc_layer_text, warnings=warnings)


async def _integrity_warnings_now(
    project_id: str, bid_id: str | None, tenant: str
) -> list[dict[str, object]]:
    """重读 doc 行生成完整性 warning——必须反映**最终**状态，重跑成功就不该再报警。"""
    if not bid_id:
        return []
    project_doc, bid_doc = await doc_layer.read_doc_rows(project_id, bid_id, tenant)
    return _ocr_integrity_warnings(project_doc, bid_doc)


# 掉落原因的用户可读说明。键与 :func:`describe_doc_layer_gap` 的机器码一一对应；
# 新增分支漏配文案会命中 _FALLBACK_REASON_TEXT 的兜底（仍可见），不会静默。
_FALLBACK_REASON_TEXT = {
    "missing_bid_id": "提交时未能定位本次投标的预热记录",
    "tender_doc_absent": "招标文件没有预热底稿记录",
    "tender_doc_not_usable": "招标文件预热 OCR 尚未就绪或已失败",
    "bid_doc_absent": "本家投标文件没有预热底稿记录",
    "bid_doc_not_usable": "本家投标文件预热 OCR 尚未就绪或已失败",
    "bid_doc_empty": "本家投标文件预热底稿为空",
    "doc_layer_unreadable": "预热底稿读取失败",
}


async def _doc_layer_fallback_warning(
    project_id: str, bid_id: str | None, tenant: str
) -> dict[str, object]:
    """把"没用上预热底稿"渲染成结论级 warning（AC2：降级必须留可见痕迹）。"""
    reason = (
        await asyncio.to_thread(describe_doc_layer_gap, project_id, bid_id, tenant)
        or "doc_layer_unusable"
    )
    detail = _FALLBACK_REASON_TEXT.get(reason, "预热底稿不可用")
    return {
        "scope": "评标底稿链路",
        "status": "doc_layer_fallback",
        "reason": reason,
        "files": [],
        "message": (
            f"未复用预热底稿（{detail}；原因码 {reason}），已改用即时 OCR 重新识别本案目录；"
            "证据出处与页锚可能与预热底稿不一致，耗时也显著更长。"
        ),
    }


def _ocr_warning_block(warnings: list[dict[str, object]]) -> str:
    """把底稿完整性 warning 渲染进模型上下文——评分项据此走 evidence 缺失规则，而不是静默判低分。"""
    lines = "\n".join(f"- {warning['message']}" for warning in warnings)
    return (
        "\n\n=== 底稿完整性告警（本次识别底稿存在降级/缺失）===\n"
        f"{lines}\n"
        "依赖上述材料的评分项：证据不足时按现行 evidence 缺失规则处理（manual_review / 不得凭空判 0）。"
    )


def load_evidence_context(
    project_id: str, bid_id: str | None, tenant: str
) -> EvidenceContext | None:
    """走证据层组装本次评标的注入块，并把降级信号一并带出（S3）。

    与 :func:`doc_layer.load_doc_layer_context_slim` 的分工：那个只返回文本（十余处测试按 ``str | None``
    monkeypatch 它），而调用方还需要 ``warnings`` 与 ``force_manual_review`` 两个**必须上界面**
    的信号，故单开一个返回结构化结果的入口，不去改既有 loader 的签名。

    Args:
        project_id: 招标项目 ID。
        bid_id: 当前被评标的投标文件 ID。
        tenant: 租户作用域。

    Returns:
        :class:`EvidenceContext`；读层本身不可用（缺 bid_id / 底稿未就绪 / DB 故障）时返回
        ``None``，由调用方按既有掉落逻辑处理。
    """
    if not bid_id:
        return None
    try:
        project_doc = doc_layer.get_project_doc(project_id, tenant)
        if doc_layer.doc_ocr_status(project_doc) not in doc_layer.DOC_LAYER_USABLE_STATUSES:
            return None
        bid = doc_layer.get_bid_doc(project_id, bid_id, tenant)
        if doc_layer.doc_ocr_status(bid) not in doc_layer.DOC_LAYER_USABLE_STATUSES or not bid.get("ocr_text"):
            return None
        return build_evidence_context(
            tender_text=project_doc["ocr_text"],
            bid_text=bid["ocr_text"],
            criteria=doc_layer._parse_stored_criteria(project_doc.get("criteria")),
            project_id=project_id,
        )
    except ValueError:
        raise  # 枚举违约是内部不变量破坏，与既有读层同一归宿
    except Exception:
        logger.warning(
            "tender_evidence_context_failed",
            extra={"project_id": project_id, "bid_id": bid_id},
            exc_info=True,
        )
        return None


def describe_doc_layer_gap(project_id: str, bid_id: str | None, tenant: str) -> str | None:
    """回答"这次为什么用不了预热底稿"，供 KD4 把静默掉落变成用户可见 warning。

    只在读层已返回 None 后调用（多一次 doc 行读，代价 = 两条主键查询）。刻意**不**与
    :func:`_build_doc_context` 合流成"返回值带原因"：后者被十余处测试按 ``str | None``
    monkeypatch，改签名等于把可见性改造的成本转嫁成一次大范围返工。

    Args:
        project_id: 招标项目 ID。
        bid_id: 当前被评标的投标文件 ID；``None`` 即"无法定位当前家"。
        tenant: 租户作用域。

    Returns:
        具名原因机器码；确实可用（不该走到这里）时返回 ``None``；读层故障返回
        ``doc_layer_unreadable``。
    """
    if not bid_id:
        return "missing_bid_id"
    try:
        project_doc = doc_layer.get_project_doc(project_id, tenant)
        bid = doc_layer.get_bid_doc(project_id, bid_id, tenant)
    except Exception:
        logger.warning("tender_doc_layer_gap_read_failed", exc_info=True)
        return "doc_layer_unreadable"
    if project_doc is None:
        return "tender_doc_absent"
    if doc_layer.doc_ocr_status(project_doc) not in doc_layer.DOC_LAYER_USABLE_STATUSES:
        return "tender_doc_not_usable"
    if bid is None:
        return "bid_doc_absent"
    if doc_layer.doc_ocr_status(bid) not in doc_layer.DOC_LAYER_USABLE_STATUSES:
        return "bid_doc_not_usable"
    if not bid.get("ocr_text"):
        return "bid_doc_empty"
    return None
