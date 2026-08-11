"""Evidence-resolution gate: deterministically verify that every cited source in a
tender verdict actually exists in this case's OCR/底稿 (anti-fabrication + 定位回查).

业务背景：评标结论里模型引用的每条出处 ``(文件, 第N页, 原文 quote)``，此前**无任何代码**
回查它是否真在本案底稿里——靠提示词自检不可靠（8636 页远超模型可核实范围，会脑补页码/原文）。
本模块在结论后处理（``apply_schema_semantics`` 的 ``resolve`` hook）拿到本案底稿，对每条出处的
逐字 quote 做确定性回查，分四档（resolved / page_mismatch / weak_match / unresolved），仅
``unresolved`` 降级承重评分项为 ``manual_review``，把"定位不准/引文不实"从静默通过变成可抓、可降级。

设计哲学（对齐 [[learning-absence-is-not-zero]] / 校验层兜底）：
- **存在性=主信号**：「原文是否在该 tier 底稿里」是抗编造的稳健硬信号（与具体文件无关）；
  file/page 精度只作细化标注，绝不单独支撑 resolved（19 家投标各自 ``【第N页】`` 从 1 重置，
  按 ``(tier, page)`` 索引会跨文件误命中 → 必须 file 级）。
- **宁漏勿误杀**：双阈值 + 中间带 ``weak_match`` 不降级（模型转述非逐字易触发，先漏报勿误杀）。
- **失败安全**：任何异常 → 原样返回结论，绝不因回查崩掉评标。

F5 evidence 拆分（本模块新家，原 ``server/common/evidence_resolution.py``）：通用语料解析/匹配
原语（切段/file-level 索引/存在性匹配度/page 精度细化/出处解析/双阈值分类）已搬到
``server/common/corpus.py``（OCR/D7 结构化检索复用，无 scoring 语义）；本模块只留 tender 专属的
scoring 证据回查闸（含降级 + verdict 一致性回填）。

纯函数 + 无副作用（除原地标注传入的 output），无 SDK / 网络依赖。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from server.common.corpus import (
    CorpusIndex,
    _classify,
    existence_ratio,
    normalize_text,
    page_status,
    parse_corpus,
    parse_source,
)

logger = logging.getLogger(__name__)

# ── 配置（运行时动态读 env，便于灰度调参，对齐 tender_worker 既有 env 模式）──────


def _enabled() -> bool:
    """Whole gate on/off (``TENDER_EVIDENCE_RESOLUTION``, default on)。"""
    return os.getenv("TENDER_EVIDENCE_RESOLUTION", "1").lower() in {"1", "true", "yes"}


def _downgrade_enabled() -> bool:
    """是否对 unresolved 承重项降级 + 升 verdict（``EVIDENCE_RESOLUTION_DOWNGRADE``, default on）。

    灰度阶段可设 0 看纯标注命中率/假阴性率，调好阈值再开降级。
    """
    return os.getenv("EVIDENCE_RESOLUTION_DOWNGRADE", "1").lower() in {"1", "true", "yes"}


def _annotate_resolved() -> bool:
    """resolved 项是否也写 ``resolution`` 标注（默认开，便于统计；0 = 只标异常）。"""
    return os.getenv("RESOLUTION_ANNOTATE_RESOLVED", "1").lower() in {"1", "true", "yes"}


def _min_quote_chars() -> int:
    try:
        return int(os.getenv("EVIDENCE_MIN_QUOTE_CHARS", "8"))
    except (TypeError, ValueError):
        return 8


# ── 主回查逻辑 ────────────────────────────────────────────────────────────────


def _check_one(
    *,
    container: dict[str, Any],
    source: str | None,
    quote: str | None,
    where: str,
    index: CorpusIndex,
    summary: dict[str, Any],
    high_severity: bool = False,
) -> str | None:
    """回查一条出处：原地给 ``container`` 写 ``resolution``，更新 summary，返回判定档（或 None=跳过）。"""
    norm_quote = normalize_text(quote or "")
    if len(norm_quote) < _min_quote_chars():
        return None  # 无逐字 quote / 太短 → 不可靠，不判（honesty：不谎称已核实）
    tier, page = parse_source(source)
    ratio = existence_ratio(norm_quote, index.corpus_for(tier))
    status = _classify(ratio)
    summary["checked"] += 1
    summary[status] = summary.get(status, 0) + 1

    annotation: dict[str, Any] = {"status": status}
    if status == "resolved":
        pstat = page_status(index, tier, page, norm_quote)
        annotation["page"] = pstat
        if pstat == "page_mismatch":
            summary["page_mismatch"] = summary.get("page_mismatch", 0) + 1
    if status != "resolved" or _annotate_resolved():
        container["resolution"] = annotation

    if status == "unresolved":
        ref = {
            "where": where,
            "source": source or "",
            "quote_preview": (quote or "")[:60],
            "severity": "high" if high_severity else "normal",
        }
        if high_severity:
            summary["high_severity_unresolved"].append(ref)
        else:
            summary["unresolved_refs"].append(ref)
    return status


def _hit_moves_score(hit: dict[str, Any], hits_key: str) -> bool:
    """该命中是否实际影响得分（award_hits 的 ``awarded`` / deduction_hits 的 ``deducted`` ≠ 0）。

    子项级降级（治"含一个 0 分未核实子项就把整项 manual"）：得 0 分的命中（如「无偏离」常规参数
    子项 awarded=0）没有可核验的"得分主张"，其出处即便 unresolved 也**不应**把同项里有检测报告
    支撑的有分子项（如性能参数 21 分 resolved）连带降人工。仅当一条**带非零分**的命中出处核不实，
    才说明"拿了不可核验的分"→ 触发降级。分值字段缺失 / 非数 → 保守视为移动得分（仍触发，不放松）。
    """
    points = hit.get("awarded") if hits_key == "award_hits" else hit.get("deducted")
    if points is None:
        return True  # 缺分值字段 → 保守仍触发（不削弱闸）
    if isinstance(points, bool) or not isinstance(points, (int, float)):
        return True
    return points != 0


def _check_hits(
    sitem: dict[str, Any],
    hits_key: str,
    where_prefix: str,
    index: CorpusIndex,
    summary: dict[str, Any],
) -> bool:
    """回查一个评分项的 ``deduction_hits``/``award_hits``；任一**带非零分**命中 unresolved → True（触发降级）。

    子项级：得 0 分的命中（无得分主张）出处 unresolved 不触发降级，避免有检测报告支撑的有分子项
    被同项里的 0 分未核实子项连带 manual。
    """
    has_unresolved = False
    hits = sitem.get(hits_key)
    if not isinstance(hits, list):
        return False
    for hi, hit in enumerate(hits):
        if not isinstance(hit, dict):
            continue
        ev = hit.get("evidence")
        if not isinstance(ev, dict):
            continue
        status = _check_one(
            container=ev,
            source=ev.get("source"),
            quote=ev.get("quote"),
            where=f"{where_prefix}.{hits_key}[{hi}]",
            index=index,
            summary=summary,
        )
        if status == "unresolved" and _hit_moves_score(hit, hits_key):
            has_unresolved = True
    return has_unresolved


_DOWNGRADE_NOTE = " ⚠ 出处未在底稿核实（evidence_unresolved），已降人工复核"
_LOW_CLARITY_NOTE = " ⚠ 出处文件 OCR 低置信，『读不清≠没提供』，已降人工复核（R3）"


def _downgrade_scoring_item(
    sitem: dict[str, Any],
    *,
    note: str,
    resolution_status: str,
    summary: dict[str, Any],
) -> bool:
    """scored → manual_review（仅迁移一次，幂等）。返回 True 当且仅当本次发生真实状态迁移。

    unresolved 与 low_clarity 共用，保证同项双触发不重复降级 / 不重复 basis。
    """
    cur_basis = str(sitem.get("basis") or "")
    if sitem.get("status") == "scored":
        sitem["status"] = "manual_review"
        sitem["score"] = None
        # KD5：回查降级造出的 null 必须自带待定原因（出处未核实/底稿读不清），
        # 否则归档结论会违反 pending_reason 契约、消费端又要靠猜。
        sitem["pending_reason"] = "evidence_unresolved"
        sitem["basis"] = cur_basis + note
        sitem["resolution"] = {"status": resolution_status}
        summary["downgraded_items"].append(sitem.get("item"))
        return True
    # 已非 scored（如 unresolved 先降）：仅补本 note（不重复），不算新迁移
    if note.strip() not in cur_basis:
        sitem["basis"] = cur_basis + note
    return False


def _flag_low_clarity_sources(sitem: dict[str, Any], index: CorpusIndex) -> str | None:
    """扫 scoring 项的 evidence 命中 source + basis，是否点名某 low 文件；命中则给该 evidence 标
    独立字段 ``clarity_flag``（不碰 resolution），返回被点名的文件名或 None。"""
    named: str | None = None
    for hits_key in ("deduction_hits", "award_hits"):
        hits = sitem.get(hits_key)
        if not isinstance(hits, list):
            continue
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            ev = hit.get("evidence")
            if isinstance(ev, dict):
                f = index.source_names_low_clarity_file(ev.get("source"))
                if f:
                    ev["clarity_flag"] = "low"
                    named = named or f
    # absence 项常把文件写进 basis（无 evidence hit）→ 也扫 basis（仍需点名 low 文件，保守）
    f = index.source_names_low_clarity_file(sitem.get("basis"))
    return named or f


def resolve_audit_evidence(structured_output: Any, evidence_source: str) -> Any:
    """``resolve`` hook 入口：回查 audit-result 结论里所有出处 vs 本案底稿，标注 + 降级 + verdict 一致性回填。

    Args:
        structured_output: 已过 normalize/validate/enrich 的结论（dict）。
        evidence_source: 本案底稿（带 ``### 文件:`` + ``【第 N 页】`` 锚点，tender_worker 透传的 ocr_block）。

    Returns:
        原对象（原地标注）；任何异常或开关关闭 → 原样返回（绝不崩评标）。
    """
    try:
        if not isinstance(structured_output, dict) or not evidence_source or not _enabled():
            return structured_output
        segments = parse_corpus(evidence_source)
        if not segments:
            return structured_output
        index = CorpusIndex(segments)

        summary: dict[str, Any] = {
            "checked": 0,
            "resolved": 0,
            "weak_match": 0,
            "unresolved": 0,
            "page_mismatch": 0,
            "loc_only": 0,
            "downgraded_items": [],
            "high_severity_unresolved": [],
            "unresolved_refs": [],
            "low_clarity_files": index.low_clarity_files(),  # 低置信文件可见性 emit
        }
        downgrade = _downgrade_enabled()
        any_new_manual = False

        # 1. evidence_chain（quote 固定 = finding，normalize 已剥到 {source,finding,conclusion}）
        chain = structured_output.get("evidence_chain")
        if isinstance(chain, list):
            for i, item in enumerate(chain):
                if isinstance(item, dict):
                    _check_one(
                        container=item,
                        source=item.get("source"),
                        quote=item.get("finding"),
                        where=f"evidence_chain[{i}]",
                        index=index,
                        summary=summary,
                    )

        extracted = structured_output.get("extracted_data")
        if isinstance(extracted, dict):
            # 2. scoring：deduction_hits/award_hits 逐字回查 → unresolved 降级该项
            scoring = extracted.get("scoring")
            if isinstance(scoring, list):
                for si, sitem in enumerate(scoring):
                    if not isinstance(sitem, dict):
                        continue
                    where = f"scoring[{si}]"
                    unresolved = _check_hits(sitem, "deduction_hits", where, index, summary)
                    unresolved |= _check_hits(sitem, "award_hits", where, index, summary)
                    has_structured_quote = bool(
                        sitem.get("deduction_hits") or sitem.get("award_hits")
                    )
                    # 是否点名 low 文件（同时给 evidence 打 clarity_flag）
                    low_clarity_named = _flag_low_clarity_sources(sitem, index)
                    # 低置信兜底触发：scored 且 score==0（"读不清却判 0"嫌疑）且点名 low 文件
                    g3_hit = (
                        low_clarity_named is not None
                        and sitem.get("status") == "scored"
                        and sitem.get("score") == 0
                    )
                    if downgrade and unresolved:
                        any_new_manual |= _downgrade_scoring_item(
                            sitem,
                            note=_DOWNGRADE_NOTE,
                            resolution_status="downgraded_unresolved",
                            summary=summary,
                        )
                    elif downgrade and g3_hit:
                        any_new_manual |= _downgrade_scoring_item(
                            sitem,
                            note=_LOW_CLARITY_NOTE,
                            resolution_status="downgraded_low_clarity",
                            summary=summary,
                        )
                    elif not has_structured_quote and sitem.get("status") in {
                        "scored",
                        "manual_review",
                        "rejected",
                    }:
                        # banded/formula/pass_fail 项无离散逐字 quote → 只标 loc_only；
                        # 不谎称已核实，也不宣称已覆盖全部承重依据。
                        sitem.setdefault("resolution", {"status": "loc_only"})
                        summary["loc_only"] += 1
                    # unresolved + low_clarity 同项双触发：unresolved 已降级走上面 if 分支、
                    # low_clarity elif 被跳过，此处补低置信 note，保证降级原因完整不丢。
                    if (
                        downgrade
                        and unresolved
                        and g3_hit
                        and _LOW_CLARITY_NOTE.strip() not in str(sitem.get("basis") or "")
                    ):
                        sitem["basis"] = str(sitem.get("basis") or "") + _LOW_CLARITY_NOTE

            # 3. 废标/资格依据（高危，仅标注不动 verdict——废标 verdict 是高代价决定）
            for key in ("disqualification_hits", "eligibility_checks"):
                hits = extracted.get(key)
                if not isinstance(hits, list):
                    continue
                for di, hit in enumerate(hits):
                    if not isinstance(hit, dict):
                        continue
                    ev = hit.get("evidence")
                    if isinstance(ev, dict):
                        _check_one(
                            container=ev,
                            source=ev.get("source"),
                            quote=ev.get("quote"),
                            where=f"{key}[{di}]",
                            index=index,
                            summary=summary,
                            high_severity=True,
                        )

        # 4. verdict/result 一致性回填：降级新引入 manual_review 项 → 顶层须一致
        if any_new_manual and downgrade:
            verdict = structured_output.get("verdict")
            if verdict == "approved":
                structured_output["verdict"] = "manual_review"
                structured_output["manual_review_reason"] = "insufficient_evidence"
                # 惰性 import 避循环（server.tender.output 末尾 import 本模块注册 resolve hook）。
                # F1[P0]（Round-1 critic）：这里必须用 tender **组合版** enrich_tender_result（含
                # _finalize_user_explanation 重算得分小结），不得用 common 的瘦身通用版
                # enrich_audit_decision——否则 verdict 已翻 manual_review、评分已降 null，但
                # explanation 仍停在陈旧的"综上，合计 X 分"，静默失真呈现给人工复核
                # （见 tests/test_evidence_resolution.py::
                # test_pipeline_evidence_downgrade_refreshes_score_summary_in_explanation）。
                from server.tender.output import enrich_tender_result

                enrich_tender_result(structured_output)  # 幂等重派生 result/conclusion/得分小结
            elif verdict == "manual_review":
                structured_output.setdefault("manual_review_reason", "insufficient_evidence")
            # verdict == "rejected"：终局更强，不因单项未核实翻盘

        # 5. 摘要（有回查 或 有低置信文件即写，勿因无 quote 吞掉 low_clarity_files）
        if isinstance(extracted, dict) and (summary["checked"] > 0 or summary["low_clarity_files"]):
            extracted["evidence_resolution"] = summary
        return structured_output
    except Exception:  # noqa: BLE001 - 失败安全：绝不因回查崩评标
        logger.warning("evidence_resolution failed; returning output unchanged", exc_info=True)
        return structured_output
