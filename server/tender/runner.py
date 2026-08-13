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
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from server.common.command_adapter import run_command_json
from server.ocr.pipeline import ocr_preprocess_block
from server.platform.config import get_tender_eval_settings
from server.stores.session_store import new_conversation_id
from server.stores.tender_doc_store import decode_failed_files
from server.tender import doc_layer, doc_rerun
from server.tender.compare_input import build_criteria_ref, resolve_project_criteria
from server.tender.context_slim import bound_tender_context
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


def _criteria_context_block(criteria: dict[str, Any], version: str | None) -> str:
    """注入给模型的权威 criteria 块（含 KD1 版本号，供结论回引与人工回溯）。"""
    readable = json.dumps(criteria, ensure_ascii=False, indent=2)
    return (
        f"\n\n=== 已解析评分标准 criteria（版本 {version}，S1 直接采用，勿重新解析）===\n"
        f"{readable}\n"
        f"（本次评标依据的项目规则版本 criteria_version={version}；"
        "结论请照此版本判分，服务端会按该版本做跨投标人横比。）"
    )


def _stamp_criteria_ref(payload: Any, injected_version: str | None) -> None:
    """在结论上**确定性**打 ``extracted_data.criteria_ref``（KD1，不依赖模型回声）。

    注入过项目权威版本 → ``source=project``（即便模型转录快照漂移，判据也只看 ref）；
    未注入 → 按模型自解析副本记 ``self_parsed``（横比时排除并提示重评）。
    归档发生在 ``run_command_json`` 内部、早于本次打标，故 results 行里的 ref 由
    ``tender.worker`` 随后补写一次（见 ``worker._persist_criteria_ref``）。
    """
    if not isinstance(payload, dict):
        return
    extracted = payload.get("extracted_data")
    if not isinstance(extracted, dict):
        return
    ref = build_criteria_ref(injected_version, extracted.get("criteria"))
    if ref is not None:
        extracted["criteria_ref"] = ref


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


async def _resolve_doc_layer(
    project_id: str, bid_id: str | None, tenant: str
) -> tuple[str | None, list[dict[str, object]]]:
    """评标入口对预热底稿的完整决策（H3 KD2 + KD5）。

    顺序：等预热到终态（in-flight 才等，不再无条件超时回落 inline）→ 对 degraded/partial 自动
    重跑一次预热 → 复用底稿并按最终状态生成结论 warning。

    Returns:
        ``(doc 层底稿文本 | None, warnings)``；文本为 None 时调用方回落 inline OCR。
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
    loader = (
        doc_layer.load_doc_layer_context_slim
        if doc_layer.slim_context_enabled()
        else doc_layer.load_doc_layer_context
    )
    doc_layer_text = await asyncio.to_thread(loader, project_id, bid_id, tenant)
    if doc_layer_text is not None and bid_id:
        # 重跑后重新读一次：warning 必须反映**最终**状态，重跑成功就不该再报警。
        project_doc, bid_doc = await doc_layer.read_doc_rows(project_id, bid_id, tenant)
        warnings.extend(_ocr_integrity_warnings(project_doc, bid_doc))
    return doc_layer_text, warnings


def _ocr_warning_block(warnings: list[dict[str, object]]) -> str:
    """把底稿完整性 warning 渲染进模型上下文——评分项据此走 evidence 缺失规则，而不是静默判低分。"""
    lines = "\n".join(f"- {warning['message']}" for warning in warnings)
    return (
        "\n\n=== 底稿完整性告警（本次识别底稿存在降级/缺失）===\n"
        f"{lines}\n"
        "依赖上述材料的评分项：证据不足时按现行 evidence 缺失规则处理（manual_review / 不得凭空判 0）。"
    )


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
