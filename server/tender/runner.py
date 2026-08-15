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

**419 行拆分（2026-08-14，纯移动）**：本模块只留主流程——底稿获取（doc 层复用 / inline OCR 回落）、
注入前的字节预算闸、模型调用与契约重试。搬走的两块：底稿层决策与完整性告警 →
``server/tender/doc_context.py``；criteria 注入块与结论 ``criteria_ref`` 回执 →
``server/tender/criteria_context.py``。整函数搬家 + import 接线，函数体/命名/日志文案/注释语义
逐字未改。预算闸**未**搬：``tender_context_truncated`` 是按 logger 名 ``server.tender.runner``
可检索的运维日志，挪家会改记录里的 logger 名（那不是纯移动）。
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from server.common.command_adapter import run_command_json
from server.common.contract import is_non_retryable
from server.ocr.pipeline import ocr_preprocess_block
from server.platform.config import get_tender_eval_settings
from server.stores.session_store import new_conversation_id
from server.tender.compare_input import resolve_project_criteria
from server.tender.context_budget import bound_draft_by_content, derive_default_max_bytes
from server.tender.context_slim import bound_tender_context
from server.tender.criteria_context import _criteria_context_block, _stamp_criteria_ref
from server.tender.doc_context import (
    _inject_ocr_warnings,
    _ocr_warning_block,
    _resolve_doc_layer,
)

# 拆分后仍从本模块 re-export（tests/test_tender_doc_ocr_status.py 与
# tests/test_tender_prewarm_oracle.py 按 ``runner._ocr_integrity_warnings`` 调用）。
from server.tender.doc_context import _ocr_integrity_warnings as _ocr_integrity_warnings
from server.tender.injection_budget import describe_context_rejection, estimate_tokens
from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME

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

# 底稿注入的**无条件**字节上限（2026-08-14 生产事故）：云 OCR 写超时 → 降级 inline_ocr 把整个
# case 目录的 OCR 全文注入，无任何长度上限 → 内网 DeepSeek Flash "Prompt is too long"，整单无
# 结论。已有的 context_slim.bound_tender_context 是**配置态**闸（部署未声明模型窗口/输出预算时
# 整体不生效，事故当天正是这个状态），故这里再加一道兜底。
#
# 默认值不再硬编码常量（2026-08-14 第二次事故 Bug A）：旧默认 64,000 B 是按"最小窗口模型
# 64K token"的错误前提反推的，而实际部署 MODEL_CONTEXT_WINDOW=1048576，64 KB 只占窗口 2%，
# 把 103 KB 的底稿截成 64 KB、砍掉评标办法整章。现改为从模型窗口推导，见
# ``context_budget.derive_default_max_bytes``；显式设 ``TENDER_CONTEXT_MAX_BYTES`` 仍以其为准。

# 截断标记：让模型**看见**底稿被截，从而对被截材料走证据缺失规则，而不是当成"材料未提供"判 0。
# 标记本身（~160 B）附加在上限之外，故意保证"被截了"这件事一定进上下文。
_TRUNCATION_NOTICE = (
    "\n【底稿超出上下文预算，已截断：按内容优先保留（评标办法/评分标准/资格审查等关键章节优先），"
    "共保留 {kept} 字节 / 原始 {total} 字节；被省略区段在正文中以 ...[已省略…]... 标出，"
    "涉及被截材料的评分项按证据缺失处理】\n"
)


def _context_max_bytes(model: str | None = None) -> int:
    """Return the OCR draft byte budget (reads ``TENDER_CONTEXT_MAX_BYTES`` live)."""
    configured = os.getenv("TENDER_CONTEXT_MAX_BYTES")
    if configured:
        return int(configured)
    return derive_default_max_bytes(model)


def _bound_ocr_block(ocr_block: str, *, request_id: str, model: str | None = None) -> str:
    """Fit the OCR draft into the byte budget, keeping review-critical sections first.

    Args:
        ocr_block: 待注入的 OCR/直读底稿全文（doc 层复用或 inline OCR 均经此）。
        request_id: 本次评标请求 id，写进截断告警日志供回溯。
        model: 本次评标实际使用的模型名，用于按其窗口推导默认预算。

    Returns:
        未超限时原样返回；超限时返回 ``内容优先截断后的底稿 + 截断标记``。
    """
    limit = _context_max_bytes(model)
    raw = ocr_block.encode("utf-8")
    if len(raw) <= limit:
        return ocr_block
    kept = bound_draft_by_content(ocr_block, limit_bytes=limit)
    kept_bytes = len(kept.encode("utf-8"))
    logger.warning(
        "tender_context_truncated",
        extra={
            "request_id": request_id,
            "original_bytes": len(raw),
            "kept_bytes": kept_bytes,
            "limit_bytes": limit,
        },
    )
    return kept + _TRUNCATION_NOTICE.format(kept=kept_bytes, total=len(raw))


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
    resolved_model = (model or get_tender_eval_settings().model or "").strip()
    # P2 评标读层：优先取 tender_doc_store 已 ready 的 OCR 底稿（上传时预热，秒过）。
    # P1-1 修复：只读招标层 + 当前家(bid_id)投标层，不混全部投标。
    # 未 ready/缺失/无 bid_id/异常 → 回落原串行 ocr_preprocess_block（兜底，不破现有路径）。
    # 无 project_id（legacy 散单）或开关关闭 → 直接回落。
    doc_layer_text: str | None = None
    ocr_warnings: list[dict[str, object]] = []
    if _tender_read_doc_layer_enabled() and project_id:
        doc_layer_text, ocr_warnings = await _resolve_doc_layer(project_id, bid_id, tenant)

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

    # 预算闸：两条来源（doc_layer_reuse / inline_ocr 降级）都过闸——预热底稿理论上同样可能超大。
    # 闸放在 tender 调用侧而非 server/ocr/：OCR 产物本身该完整，只有"注入给模型"这一步有预算。
    if ocr_block:
        ocr_block = _bound_ocr_block(
            ocr_block, request_id=request_id, model=resolved_model or None
        )

    context = (
        f"=== OCR/直读底稿（确定性预处理，优先用此文本，无需再 Read 文件）===\n{ocr_block}"
        if ocr_block
        else None
    )

    # R1 criteria 注入（治②）：若招标层已有权威 criteria（上传时预抽 / 首家评标 backfill），
    # 连同 KD1 的 criteria_version 一并追加到 context，指示模型 S1 直接采用、无需重解析。
    # 降级安全：无 criteria/project_id/异常 → 不注入（version 留 None → 结论记 self_parsed）。
    injected_criteria_version: str | None = None
    if project_id and context:
        try:
            # F4：同步 SQLite 读经 to_thread 移出事件循环（对齐 _load_doc_layer_context / round4 F4）。
            project_criteria, injected_criteria_version = await asyncio.to_thread(
                resolve_project_criteria, project_id, tenant
            )
            if project_criteria is not None:
                context = context + _criteria_context_block(
                    project_criteria, injected_criteria_version
                )
        except Exception:
            injected_criteria_version = None
            logger.debug("criteria context injection failed, continuing without", exc_info=True)

    # H3 KD2：底稿降级/缺失对模型显式可见（不静默）——与结论里的 ocr_warnings 同源同文案。
    if context and ocr_warnings:
        context = context + _ocr_warning_block(ocr_warnings)

    bounded_context = bound_tender_context(context, model=resolved_model or None) if context else None
    if bounded_context is not None:
        context = bounded_context

    # D1 T3：per-call model 覆盖——显式参数优先于 TENDER_EVAL_MODEL env，两者皆空则不传
    # model kwargs（零行为变更）。生产 tender_worker 调用从不传 model 也从不设该 env，
    # 故这条兜底路径只在 eval CLI / 部署机手动调参场景生效。
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
            # H3 KD2：底稿降级/缺失强制随结论落盘，人工复核时不必回翻日志才知道底稿有洞。
            _inject_ocr_warnings(payload, ocr_warnings)
            _stamp_criteria_ref(payload, injected_criteria_version)
            return payload, meta
        except Exception as exc:
            last_error = exc
            # 确定性失败立即上抛：重发同一 prompt 结果必然相同（2026-08-14 事故）。判定上提到
            # server.common.contract，与 audit 的两处同型重试环共用（2026-08-14 后续）。
            if is_non_retryable(exc):
                # AC6：爆窗是一次性硬失败（contract.py 已列不可重试），这条日志就是运维唯一
                # 线索——必须带上"去哪复标定"，否则 TENDER_EFFECTIVE_CONTEXT_TOKENS 会变成
                # 第五个被凭猜调的错数字。
                logger.error(
                    "tender_context_rejected",
                    extra={
                        "request_id": request_id,
                        "recalibration_hint": describe_context_rejection(
                            observed_tokens=estimate_tokens(context or "")
                        ),
                    },
                )
                raise
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
