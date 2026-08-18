"""Tender 招标/投标文档摄取编排：上传后台 OCR → criteria/tender_info 抽取（S3 从 tender.py 下沉）。

server/tender/ feature 层 helper（与 ``worker`` 同级，非 HTTP router；D2 从
``routes/tender_doc_pipeline.py`` 纯移动至此，见 D2 design T3）。它把 OCR 通用能力（
``server.ocr.pipeline`` 的 ``prewarm_and_report`` + ``server.ocr.prewarm_scheduler``
的并发闸/任务追踪）与 tender 业务（写 ``tender_doc_store``、调 ``tender-extract-info``）粘合。

放 feature 层：本编排需同时用 ocr + stores + common，feature 层可合法向下 import 三者（见
``tests/test_layering.py``）；``routes/tender.py`` 路由消费本模块，自身仅做 HTTP 编排。
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from pathlib import Path
from typing import Any

from server.common.command_adapter import run_command_json
from server.common.contract import is_non_retryable
from server.common.json_bridge import run_agent_json
from server.ocr.pipeline import prewarm_and_report
from server.ocr.prewarm_scheduler import run_prewarm_with_heartbeat, track_upload_ocr_task
from server.stores.tender_doc_store import (
    touch_bid_doc_ocr,
    touch_project_doc_ocr,
    update_bid_doc_ocr,
    update_project_doc_criteria_extracted,
    update_project_doc_ocr,
)
from server.stores.tender_project_store import update_project_fields_if_empty
from server.tender.context_slim import build_preextract_tender_context
from server.tender.contract_repair import build_extraction_repair_prompt, repair_session_id

# re-export：server.routes.tender 从本模块 import TENDER_OCR_PURPOSE（既有引用点不变）。
# ``DRAFT_INJECTED_TOOLS`` 是**复用**评标侧同一个常量对象（不是抄一份）：底稿在场时两条路径
# 的工具面必须同进同退，各存一份必然漂移。
from server.tender.runner import DRAFT_INJECTED_TOOLS
from server.tender.runner import TENDER_OCR_PURPOSE as TENDER_OCR_PURPOSE

logger = logging.getLogger(__name__)


def _tender_slim_context_enabled() -> bool:
    """Return True when the opt-in tender context slimming path is enabled."""
    return os.getenv("TENDER_SLIM_CONTEXT", "0").lower() in {"1", "true", "yes"}


# criteria 抽取的契约失败重试次数。2026-08-17 生产事故：这里原本一发定生死——一次
# ``JSONContractError`` 就落 criteria_status=failed，criteria 缺位让证据层整条跳过，评标退回
# 全量注入并被截断（那次会话只看到 23% 的材料）。失败形态与评标侧同型（文本模式下模型没有
# 只输出 JSON），处置也同型：拿得到 CLI 会话 id 就 resume 修一轮，拿不到才整跑。
# 默认 1：修补轮是常数级短指令，一轮还不听话多半这次就是不听话，再加轮次只会把上传后的
# criteria 等待期（评标入口要等它到终态）拖长。
EXTRACT_CONTRACT_MAX_RETRY = 1

# criteria 抽取的硬超时（秒），形态与评标侧 ``worker.TENDER_TIMEOUT_SEC`` 同款（模块级常量 +
# env 覆盖 + ``asyncio.wait_for`` 包住整次调用）。抽取此前**根本没有超时**：线上实测一次抽取
# 跑到 16 分钟仍未结束，而评标入口要等 criteria 到终态才放行——一次挂死把整条链路一起拖住。
# 上限覆盖整个重试环（整跑 + 修补轮），因为要封的是"这次抽取一共能占多久"，不是单次往返。
EXTRACT_TIMEOUT_SEC = float(os.getenv("TENDER_EXTRACT_TIMEOUT_SEC", "1200"))

_EXTRACTION_OUTPUT_GUARD = (
    "=== 服务端输出约束（最高优先级）===\n"
    "criteria.schema.json 和 tender-info.schema.json 已由服务端预加载；禁止调用 Read、Glob 或任何工具。"
    "请立即完成抽取。\n"
    "只输出一个合法 JSON 对象，首字符必须是 {，末字符必须是 }，不要输出分析、Markdown 围栏、"
    "<think>、<tool_call> 或英文散文。字符串内的半角双引号必须转义或改用中文引号。"
)


# TENDER_OCR_PURPOSE 挪家 server/tender/runner.py（D1 T2 方案 i 接缝）：评标 OCR 与本模块的上传
# 预热 OCR 共用同一目的字符串，evaluation 核心下沉后常量随之下沉，本模块改 import 复用（routes→
# features 合法方向），消除原先两处重复的语义未变。

# 评标方法枚举归一化（criteria.schema method enum）。模型常把"综合评估法"写成"综合评分法/打分法"，
# 把法定方法名写成口语变体——这是 enum 校验最常见的漂移点。代码侧确定性归一化比 prompt 约束可靠
# （跨 qwen/deepseek/opus 一致），避免单字之差让整份合格 criteria 被判 failed（criteria 价值在 items
# 评分项/扣分点，不在 method 标签）。映射不到的归 "其他"（schema 的兜底枚举），校验恒过、structure 仍判。
_METHOD_CANON = "综合评估法"
_METHOD_LOWEST = "经评审的最低投标价法"
_METHOD_ALIASES = {
    "综合评估法": _METHOD_CANON,
    "综合评分法": _METHOD_CANON,
    "综合打分法": _METHOD_CANON,
    "综合评议法": _METHOD_CANON,
    "综合评价法": _METHOD_CANON,
    "经评审的最低投标价法": _METHOD_LOWEST,
    "经评审最低投标价法": _METHOD_LOWEST,
    "最低投标价法": _METHOD_LOWEST,
    "最低评标价法": _METHOD_LOWEST,
    "合理低价法": _METHOD_LOWEST,
}
# criteria item.tag 枚举（必填）。模型常把 variables[].source 的短名（cross_bid/external_data/
# live_event/derived）误写成 tag → 别名映射到对应 tag 枚举。
_TAG_CANON = {
    "scored",
    "requires_live_event",
    "requires_external_data",
    "requires_cross_bid_comparison",
}
_TAG_ALIASES = {
    "cross_bid": "requires_cross_bid_comparison",
    "requires_cross_bid": "requires_cross_bid_comparison",
    "external_data": "requires_external_data",
    "live_event": "requires_live_event",
    "derived": "requires_cross_bid_comparison",
}
# 不可识别 tag 的兜底：选一个强制人工复核的枚举（绝不默认 scored 冒充可自动判定）。
_TAG_FALLBACK = "requires_external_data"
_MANUAL_NULL_TAGS = _TAG_CANON - {"scored"}
_SCORE_MODES = {"deduction", "banded", "additive", "formula", "pass_fail", "manual"}


# criteria 结构缺陷的用户可读说明（KD4/AC3）。此前只有一个 bool + 一句笼统的
# "no usable items"，用户在界面上只看得到"识别失败"，无从判断是该重传文件还是该手填规则。
_CRITERIA_PROBLEM_TEXT = {
    "criteria_not_object": "评分标准不是一个对象，抽取结果结构性损坏",
    "items_missing": "评分标准里没有 items 评分项字段",
    "items_not_array": "评分标准的 items 不是数组",
    "items_empty": "评分标准的 items 评分项为空",
    "item_not_object": "存在不是对象的评分项条目",
    "item_name_missing": "存在没有名称的评分项",
    "item_max_invalid": "存在满分非法的评分项（须为有限非负数；仅 manual 且需外部输入的项可为空）",
    "no_numeric_max": "没有任何一项带数值满分，无法据此逐项判分",
}


class CriteriaUnusableError(ValueError):
    """criteria 结构 sanity 检查未过；``problem`` 携带具名机器码供界面渲染（AC3）。"""

    def __init__(self, problem: str) -> None:
        super().__init__(f"extracted criteria failed structural sanity check: {problem}")
        self.problem = problem


def criteria_usability_problem(criteria_obj: object) -> str | None:
    """承重结构 sanity 检查（codex R1 P1）：criteria 是否「能用来评标」。

    刻意**不**用整份 jsonschema 校验——模型输出几乎总有零星叶子瑕疵（enum 漂移、某个
    formula_spec.cap 写成对象、多一个字段），整份 all-or-nothing 校验会因一个叶子误杀整套
    14 项合格 criteria，让本功能形同虚设（实测 qwen 三处枚举/类型漂移）。

    评标真正承重的最小结构 = 有评分项 + 每项有名字 + 至少一个数值满分（S3 据此逐项判分）；其余
    枚举/嵌套细节由 normalize_criteria_enums 尽力归一化、注入评标也只作文本 hint、区2 展示也
    防御式渲染，零星瑕疵无害。数值满分必须是有限非负数；仅 ``manual`` 且非 ``scored`` 的项目
    允许 ``max=null``，这种项目计入评分项数量但不参与满分算术。

    Returns:
        ``None`` 表示可用；否则返回**具名机器码**（见 ``_CRITERIA_PROBLEM_TEXT``）。AC3：旧实现
        只返回 bool，失败时用户界面只显示"识别失败"，无从判断该重传还是该手填。
    """
    if not isinstance(criteria_obj, dict):
        return "criteria_not_object"
    items = criteria_obj.get("items")
    if items is None:
        return "items_missing"
    if not isinstance(items, list):
        return "items_not_array"
    if not items:
        return "items_empty"
    has_numeric_max = False
    for item in items:
        if not isinstance(item, dict):
            return "item_not_object"
        name = item.get("item")
        if not isinstance(name, str) or not name.strip():
            return "item_name_missing"
        max_score = item.get("max")
        if isinstance(max_score, (int, float)) and not isinstance(max_score, bool):
            if not math.isfinite(max_score) or max_score < 0:
                return "item_max_invalid"
            has_numeric_max = True
            continue
        if not (
            max_score is None
            and item.get("score_mode") == "manual"
            and item.get("tag") in _MANUAL_NULL_TAGS
        ):
            return "item_max_invalid"
    return None if has_numeric_max else "no_numeric_max"


def criteria_usability_problem_message(problem: str) -> str:
    """把 :func:`criteria_usability_problem` 的机器码渲染成界面可读说明。

    机器码同时保留在文案里：运维按码 grep 日志，用户看中文，两者不必各存一份。
    """
    return f"{_CRITERIA_PROBLEM_TEXT.get(problem, '评分标准结构不可用')}（{problem}）"


def normalize_criteria_enums(criteria_obj: object) -> None:
    """In-place map criteria enum fields (method/item.tag/item.score_mode) to schema enums.

    模型（qwen/deepseek/opus）在枚举上可靠地漂移：method 写"综合评分法"、tag 写 source 短名
    "cross_bid"。代码侧确定性归一化比 prompt 约束可靠，避免单值之差让整份**结构合格**的 criteria
    被 schema 校验判 failed（criteria 价值在 items 评分项/扣分点，不在枚举标签）。映射不到的：
    method→其他、score_mode→manual、tag→强制人工枚举（保守，绝不冒充 scored 自动判分）。
    """
    if not isinstance(criteria_obj, dict):
        return
    method = criteria_obj.get("method")
    if isinstance(method, str):
        criteria_obj["method"] = _METHOD_ALIASES.get(method.strip(), "其他")
    items = criteria_obj.get("items")
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        tag = item.get("tag")
        if isinstance(tag, str) and tag not in _TAG_CANON and item.get("max") is not None:
            item["tag"] = _TAG_ALIASES.get(tag.strip(), _TAG_FALLBACK)
        score_mode = item.get("score_mode")
        if isinstance(score_mode, str) and score_mode not in _SCORE_MODES:
            item["score_mode"] = "manual"


# R7-#2：tender_info 仅 6 个已知 optional string 字段，作展示/回填用。
_TENDER_INFO_FIELDS = (
    "tender_no",
    "project_name",
    "tenderee",
    "control_price",
    "method",
    "funding_hint",
)


def sanitize_tender_info(obj: object) -> dict[str, str] | None:
    """R7-#2：净化 tender_info——保留 6 已知 string 字段（trim 非空），剥未知字段。

    替代旧的 jsonschema validate-or-drop：tender-info.schema 是 additionalProperties:false，
    模型只要多抽一个字段（如投标截止时间 / 项目地点）整份校验即抛错 → tender_info 被整体丢弃 →
    「区1 基本信息」空白（criteria 走独立 sanity 检查故区2 仍显，正是用户实测的不对称现象）。
    改为结构净化：合法字段照留、未知字段剥掉，杜绝因单个多余字段丢掉全部已抽取的项目元数据。

    Args:
        obj: tender-extract-info 返回的 tender_info 原始对象。

    Returns:
        仅含已知非空 string 字段的 dict；无任何可用字段或入参非 dict 时返回 None。
    """
    if not isinstance(obj, dict):
        return None
    cleaned: dict[str, str] = {}
    for key in _TENDER_INFO_FIELDS:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            cleaned[key] = value.strip()
    return cleaned or None


def _extraction_call_kwargs(tenant: str, *, case_path: str, draft_present: bool) -> dict[str, Any]:
    """整跑与修补轮共用的一套调用参数（分开写两份必然漂移，见 ``runner._call_kwargs`` 先例）。

    Args:
        tenant: 租户作用域。
        case_path: 上传落盘目录；底稿在场时兼作 ``case_root``，见下。
        draft_present: 底稿是否已由 ``context`` 注入。

    Returns:
        传给 ``run_command_json`` / ``run_agent_json`` 的 kwargs。
    """
    kwargs: dict[str, Any] = {
        "schema_name": None,
        "tenant": tenant,
        # 文本模式（与评标对齐）：大底稿下 SDK 结构化输出会 error_max_structured_output_retries。
        "structured": False,
        # 抽取产物不是投标人结论，不进 results 表。
        "archive_to_results": False,
    }
    if draft_present:
        # 底稿在场 → 锁工具面（评标侧 2026-08-17 已这么做，抽取侧当时漏了）：提示词写着"禁止
        # 调用任何工具"，模型照样 Glob + 逐个 Read，每一次都是一整轮重新预填充整份底稿。
        # ``case_root`` 必须一起传：锁面里唯一的 Bash 靠 build_options 的 ocr-page PreToolUse
        # 白名单闸约束，不绑 case_root 就等于给一个处理**攻击者可控 PDF** 的子进程配了裸 Bash。
        kwargs["tools"] = DRAFT_INJECTED_TOOLS
        kwargs["allowed_tools"] = DRAFT_INJECTED_TOOLS
        kwargs["case_root"] = Path(case_path)
    return kwargs


async def _run_extraction(
    case_path: str, context: str, tenant: str, *, draft_present: bool = True
) -> Any:
    """跑一次 criteria/tender_info 抽取，契约失败时优先 resume 修补而不是整跑。

    与 ``server.tender.runner`` 的重试环同构：失败带回了 CLI 会话 id 就只发一条常数级短指令
    让模型把 JSON 改对（底稿它已经看过），拿不到会话（失败发生在会话建立之前）才回落整跑。

    Args:
        case_path: 上传落盘目录，作命令参数。
        context: 已装配好的底稿 + 输出约束（修补轮**不重发**它）。
        tenant: 租户作用域。
        draft_present: 底稿是否真的在 ``context`` 里。为假时**不锁工具面**——那条降级路径下
            模型必须还能自己读文件。

    Returns:
        模型返回的 payload（结构合法性由调用方判定——那不是格式问题，修补轮救不了）。

    Raises:
        Exception: 最后一次 attempt 的失败原样上抛，由调用方落 criteria_status=failed。
    """
    last_error: Exception | None = None
    session_to_repair: str | None = None
    call_kwargs = _extraction_call_kwargs(
        tenant, case_path=case_path, draft_present=bool(draft_present)
    )
    for attempt in range(EXTRACT_CONTRACT_MAX_RETRY + 1):
        try:
            if session_to_repair is not None:
                payload, _meta = await run_agent_json(
                    build_extraction_repair_prompt(last_error),
                    resume_session_id=session_to_repair,
                    **call_kwargs,
                )
            else:
                payload, _meta = await run_command_json(
                    "tender-extract-info",
                    case_path,
                    context=context,
                    **call_kwargs,
                )
            return payload
        except Exception as exc:
            last_error = exc
            # 确定性失败（爆窗）重发必然同样失败，立即上抛（判定与评标侧同源）。
            if is_non_retryable(exc) or attempt >= EXTRACT_CONTRACT_MAX_RETRY:
                raise
            session_to_repair = repair_session_id(exc)
            logger.warning(
                "tender_extract_attempt_failed",
                extra={
                    "case_path": case_path,
                    "attempt": attempt + 1,
                    "retry_via": "contract_repair" if session_to_repair else "full_rerun",
                    "reason": str(exc)[:200],
                },
            )
    # 不可达：循环要么 return 要么在最后一次 attempt re-raise。
    raise AssertionError("unreachable: extraction retry loop exited without returning")


def _criteria_failure_message(exc: BaseException) -> str:
    """把一次抽取失败渲染成**带可执行动作**的界面说明（机器码留在括号里供 grep）。

    三档各有各的下一步，故不能归一成一句"识别失败"：结构不可用要用户换/补文件；超时要
    用户重传或运维放宽上限；其余（命令失败/返回结构异常）只能重试。

    Args:
        exc: 抽取路径上抛出的异常。

    Returns:
        落库到 ``criteria_error`` 的中文说明。
    """
    if isinstance(exc, CriteriaUnusableError):
        return criteria_usability_problem_message(exc.problem)
    if isinstance(exc, TimeoutError):
        return (
            f"评分标准解析超时（超过 {int(EXTRACT_TIMEOUT_SEC)}s 未返回）。"
            "请重新上传招标文件重试；若该文件确实很大或本机模型很慢，"
            "由运维调高 TENDER_EXTRACT_TIMEOUT_SEC 后再传。（extraction_timeout）"
        )
    return "评分标准抽取未完成（抽取命令失败或返回结构异常）（extraction_failed）"


async def extract_project_doc_info(
    project_id: str,
    case_path: str,
    ocr_text: str,
    tenant: str,
) -> None:
    """R1: Extract criteria + tender_info from OCR text after OCR completes.

    Calls the tender-extract-info command with the OCR text as context (契约失败会走
    :func:`_run_extraction` 的修补轮，不是一发定生死).  On success writes criteria_json,
    tender_info_json, and criteria_status=ready to tender_project_docs, then back-fills
    empty fields in tender_projects from tender_info (user-entered values are never
    overwritten).

    On ANY exception writes criteria_status=failed and leaves ocr_status=ready —
    extraction failure is non-fatal and must not affect the OCR-ready signal.

    Args:
        project_id: Tender project identifier.
        case_path: Directory path (used as the command argument for file context).
        ocr_text: The OCR text already extracted — injected as command context.
        tenant: Tenant scope for all DB writes.
    """
    extraction_text = ocr_text
    if _tender_slim_context_enabled():
        slim_text = build_preextract_tender_context(ocr_text, file_name=case_path)
        if slim_text is not None:
            extraction_text = slim_text
    context = (
        "=== 招标文件 OCR 底稿（确定性预处理，优先用此文本，无需再 Read 文件）===\n"
        + extraction_text
        + "\n\n"
        + _EXTRACTION_OUTPUT_GUARD
    )
    try:
        # 契约失败不再一发定生死：拿得到会话就 resume 修一轮（见 :func:`_run_extraction`）。
        # 硬超时包住整个重试环（形态同评标侧 ``worker._execute_inner`` 的 ``asyncio.wait_for``）：
        # 要封的是"这次抽取一共能占多久"，不是单次往返——评标入口在等它到终态。
        payload = await asyncio.wait_for(
            _run_extraction(case_path, context, tenant, draft_present=bool(extraction_text)),
            timeout=EXTRACT_TIMEOUT_SEC,
        )
        # payload must be a dict with a 'criteria' key to be considered valid
        if not isinstance(payload, dict) or "criteria" not in payload:
            raise ValueError(f"tender-extract-info returned unexpected payload shape: {payload!r}")

        criteria_obj = payload.get("criteria")
        tender_info_obj = payload.get("tender_info")

        # 承重校验（codex R1 P1）：criteria 会被评标 worker 当权威 S1 注入（"直接采用，勿重解析"）。
        # 残缺 criteria 注入会污染逐项 scoring/扣分 → 必须先按 criteria.schema 硬校验结构；不合格
        # 宁可 raise（→ criteria_status=failed，评标自行 S1 解析、区2 显"识别失败"），也不注入垃圾。
        # 归一化已知枚举漂移（method/tag/score_mode）清洁存储数据，再做承重结构 sanity 检查
        # （容忍零星叶子瑕疵，但无 items/缺名字/满分非数 → failed，不注入残缺 criteria 污染评分）。
        normalize_criteria_enums(criteria_obj)
        problem = criteria_usability_problem(criteria_obj)
        if problem is not None:
            raise CriteriaUnusableError(problem)
        # tender_info 仅作展示/回填，best-effort：净化保留已知字段（R7-#2），剥未知字段，不再因
        # additionalProperties:false 整对象丢弃 → 治"区1 基本信息没回传"（用户没手填、直接下一步）。
        tender_info_obj = sanitize_tender_info(tender_info_obj)

        criteria_json = json.dumps(criteria_obj, ensure_ascii=False) if criteria_obj else None
        tender_info_json = (
            json.dumps(tender_info_obj, ensure_ascii=False) if tender_info_obj else None
        )

        await asyncio.to_thread(
            update_project_doc_criteria_extracted,
            project_id,
            tenant,
            criteria_json=criteria_json,
            tender_info_json=tender_info_json,
            status="ready",
        )

        # Back-fill empty project metadata fields from tender_info (user values win).
        if isinstance(tender_info_obj, dict):
            fill_fields: dict[str, str | None] = {
                k: tender_info_obj.get(k)
                for k in ("tender_no", "tenderee", "control_price", "method")
            }
            await asyncio.to_thread(
                update_project_fields_if_empty,
                project_id,
                tenant,
                fill_fields,
            )
        logger.info(
            "tender_doc_info_extracted",
            extra={"project_id": project_id, "tenant": tenant or "default"},
        )
    except Exception as exc:
        # AC3：结构不合格有具名原因，其余异常（命令失败/payload 形状不对）归一到一条可读说明——
        # 两者都必须落库，界面才不会只剩一个"识别失败"。超时另立一档：它的处置动作与"抽取
        # 失败"完全不同（一个是重试/放宽上限，一个是换文件），混成一条等于没说。
        criteria_error = _criteria_failure_message(exc)
        logger.warning(
            "tender_doc_info_extraction_failed",
            extra={
                "project_id": project_id,
                "case_path": case_path,
                "criteria_error": criteria_error,
            },
            exc_info=True,
        )
        try:
            await asyncio.to_thread(
                update_project_doc_criteria_extracted,
                project_id,
                tenant,
                criteria_error=criteria_error,
                criteria_json=None,
                tender_info_json=None,
                status="failed",
            )
        except Exception:
            logger.debug("failed to write criteria_status=failed", exc_info=True)


async def run_project_doc_ocr(
    project_id: str,
    case_path: str,
    *,
    tenant: str,
    purpose: str | None = None,
    run_info_extraction: bool = True,
) -> None:
    """Background OCR coroutine for a tender project doc upload (P1-2/P1-3).

    Runs prewarm_and_report via run_prewarm_with_heartbeat (心跳 → 上传并发闸 → 命名池)。
    On success AND valid text writes ocr_status=ready; on any exception or error
    text writes ocr_status=failed (P1-3 — ensures read layer never sees stale ready).

    R1 extension: after a successful OCR write, sets criteria_status=running and
    immediately awaits extract_project_doc_info.  Extraction failure is non-fatal
    (criteria_status=failed) and never touches ocr_status=ready.

    Always writes tenant-scoped (P2).

    Args:
        project_id: Tender project identifier.
        case_path: Directory containing uploaded tender files.
        tenant: Tenant scope forwarded to update_project_doc_ocr.
        purpose: OCR engine purpose hint.
        run_info_extraction: 是否在 OCR 成功后抽取 criteria/tender_info。评标入口的补底稿重跑
            （H3 KD2）传 False——那是一次 30-60s 的模型往返，与"补回缺失页"无关。
    """
    # OCR 与抽取分两段：上传并发闸只圈住 OCR 计算本身（在 run_prewarm_with_heartbeat 内取名额，
    # 心跳早于排队起跑，review F2），抽取是模型调用必须在闸外——否则一次 criteria 抽取
    # （~30-60s 模型往返）会占住一个 OCR 名额，拖慢同项目投标文件的 OCR → 拖慢 isOcrReady →
    # 拖慢「开始分析」（违背 R1「不阻塞开始分析」）。状态写库同理不占名额。
    ocr_text: str | None = None
    try:
        text, report = await run_prewarm_with_heartbeat(
            prewarm_and_report,
            case_path,
            purpose=purpose,
            touch=lambda: touch_project_doc_ocr(project_id, tenant=tenant),
        )
        # P1-3: 底稿完全不可用（全失败/空目录）→ 走 failed 分支，读层绝不能看到 stale ready。
        if report.status == "failed":
            raise ValueError(f"OCR returned error/empty text: {text[:100]!r}")
        # 仅 OCR 写入在此 try（决定 ocr_status）。criteria_status=running 写移出（F1：否则其
        # 失败会触发下面 except 把已写好的 ocr_status 误覆写成 failed）。
        # H3 KD2：degraded/partial 如实落库（此前一律写 ready → 低质底稿永久固化）。
        await asyncio.to_thread(
            update_project_doc_ocr,
            project_id,
            tenant=tenant,
            ocr_text=text,
            ocr_clarity=None,
            status=report.status,
            failed_files=list(report.problem_files),  # 失败 + 降级合并落库（F6）
        )
        ocr_text = text
    except Exception:
        logger.warning(
            "tender_project_doc_ocr_failed",
            extra={"project_id": project_id, "case_path": case_path},
            exc_info=True,
        )
        try:
            await asyncio.to_thread(
                update_project_doc_ocr,
                project_id,
                tenant=tenant,
                ocr_text=None,
                ocr_clarity=None,
                status="failed",
            )
        except Exception:
            logger.debug("failed to write project_doc ocr failed status", exc_info=True)
        # F2：OCR 失败也置 criteria_status=failed，否则它停在 pending，前端 tenderDocInfo 轮询
        # （只在 ready/failed 停）会对该项目无限轮询。
        try:
            await asyncio.to_thread(
                update_project_doc_criteria_extracted,
                project_id,
                tenant,
                criteria_json=None,
                tender_info_json=None,
                status="failed",
            )
        except Exception:
            logger.debug("failed to set criteria_status=failed on ocr failure", exc_info=True)

    # 闸外：抽取（模型调用）不占 OCR 名额。OCR 成功且调用方要抽取才抽。
    if ocr_text is not None and run_info_extraction:
        # OCR ready 即解锁开始分析；置 criteria_status=running（独立 try，F1：失败只记日志，绝不
        # 触发 OCR failed 路径）。随后抽取在末尾置 ready/failed，故 running 写失败也无碍最终状态。
        try:
            await asyncio.to_thread(
                update_project_doc_criteria_extracted,
                project_id,
                tenant,
                criteria_json=None,
                tender_info_json=None,
                status="running",
            )
        except Exception:
            logger.debug("failed to set criteria_status=running", exc_info=True)
        await extract_project_doc_info(project_id, case_path, ocr_text, tenant)


async def run_bid_doc_ocr(
    project_id: str,
    bid_id: str,
    case_path: str,
    *,
    tenant: str,
    purpose: str | None = None,
) -> None:
    """Background OCR coroutine for a bid doc upload (P1-2/P1-3).

    Mirrors run_project_doc_ocr for tender_bid_docs. Runs under semaphore (P1-2).
    Error text or exception → writes ocr_status=failed (P1-3).
    All writes are tenant-scoped (P2).

    Args:
        project_id: Parent tender project identifier.
        bid_id: Bid document identifier.
        case_path: Directory containing uploaded bid files.
        tenant: Tenant scope forwarded to update_bid_doc_ocr.
        purpose: OCR engine purpose hint.
    """
    try:
        text, report = await run_prewarm_with_heartbeat(
            prewarm_and_report,
            case_path,
            purpose=purpose,
            touch=lambda: touch_bid_doc_ocr(project_id, bid_id, tenant=tenant),
        )
        if report.status == "failed":
            raise ValueError(f"OCR returned error/empty text: {text[:100]!r}")
        await asyncio.to_thread(
            update_bid_doc_ocr,
            project_id,
            bid_id,
            tenant=tenant,
            ocr_text=text,
            status=report.status,
            failed_files=list(report.problem_files),  # 失败 + 降级合并落库（F6）
        )
    except Exception:
        logger.warning(
            "tender_bid_doc_ocr_failed",
            extra={"project_id": project_id, "bid_id": bid_id, "case_path": case_path},
            exc_info=True,
        )
        try:
            await asyncio.to_thread(
                update_bid_doc_ocr,
                project_id,
                bid_id,
                tenant=tenant,
                ocr_text=None,
                status="failed",
            )
        except Exception:
            logger.debug("failed to write bid_doc ocr failed status", exc_info=True)


def start_project_doc_ocr_task(
    project_id: str, case_path: str, *, tenant: str = "", purpose: str | None = None
) -> None:
    """Fire-and-forget: schedule background OCR for a project doc and track the task (P1-2)."""
    task = asyncio.create_task(
        run_project_doc_ocr(project_id, case_path, tenant=tenant, purpose=purpose)
    )
    track_upload_ocr_task(task, project_id)


def start_bid_doc_ocr_task(
    project_id: str, bid_id: str, case_path: str, *, tenant: str = "", purpose: str | None = None
) -> None:
    """Fire-and-forget: schedule background OCR for a bid doc and track the task (P1-2)."""
    task = asyncio.create_task(
        run_bid_doc_ocr(project_id, bid_id, case_path, tenant=tenant, purpose=purpose)
    )
    track_upload_ocr_task(task, project_id)
