"""Tender evaluation core: preload OCR/read-layer context, then run ``/tender-evaluate``.

下沉自 ``server/routes/tender_worker.py``（D1 T2，design round1 F1 + round2 F5 方案 i）：
评标核心 ``_run_evaluation``（含 doc-layer 助手）与 ``routes/audit_worker.py → server/audit/runner.py``
同构下沉，公开名 ``run_tender_evaluation``；``routes/tender_worker.py`` 留调度壳（准入闸/信号量/
超时/任务状态机），import 本模块。

**OCR 依赖处置（方案 i，2026-07-15 拍板）**：ocr 从 tender/audit 的平级 sibling 降为 feature 域
之下的服务层（audit_worker / tender_worker / tender_doc_pipeline 三处已按服务消费）。本模块内嵌
``ocr_preprocess_block`` 调用因此合法（tender→ocr），``TENDER_OCR_PURPOSE`` 常量挪家至此（原定义在
``routes/tender_doc_pipeline.py``，该模块现改为从本模块 import）。``test_layering.py`` 守卫改
**单向**：允许 tender/audit→ocr，禁止 ocr→tender/audit。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

from server.common.command_adapter import run_command_json
from server.ocr.pipeline import ocr_preprocess_block
from server.tender.context_slim import build_slim_tender_context
from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME
from server.platform.config import get_tender_eval_settings
from server.stores.session_store import new_conversation_id
from server.stores.tender_doc_store import get_bid_doc, get_project_doc

logger = logging.getLogger(__name__)

# 评标场景 OCR 目的（治"OCR 无目的性"）：让 OCR 引擎在通用文本提取之外，重点完整、结构化地还原
# 评分标准/评标办法/扣分细则/废标条款等【表格】——评分表是评标命脉。tender_doc_pipeline.py（上传
# 预热）与本模块（评标 OCR）均从此处 import，消除原先两处重复（S3 消重，D1 T2 挪家至此）。
TENDER_OCR_PURPOSE = (
    "本批为招投标评标材料。请在完整提取文本之外，特别完整、结构化地还原"
    "【评分标准/评标办法/评分细则/扣分细则/加分项/废标与资格条款】等表格："
    "保留表格的行列结构与每一行的分值数字，不要合并或省略任何评分/扣分行。"
)


# P2 评标读层开关：TENDER_READ_DOC_LAYER=1 (默认) 先读 tender_doc_store;
# =0 回落原串行 ocr_preprocess_block（兜底，不破现有路径）。
# 注意：每次调用时动态读 env，支持运行时灰度切换 + 测试 monkeypatch。
def _tender_read_doc_layer_enabled() -> bool:
    """Return True when the P2 doc layer is active (reads TENDER_READ_DOC_LAYER env live)."""
    return os.getenv("TENDER_READ_DOC_LAYER", "1").lower() in {"1", "true", "yes"}


def _stream_partial_enabled() -> bool:
    """遗留①：是否开 include_partial_messages 让端点逐字吐 partial（真·思考流式）。默认开；
    端点不支持流式则无害（无 partial 退回完整消息 + 兜底 final-flush）。TENDER_STREAM_PARTIAL=0 关。"""
    return os.getenv("TENDER_STREAM_PARTIAL", "1").lower() in {"1", "true", "yes"}


# 契约失败重试次数。tender 输出大而复杂（14+项 scoring），deepseek 文本模式偶发不出 JSON /
# 写坏 JSON（间歇性，同标重跑可成功）。audit 早有重试环，tender 此前缺失 → 单次 flaky 即失败。
# 默认 2（共 3 次尝试，比 audit 的 1 更宽，因 tender 输出更易 flaky）；OCR 预处理只做一次不重跑。
TENDER_CONTRACT_MAX_RETRY = int(os.getenv("TENDER_CONTRACT_MAX_RETRY", "2"))

# 评标推理强度（extended thinking）：评标是高难合规判断，默认 xhigh 压 deepseek 随机性（per-call，
# 不走全局 build_options 默认 → 不拖慢 audit，codex r4 P1）；env 可调或设非法值走端点默认。
_TENDER_EFFORT = os.getenv("TENDER_REASONING_EFFORT", "xhigh")

# R6-R2 复用预热 OCR：等招标层+当前家投标层 OCR 就绪的上限/间隔。标书大(百页)OCR 可达数分钟，
# 给足窗口；env 可调。用迭代次数计时（不依赖 wall-clock 时间函数）。
_DOC_LAYER_WAIT_SEC = float(os.getenv("TENDER_DOC_LAYER_WAIT_SEC", "360"))
_DOC_LAYER_POLL_SEC = 3.0


def _load_doc_layer_context(project_id: str, bid_id: str | None, tenant: str) -> str | None:
    """P2 评标读层：从 tender_doc_store 取已预热的 OCR 底稿并拼为上下文字符串。

    **P1-1 修复**：只加载招标层 + **当前被评标这一家**的投标层（by bid_id）。
    旧实现拼接所有投标文件 → 多家材料污染同一 context，错乱 claim_id/scoring。
    无 bid_id（legacy 散单/无法定位当前家）→ 返回 None 回落串行 OCR（天然正确，
    case_path 就是该家散单目录）。招标层或当前家 not-ready/failed/缺失 → 返回 None。
    任何异常 → 静默返回 None，**绝不拖垮评标**。

    Args:
        project_id: 招标项目 ID。
        bid_id: 当前被评标的投标文件 ID；为 None 时跳过读层（安全回落）。
        tenant: 租户作用域。

    Returns:
        "招标底稿 + 当前家投标底稿"组合字符串，或 None 触发回落。
    """
    # 无 bid_id → 无法精确定位当前家，绝不混入其他家材料，直接回落
    if not bid_id:
        return None
    try:
        project_doc = get_project_doc(project_id, tenant)
        if project_doc is None or project_doc.get("ocr_status") != "ready":
            return None
        bid = get_bid_doc(project_id, bid_id, tenant)
        if bid is None or bid.get("ocr_status") != "ready" or not bid.get("ocr_text"):
            return None
        bidder = bid.get("bidder_name") or bid["bid_id"]
        parts: list[str] = [
            f"=== 招标文件底稿 ===\n{project_doc['ocr_text']}",
            f"=== 投标文件（{bidder}）底稿 ===\n{bid['ocr_text']}",
        ]
        return "\n\n".join(parts)
    except Exception:
        logger.warning("_load_doc_layer_context failed, falling back", exc_info=True)
        return None


def _tender_slim_context_enabled() -> bool:
    """Return True when D8 criteria-driven tender context slimming is enabled."""
    return os.getenv("TENDER_SLIM_CONTEXT", "0").lower() in {"1", "true", "yes"}


def _parse_stored_criteria(raw: str | None) -> dict | None:
    """Parse stored criteria JSON for the D8 slimming path, tolerating missing or invalid data."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _load_doc_layer_context_slim(project_id: str, bid_id: str | None, tenant: str) -> str | None:
    """Load doc-layer context with an optional criteria-driven tender-document reduction.

    This preserves the full tender text when criteria are unavailable or slimming cannot safely
    produce a complete result; the current bidder's document is always passed through unchanged.
    """
    if not bid_id:
        return None
    try:
        project_doc = get_project_doc(project_id, tenant)
        if project_doc is None or project_doc.get("ocr_status") != "ready":
            return None
        bid = get_bid_doc(project_id, bid_id, tenant)
        if bid is None or bid.get("ocr_status") != "ready" or not bid.get("ocr_text"):
            return None
        bidder = bid.get("bidder_name") or bid["bid_id"]
        tender_text = project_doc["ocr_text"]
        criteria = _parse_stored_criteria(project_doc.get("criteria"))
        if criteria is not None:
            slim_text = build_slim_tender_context(tender_text, criteria, file_name=project_id)
            if slim_text is not None:
                tender_text = slim_text
        parts: list[str] = [
            f"=== 招标文件底稿 ===\n{tender_text}",
            f"=== 投标文件（{bidder}）底稿 ===\n{bid['ocr_text']}",
        ]
        return "\n\n".join(parts)
    except Exception:
        logger.warning("_load_doc_layer_context_slim failed, falling back", exc_info=True)
        return None


async def _wait_doc_layer_ready(project_id: str, bid_id: str, tenant: str) -> None:
    """短轮询等招标层 + 当前家投标层 OCR 都到终态（ready/failed），供评标复用预热 OCR、免重 OCR。

    用户「上传即 OCR」后可能在 OCR 未完就点开始分析（R1 解阻塞）→ 评标提交时预热 OCR 还在跑。本函数
    等它跑完（ready→复用 / failed→由 _load_doc_layer_context 回落 inline）。缺记录/超时/异常 → 直接返回
    （绝不死等、绝不拖垮评标）。
    """
    max_polls = max(1, int(_DOC_LAYER_WAIT_SEC / _DOC_LAYER_POLL_SEC))
    terminal = {"ready", "failed"}
    for _ in range(max_polls):
        try:
            proj = await asyncio.to_thread(get_project_doc, project_id, tenant)
            bid = await asyncio.to_thread(get_bid_doc, project_id, bid_id, tenant)
        except Exception:
            return  # 读失败 → 不等，交后续逻辑回落
        if proj is None or bid is None:
            return  # 无预热记录（散单/旧路径）→ 不等
        if proj.get("ocr_status") in terminal and bid.get("ocr_status") in terminal:
            return  # 都终态 → 可判复用/回落
        await asyncio.sleep(_DOC_LAYER_POLL_SEC)


async def run_tender_evaluation(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    project_id: str | None = None,
    bid_id: str | None = None,
    on_progress: Callable[[str], None] | None = None,
    case_root: Path | None = None,
    model: str | None = None,
) -> tuple[Any, Any]:
    """Run one tender evaluation with OCR/read-layer context preloaded + criteria injection.

    ``model``（D1 T2 --model CLI + T3 env 覆盖）：per-call 模型覆盖，供
    ``server.tender.eval`` CLI 的 ``--model`` 与生产 tender_worker 共用同一条路径。显式参数
    优先；未传时读 ``TENDER_EVAL_MODEL`` env（``get_tender_eval_settings``，仿 ``_TENDER_EFFORT``
    先例，只读不缓存）；两者皆空则不覆盖，走全局默认——生产 tender_worker 从不设
    ``TENDER_EVAL_MODEL``，故这条 env 兜底路径零行为变更。
    """
    # P2 评标读层：优先取 tender_doc_store 已 ready 的 OCR 底稿（上传时预热，秒过）。
    # P1-1 修复：只读招标层 + 当前家(bid_id)投标层，不混全部投标。
    # 未 ready/缺失/无 bid_id/异常 → 回落原串行 ocr_preprocess_block（兜底，不破现有路径）。
    # 无 project_id（legacy 散单）或开关关闭 → 直接回落。
    doc_layer_text: str | None = None
    if _tender_read_doc_layer_enabled() and project_id:
        # R6-R2：复用预热 OCR——用户「上传即 OCR」后可能在 OCR 未完就点开始分析(R1 解阻塞)。此时给了
        # prewarm bid_id 但 doc 层尚 running → 先短轮询等其 ready(预热在跑)，再复用，避免重 OCR 跑两遍
        # ~5min。兜底超时/失败 → 回落 inline(不死等)。
        if bid_id:
            await _wait_doc_layer_ready(project_id, bid_id, tenant)
        loader = (
            _load_doc_layer_context_slim
            if _tender_slim_context_enabled()
            else (_load_doc_layer_context)
        )
        doc_layer_text = await asyncio.to_thread(loader, project_id, bid_id, tenant)

    if doc_layer_text is not None:
        ocr_block: str | None = doc_layer_text
        # R6-R2 可观测：评标复用了预热 OCR（未重 OCR）。
        logger.info(
            "tender_ocr_source",
            extra={"request_id": request_id, "source": "doc_layer_reuse", "bid_id": bid_id},
        )
    else:
        # P4 原串行 OCR 回落（pymupdf 直读 / 云 OCR）。
        logger.info(
            "tender_ocr_source",
            extra={"request_id": request_id, "source": "inline_ocr", "bid_id": bid_id},
        )
        ocr_block = await asyncio.to_thread(
            ocr_preprocess_block, directory_path, purpose=TENDER_OCR_PURPOSE
        )

    context = (
        f"=== OCR/直读底稿（确定性预处理，优先用此文本，无需再 Read 文件）===\n{ocr_block}"
        if ocr_block
        else None
    )

    # R1 criteria 注入（治②）：若招标层已有 criteria（上传时预抽），追加到 context，
    # 指示模型 S1 直接采用、无需重解析。降级安全：无 criteria/project_id/异常 → 不注入。
    if project_id and context:
        try:
            import json as _json

            # F4：同步 SQLite 读经 to_thread 移出事件循环（对齐 _load_doc_layer_context / round4 F4）。
            project_doc = await asyncio.to_thread(get_project_doc, project_id, tenant)
            stored_criteria = (project_doc or {}).get("criteria")
            if stored_criteria:
                # Ensure Chinese characters are readable in the injected context block.
                try:
                    parsed = _json.loads(stored_criteria)
                    readable = _json.dumps(parsed, ensure_ascii=False, indent=2)
                except (ValueError, TypeError):
                    readable = stored_criteria
                criteria_block = (
                    "\n\n=== 已解析评分标准 criteria（S1 直接采用，勿重新解析）===\n" + readable
                )
                context = context + criteria_block
        except Exception:
            logger.debug("criteria context injection failed, continuing without", exc_info=True)

    # D1 T3：per-call model 覆盖——显式参数优先于 TENDER_EVAL_MODEL env，两者皆空则不传
    # model kwargs（零行为变更）。生产 tender_worker 调用从不传 model 也从不设该 env，
    # 故这条兜底路径只在 eval CLI / 部署机手动调参场景生效。
    resolved_model = (model or get_tender_eval_settings().model or "").strip()
    model_kwargs: dict[str, str] = {"model": resolved_model} if resolved_model else {}
    # 有意的安全设计（D11 TA4）：case_root 恒绑定本案目录，因此受 ocr-page
    # PreToolUse hook 约束的 Bash 对每次评标都可用——任一评标都可能需要低清页重识别。
    # hook 是唯一闸；这是显式设计，不是 case_root 默认回填带来的副作用。
    evaluation_case_root = case_root if case_root is not None else Path(directory_path)

    # 契约失败重试（对齐 audit runner）：deepseek 文本模式偶发不出 JSON / 写坏 JSON，重跑可成功。
    # OCR 预处理在循环外只做一次（慢且确定性），仅重试模型调用。
    last_error: Exception | None = None
    for attempt in range(TENDER_CONTRACT_MAX_RETRY + 1):
        try:
            payload, meta = await run_command_json(
                "tender-evaluate",
                directory_path,
                schema_name=TENDER_OUTPUT_SCHEMA_NAME,
                request_id=request_id,
                tenant=tenant,
                project_id=project_id,  # 显式透传 → 结论落 results.project_id（codex P1.3）
                bid_id=bid_id,  # X2：显式透传 → 结论落 results.bid_id（bids 层手填回填 join key）
                conversation_id=new_conversation_id(),
                context=context,
                # R1 evidence-resolution：透传**原始底稿** ocr_block（带 ### 文件:/【第N页】 锚点）
                # 给结论校验闸做出处回查。**传 ocr_block 而非 context**——context 尾部已追加 criteria
                # 注入块 + OCR 头注释，会干扰 tier/page 解析（design critic blind-spot C）。
                evidence_source=ocr_block,
                case_root=evaluation_case_root,
                on_progress=on_progress,  # 思考流式：agent 文本片段实时回调给 worker
                effort=_TENDER_EFFORT,  # 评标 per-call 扩展思考（不全局默认，避免拖慢 audit）
                # 遗留①：开 include_partial_messages → 端点逐字吐 StreamEvent partial，on_progress
                # 实时收增量(真·流式)。端点不支持流式则无 partial、退回完整 AssistantMessage + 兜底
                # final-flush，行为不退化。env TENDER_STREAM_PARTIAL=0 可关。
                include_partial_messages=_stream_partial_enabled(),
                # 文本模式（与 audit 对齐）：大底稿(百页标书)下 SDK 结构化输出会 error_max_structured_
                # output_retries；文本模式由服务端抽 JSON，对大输入更稳。配合命令里的 JSON 输出硬化。
                structured=False,
                **model_kwargs,
            )
            # D1 M1（返工）：契约重试次数是运维基线指标（design 评分维度表「运维指标」，
            # S7 配套问题②），供 eval 回归闸捕捉「D8 底稿瘦身导致 JSON 更易写坏→重试变多」
            # 这类回归信号。成功时的 attempt（从 0 计数）即实际重试了几次；AgentRunMeta 已
            # 声明 retry_count 尾部字段（带默认值 0），slots 下此赋值合法。
            meta.retry_count = attempt
            return payload, meta
        except Exception as exc:
            last_error = exc
            if attempt >= TENDER_CONTRACT_MAX_RETRY:
                raise
            logger.warning(
                "tender attempt failed (%s, %d/%d), retrying: %s",
                type(exc).__name__,
                attempt + 1,
                TENDER_CONTRACT_MAX_RETRY + 1,
                exc,
                extra={"request_id": request_id, "tenant": tenant or "default"},
            )
    # 不可达：循环要么 return 要么在最后一次 attempt re-raise。
    raise AssertionError("unreachable: tender retry loop exited without returning") from last_error
