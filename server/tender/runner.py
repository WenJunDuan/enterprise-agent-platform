"""Tender evaluation core: preload OCR/read-layer context, then run ``/tender-evaluate``.

与 ``server/audit/runner.py`` 同构：评标核心在此，``routes/tender_worker.py`` 只留调度壳
（准入闸 / 信号量 / 超时 / 任务状态机）并 import 本模块。

**OCR 依赖处置**：ocr 是 feature 域之下的服务层，故本模块内嵌 ``ocr_preprocess_block``
合法（tender→ocr）；``test_layering.py`` 守卫是**单向**的，禁止 ocr→tender/audit。

**边界**：本模块只留主流程——底稿获取（doc 层复用 / inline OCR 回落）、上下文装配、模型调用
与契约重试。底稿层决策与完整性告警在 ``doc_context``，criteria 注入块与结论 ``criteria_ref``
回执在 ``criteria_context``，法规/记忆注入块在 ``rules_context``，字节预算闸的纯计算在
``draft_budget``，契约修补轮的文案在 ``contract_repair``。``tender_context_truncated`` 这条
告警刻意留在本模块：它按 logger 名 ``server.tender.runner`` 可检索，挪家会改记录里的 logger 名。
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
from server.common.json_bridge import run_agent_json
from server.ocr.pipeline import ocr_preprocess_block
from server.platform.config import get_tender_eval_settings
from server.stores.session_store import new_conversation_id
from server.tender.compare_input import resolve_project_criteria
from server.tender.context_slim import bound_tender_context
from server.tender.contract_repair import build_repair_prompt, repair_session_id
from server.tender.criteria_context import _criteria_context_block, _stamp_criteria_ref
from server.tender.doc_context import (
    _inject_ocr_warnings,
    _ocr_warning_block,
    _resolve_doc_layer,
)

# re-export：两处测试按 ``runner._ocr_integrity_warnings`` 调用（拆分前的公开位置）。
from server.tender.doc_context import _ocr_integrity_warnings as _ocr_integrity_warnings
from server.tender.draft_budget import (
    TRUNCATION_NOTICE,
    TruncatedDraft,
    bound_draft,
    context_max_bytes,
    truncation_warning,
)
from server.tender.evidence_context import build_manual_review_result
from server.tender.injection_budget import describe_context_rejection, estimate_tokens
from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME
from server.tender.rules_context import tender_rules_block

logger = logging.getLogger(__name__)

# 拆分前的公开位置：两处测试按 ``runner._TRUNCATION_NOTICE`` / ``runner._context_max_bytes``
# 调用（与 ``_ocr_integrity_warnings`` 同款保位）。用赋值而非 ``import as``——后者名字不同名，
# 会被 F401 当未用导入删掉。
_TRUNCATION_NOTICE = TRUNCATION_NOTICE
_context_max_bytes = context_max_bytes

# 评标场景 OCR 目的：让引擎在通用文本提取之外，重点完整、结构化地还原评分标准/评标办法/扣分
# 细则/废标条款等【表格】——评分表是评标命脉。上传预热（tender_doc_pipeline）与本模块共用此常量。
TENDER_OCR_PURPOSE = (
    "本批为招投标评标材料。请在完整提取文本之外，特别完整、结构化地还原"
    "【评分标准/评标办法/评分细则/扣分细则/加分项/废标与资格条款】等表格："
    "保留表格的行列结构与每一行的分值数字，不要合并或省略任何评分/扣分行。"
)


# 评标读层开关：=1(默认) 先读 tender_doc_store，=0 回落原串行 ocr_preprocess_block。
# 每次调用动态读 env，支持运行时灰度切换 + 测试 monkeypatch。
def _tender_read_doc_layer_enabled() -> bool:
    """Return True when the P2 doc layer is active (reads TENDER_READ_DOC_LAYER env live)."""
    return os.getenv("TENDER_READ_DOC_LAYER", "1").lower() in {"1", "true", "yes"}


def _stream_partial_enabled() -> bool:
    """遗留①：是否开 include_partial_messages 让端点逐字吐 partial（真·思考流式）。默认开；
    端点不支持流式则无害（无 partial 退回完整消息 + 兜底 final-flush）。TENDER_STREAM_PARTIAL=0 关。"""
    return os.getenv("TENDER_STREAM_PARTIAL", "1").lower() in {"1", "true", "yes"}


# 契约失败重试次数。tender 输出大而复杂（14+项 scoring），deepseek 文本模式偶发写坏 JSON
# （间歇性，同标重跑可成功）→ 默认 2（比 audit 的 1 更宽）；OCR 预处理只做一次不重跑。
TENDER_CONTRACT_MAX_RETRY = int(os.getenv("TENDER_CONTRACT_MAX_RETRY", "2"))

# 评标推理强度（extended thinking）：评标是高难合规判断，默认 xhigh 压 deepseek 随机性（per-call，
# 不走全局 build_options 默认 → 不拖慢 audit，codex r4 P1）；env 可调或设非法值走端点默认。
_TENDER_EFFORT = os.getenv("TENDER_REASONING_EFFORT", "xhigh")

# B（2026-08-17 延时治理）：底稿已注入时的工具面。`error_max_turns` 的根因是自相矛盾的指令
# ——注入头写"无需再 Read 文件"，S0 却让模型 Glob 列目录、后续再逐个 Read，每一次都是一整轮
# 重新预填充 ~83K token 底稿。提示词说服不了模型的部分由工具面兜底：底稿在场时子进程根本
# 不存在 Read/Glob/Grep/Task，**唯一例外是 Bash**——它受 build_options 的 ocr-page PreToolUse
# hook 约束，只放行按页重识别。**必须非空**：build_options 里 `defaults.get("tools") or
# _AGENT_TOOLS` 会把空清单悄悄还原成全量工具。
DRAFT_INJECTED_TOOLS = ["Bash"]


def _bound_ocr_block(
    ocr_block: str, *, request_id: str, model: str | None = None
) -> tuple[str, TruncatedDraft | None]:
    """Fit the OCR draft into the byte budget and log the truncation for ops.

    截断本身是纯计算（``draft_budget``）；这条 ``tender_context_truncated`` 告警刻意留在
    runner——它按 logger 名 ``server.tender.runner`` 可检索，挪家会改记录里的 logger 名。

    Args:
        ocr_block: 待注入的 OCR/直读底稿全文（doc 层复用或 inline OCR 均经此）。
        request_id: 本次评标请求 id，写进截断告警日志供回溯。
        model: 本次评标实际使用的模型名，用于按其窗口推导默认预算。

    Returns:
        ``(注入用底稿, 截断账目)``。未超限时账目为 ``None``、底稿原样返回；超限时返回
        ``内容优先截断后的底稿 + 截断标记`` 与字节账——账目**必须回传**，调用方据此产出
        用户可见 warning 并裁定本次评分是否还有权威性（2026-08-18 事故：账目只进日志）。
    """
    truncated = bound_draft(ocr_block, model=model)
    if truncated is None:
        return ocr_block, None
    logger.warning(
        "tender_context_truncated",
        extra={
            "request_id": request_id,
            "original_bytes": truncated.original_bytes,
            "kept_bytes": truncated.kept_bytes,
            "limit_bytes": truncated.limit_bytes,
        },
    )
    return truncated.text, truncated


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
        outcome = await _resolve_doc_layer(project_id, bid_id, tenant)
        doc_layer_text, ocr_warnings = outcome.text, outcome.warnings
        if outcome.force_manual_review:
            # F7 降级归宿：证据层不可用时**不回落 inline**（那条路径对 400 页投标产出的是
            # 带 warning 的错误评分），也不把注定无证据的 prompt 发出去，直接出人工复核结论。
            return await asyncio.to_thread(
                build_manual_review_result,
                request_id=request_id,
                tenant=tenant,
                project_id=project_id,
                bid_id=bid_id,
                warnings=ocr_warnings,
            )

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
    truncation: TruncatedDraft | None = None
    if ocr_block:
        ocr_block, truncation = _bound_ocr_block(
            ocr_block, request_id=request_id, model=resolved_model or None
        )
    if truncation is not None:
        # KD4：截断此前只进运维日志与模型上下文，结论与前端零痕迹（2026-08-18 事故）。
        ocr_warnings.append(truncation_warning(truncation, stops_scoring=False))

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

    # A（2026-08-17 延时治理）：通则层法规 + 业务记忆改服务端注入，命令/skill 里对应的 Read
    # 指令已删。拼在 criteria **之后**——bound_tender_context 只削 criteria 之前的证据段，
    # 法定底座落在尾段才不会被预算闸削掉（削掉 = 承重 policy_refs 无处可引）。
    if context:
        context = context + tender_rules_block()

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
    # B：底稿在场 → 锁掉自由 Glob/Read（见 DRAFT_INJECTED_TOOLS）。底稿缺失时**不锁**，
    # 那条降级路径下模型必须还能自己读文件。
    tool_kwargs: dict[str, list[str]] = (
        {"tools": DRAFT_INJECTED_TOOLS, "allowed_tools": DRAFT_INJECTED_TOOLS} if context else {}
    )
    # 有意的安全设计（D11 TA4）：case_root 恒绑定本案目录，因此受 ocr-page
    # PreToolUse hook 约束的 Bash 对每次评标都可用——任一评标都可能需要低清页重识别。
    # hook 是唯一闸；这是显式设计，不是 case_root 默认回填带来的副作用。
    evaluation_case_root = case_root if case_root is not None else Path(directory_path)

    # 两条调用路径共用的 kwargs（整单跑 / resume 修补轮），逐字同一套，避免两份参数表漂移。
    def _call_kwargs() -> dict[str, Any]:
        return {
            "schema_name": TENDER_OUTPUT_SCHEMA_NAME,
            "request_id": request_id,
            "tenant": tenant,
            # 显式透传 → 结论落 results.project_id（codex P1.3）
            "project_id": project_id,
            # X2：显式透传 → 结论落 results.bid_id（bids 层手填回填 join key）
            "bid_id": bid_id,
            # 每次 attempt 取新 conversation_id：整单重跑那条路径靠"查不到同 conversation 的
            # 历史会话"来保证真的重来一遍；共用一个 id 会让它悄悄变成隐式 resume。
            "conversation_id": new_conversation_id(),
            # R1 evidence-resolution：透传注入给模型的那份底稿 ocr_block 给结论校验闸做出处
            # 回查。**传 ocr_block 而非 context**——context 尾部已追加 criteria 注入块 + OCR
            # 头注释，会干扰 tier/page 解析（design critic blind-spot C）。
            # 两种形态都带 `### 文件:` + `【第N页】` 锚点，parse_corpus 一视同仁：doc 层/inline
            # 是**整份底稿**；证据层是**按项检出的片段**，其锚点由 EvidenceBlock.render 逐块
            # 补齐（块不自带文件头时归属会跟着检索顺序漂，见该函数 docstring / pass3 F1）。
            "evidence_source": ocr_block,
            "case_root": evaluation_case_root,
            "on_progress": on_progress,  # 思考流式：agent 文本片段实时回调给 worker
            "effort": _TENDER_EFFORT,  # 评标 per-call 扩展思考（不全局默认，避免拖慢 audit）
            # 遗留①：开 include_partial_messages → 端点逐字吐 StreamEvent partial，on_progress
            # 实时收增量(真·流式)。端点不支持流式则无 partial、退回完整 AssistantMessage + 兜底
            # final-flush，行为不退化。env TENDER_STREAM_PARTIAL=0 可关。
            "include_partial_messages": _stream_partial_enabled(),
            # 文本模式（与 audit 对齐）：大底稿(百页标书)下 SDK 结构化输出会 error_max_structured_
            # output_retries；文本模式由服务端抽 JSON，对大输入更稳。配合命令里的 JSON 输出硬化。
            "structured": False,
            **tool_kwargs,
            **model_kwargs,
        }

    # 契约失败重试（对齐 audit runner）：deepseek 文本模式偶发不出 JSON / 写坏 JSON。
    # OCR 预处理在循环外只做一次（慢且确定性），仅重试模型调用。
    # D：失败带回了 CLI 会话 id 时**不整单重跑**——resume 那个会话只发一条短修补指令让模型把
    # JSON 改对（评标结论已在会话里，重发底稿 = 让它从头再评一遍，正是那个 20 分钟档）。
    last_error: Exception | None = None
    session_to_repair: str | None = None
    for attempt in range(TENDER_CONTRACT_MAX_RETRY + 1):
        try:
            if session_to_repair is not None:
                payload, meta = await run_agent_json(
                    build_repair_prompt(last_error),
                    resume_session_id=session_to_repair,
                    **_call_kwargs(),
                )
            else:
                payload, meta = await run_command_json(
                    "tender-evaluate",
                    directory_path,
                    context=context,
                    **_call_kwargs(),
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
                # 线索——必须带上"去哪复标定"，否则标定常量会变成第五个被凭猜调的错数字。
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
            # 拿得到会话就走修补轮；拿不到（会话建立前就失败）回落整单重跑，不静默少跑一轮。
            session_to_repair = repair_session_id(exc)
            logger.warning(
                "tender attempt failed (%s, %d/%d), retrying via %s: %s",
                type(exc).__name__,
                attempt + 1,
                TENDER_CONTRACT_MAX_RETRY + 1,
                "contract_repair" if session_to_repair else "full_rerun",
                exc,
                extra={"request_id": request_id, "tenant": tenant or "default"},
            )
    # 不可达：循环要么 return 要么在最后一次 attempt re-raise。
    raise AssertionError("unreachable: tender retry loop exited without returning") from last_error
