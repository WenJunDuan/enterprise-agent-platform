"""Background task execution for tender bid evaluation.

镜像 ``audit_worker``：准入闸 + 引用集 + 信号量限并发 + 硬超时 + 任务状态机更新。区别是调
``/tender-evaluate`` 五步内联命令（而非 inline audit runner）。结果归档由
``run_command_json → run_agent_json`` 内部的 ``archive_result_payload`` 完成，
故必须透传 ``request_id`` / ``tenant``，GET 结果端点才能取到。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import Callable

from server.common.command_adapter import run_command_json
from server.common.contract import DEFAULT_OUTPUT_SCHEMA_NAME
from server.ocr.pipeline import ocr_preprocess_block
from server.platform.logging_setup import logging_context
from server.stores.request_store import utc_now
from server.stores.session_store import new_conversation_id
from server.stores.tender_doc_store import (
    get_bid_doc,
    get_project_doc,
    update_project_doc_criteria,
)
from server.stores.tender_task_store import update_tender_progress, upsert_tender_task

logger = logging.getLogger(__name__)

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

# 评标硬超时（秒）。标书大（40MB+/百页）+ 模型 extended thinking，单次评标实测可达 ~9min(537s)。
# 前端已解耦【不阻塞等待】（提交即返回、analyzing 独立轮询、可离开回来恢复），故后端超时仅作
# "防无限挂"兜底，默认大幅放宽到 3600s（env TENDER_TIMEOUT_SEC 可调）。
TENDER_TIMEOUT_SEC = float(os.getenv("TENDER_TIMEOUT_SEC", "3600"))

# 同时进行的评标上限。单标已重（多章节多跳），默认 1，超额提交在信号量处排队。
# R4-C 提速：默认 1→2（多投标并行评标，N 家从 N×~290s 压到 ~并行）。每并发 = 一路独立模型调用，
# 成本/限流随之×N；模型网关并发限制时经 .env MAX_CONCURRENT_TENDER 调回 1 或按额度调高。
MAX_CONCURRENT_TENDER = int(os.getenv("MAX_CONCURRENT_TENDER", "2"))
_TENDER_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_TENDER)

# 准入上限（round4 F5，对齐 audit_worker）：信号量只限执行，accepted 任务会在信号量处无界
# 堆积 → 内存 DoS。在途(排队+执行)任务数达此上限时，evaluate/retry 直接回 503，不再无界接单。
MAX_PENDING_TENDERS = int(os.getenv("MAX_PENDING_TENDERS", "50"))

# 契约失败重试次数。tender 输出大而复杂（14+项 scoring），deepseek 文本模式偶发不出 JSON /
# 写坏 JSON（间歇性，同标重跑可成功）。audit 早有重试环，tender 此前缺失 → 单次 flaky 即失败。
# 默认 2（共 3 次尝试，比 audit 的 1 更宽，因 tender 输出更易 flaky）；OCR 预处理只做一次不重跑。
TENDER_CONTRACT_MAX_RETRY = int(os.getenv("TENDER_CONTRACT_MAX_RETRY", "2"))

# 思考流式（轮询伪流式）：on_progress 累积 agent 文本片段；flusher 节流写 task.progress_message。
_PROGRESS_FLUSH_SEC = float(os.getenv("TENDER_PROGRESS_FLUSH_SEC", "1.5"))  # 写 DB 节流间隔
_PROGRESS_MAX_CHARS = int(os.getenv("TENDER_PROGRESS_MAX_CHARS", "4000"))  # progress_message 留最新尾部
_PROGRESS_LOG_SNIPPET = 500  # 每片段落思考日志的截断长度
# 思考日志节流：每积累多少字符记一次 INFO（partial 流式逐字回调 1000+ 次，否则日志爆炸）。
_PROGRESS_LOG_EVERY = int(os.getenv("TENDER_PROGRESS_LOG_EVERY", "800"))

# 评标推理强度（extended thinking）：评标是高难合规判断，默认 xhigh 压 deepseek 随机性（per-call，
# 不走全局 build_options 默认 → 不拖慢 audit，codex r4 P1）；env 可调或设非法值走端点默认。
_TENDER_EFFORT = os.getenv("TENDER_REASONING_EFFORT", "xhigh")

# 评标场景 OCR 目的（治"OCR 无目的性"）：让 OCR 引擎在通用文本提取之外，重点完整、结构化地
# 还原评分标准/评标办法/扣分细则/废标条款等【表格】——评分表是评标命脉，通用提取易丢表格行列
# 致扣分项缺失。仅 OpenAI-compatible OCR 路径注入生效（云/本地 pipeline 为固定 OCR，见 engine）。
TENDER_OCR_PURPOSE = (
    "本批为招投标评标材料。请在完整提取文本之外，特别完整、结构化地还原"
    "【评分标准/评标办法/评分细则/扣分细则/加分项/废标与资格条款】等表格："
    "保留表格的行列结构与每一行的分值数字，不要合并或省略任何评分/扣分行。"
)

# round4 F5：裸 asyncio.create_task 不留引用 → 待定任务可被 GC 静默回收。留强引用集，完成即
# 自清；集合大小兼作"在途任务数"供准入闸用。
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def _track_task(task: asyncio.Task[None]) -> None:
    """留强引用防 fire-and-forget 任务被 GC 回收；done 时自清（round4 F5）。"""
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


def admission_available() -> bool:
    """round4 F5 准入闸：在途任务数低于上限才接新单，否则路由回 503（防 accepted 无界堆积）。"""
    return len(_BACKGROUND_TASKS) < MAX_PENDING_TENDERS


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


# R6-R2 复用预热 OCR：等招标层+当前家投标层 OCR 就绪的上限/间隔。标书大(百页)OCR 可达数分钟，
# 给足窗口；env 可调。用迭代次数计时（不依赖 wall-clock 时间函数）。
_DOC_LAYER_WAIT_SEC = float(os.getenv("TENDER_DOC_LAYER_WAIT_SEC", "360"))
_DOC_LAYER_POLL_SEC = 3.0


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


async def _run_evaluation(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    project_id: str | None = None,
    bid_id: str | None = None,
    on_progress: Callable[[str], None] | None = None,
):
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
        doc_layer_text = await asyncio.to_thread(
            _load_doc_layer_context, project_id, bid_id, tenant
        )

    if doc_layer_text is not None:
        ocr_block: str | None = doc_layer_text
    else:
        # P4 原串行 OCR 回落（pymupdf 直读 / 云 OCR）。
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
                    "\n\n=== 已解析评分标准 criteria（S1 直接采用，勿重新解析）===\n"
                    + readable
                )
                context = context + criteria_block
        except Exception:
            logger.debug("criteria context injection failed, continuing without", exc_info=True)
    # 契约失败重试（对齐 audit runner）：deepseek 文本模式偶发不出 JSON / 写坏 JSON，重跑可成功。
    # OCR 预处理在循环外只做一次（慢且确定性），仅重试模型调用。
    last_error: Exception | None = None
    for attempt in range(TENDER_CONTRACT_MAX_RETRY + 1):
        try:
            return await run_command_json(
                "tender-evaluate",
                directory_path,
                schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
                request_id=request_id,
                tenant=tenant,
                project_id=project_id,  # 显式透传 → 结论落 results.project_id（codex P1.3）
                conversation_id=new_conversation_id(),
                context=context,
                on_progress=on_progress,  # 思考流式：agent 文本片段实时回调给 worker
                effort=_TENDER_EFFORT,  # 评标 per-call 扩展思考（不全局默认，避免拖慢 audit）
                # 遗留①：开 include_partial_messages → 端点逐字吐 StreamEvent partial，on_progress
                # 实时收增量(真·流式)。端点不支持流式则无 partial、退回完整 AssistantMessage + 兜底
                # final-flush，行为不退化。env TENDER_STREAM_PARTIAL=0 可关。
                include_partial_messages=_stream_partial_enabled(),
                # 文本模式（与 audit 对齐）：大底稿(百页标书)下 SDK 结构化输出会 error_max_structured_
                # output_retries；文本模式由服务端抽 JSON，对大输入更稳。配合命令里的 JSON 输出硬化。
                structured=False,
            )
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


async def execute_tender_evaluation_task(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    source_mode: str = "directory",
    project_id: str | None = None,
    bid_id: str | None = None,
) -> None:
    """Gate on the concurrency semaphore, then run the evaluation task."""
    # 并发闸：拿不到名额就在此 await 排队，排队期间任务保持 accepted（不计入评标超时）。
    async with _TENDER_SEMAPHORE:
        await _execute_inner(
            request_id=request_id,
            tenant=tenant,
            directory_path=directory_path,
            source_mode=source_mode,
            project_id=project_id,
            bid_id=bid_id,
        )


async def _execute_inner(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    source_mode: str,
    project_id: str | None = None,
    bid_id: str | None = None,
) -> None:
    started_at = utc_now()
    with logging_context(request_id=request_id, tenant=tenant):
        # round4 F4：同步 SQLite 写经 to_thread 移出事件循环，写争用时不阻塞整个 loop。
        await asyncio.to_thread(
            upsert_tender_task,
            {
                "request_id": request_id,
                "tenant": tenant,
                "status": "running",
                "mode": source_mode,
                "source_mode": source_mode,
                "case_path": directory_path,
                "claim_id": None,
                "result_file": None,
                "session_id": None,
                "error_detail": None,
                "progress_message": "评标 Agent 正在运行中",
                "started_at": started_at,
                "updated_at": started_at,
            },
        )
        # 思考流式：on_progress 累积 agent 文本片段（含思考/分析）到内存；flusher 每
        # _PROGRESS_FLUSH_SEC 把最新尾部写 task.progress_message（节流，防每片段写 DB），前端轮询取。
        # logged_len：日志节流游标——partial 模式逐字回调 1000+ 次，不能每次都 INFO（日志爆炸）。
        progress_state = {"text": "", "logged_len": 0}

        def on_progress(text: str) -> None:
            # **不 strip**：partial 模式下每个 delta 是句中片段，strip 会吞掉词间空格致显示粘连
            # （helloworld）；只跳过空串。直接拼接（不再每片段加 \n，否则逐字 delta 会每字一行）。
            if not text:
                return
            progress_state["text"] = (progress_state["text"] + text)[-_PROGRESS_MAX_CHARS:]
            # 日志节流：仅每积累 ≥ _PROGRESS_LOG_EVERY 字符记一次思考日志（partial 1000+ 次回调不刷屏）。
            if len(progress_state["text"]) - int(progress_state["logged_len"]) >= _PROGRESS_LOG_EVERY:
                progress_state["logged_len"] = len(progress_state["text"])
                logger.info(
                    "tender_progress",
                    extra={
                        "request_id": request_id,
                        "tenant": tenant or "default",
                        "snippet": progress_state["text"][-_PROGRESS_LOG_SNIPPET:],
                    },
                )

        async def _flush_progress() -> None:
            while True:
                await asyncio.sleep(_PROGRESS_FLUSH_SEC)
                if progress_state["text"]:
                    try:
                        await asyncio.to_thread(
                            update_tender_progress, request_id, progress_state["text"]
                        )
                    except Exception:  # noqa: BLE001 - 进度写失败不影响评标，仅记 debug
                        logger.debug("progress flush failed", exc_info=True)

        flusher = asyncio.create_task(_flush_progress())
        try:
            payload, meta = await asyncio.wait_for(
                _run_evaluation(
                    request_id=request_id,
                    tenant=tenant,
                    directory_path=directory_path,
                    project_id=project_id,
                    bid_id=bid_id,
                    on_progress=on_progress,
                ),
                timeout=TENDER_TIMEOUT_SEC,
            )
            # criteria 项目级回填（P3 A1）：评标 completed 后，首次把会话解析的 criteria
            # 写到招标层 → 同项目后续家评标 S1 读层命中复用，不再重复解析。异常不崩主流程。
            if project_id and isinstance(payload, dict):
                criteria = (payload.get("extracted_data") or {}).get("criteria")
                await asyncio.to_thread(
                    _backfill_criteria, project_id, tenant, criteria
                )
            finished_at = utc_now()
            await asyncio.to_thread(
                upsert_tender_task,
                {
                    "request_id": request_id,
                    "tenant": tenant,
                    "status": "completed",
                    "mode": source_mode,
                    "source_mode": source_mode,
                    "case_path": directory_path,
                    "claim_id": payload.get("claim_id") if isinstance(payload, dict) else None,
                    "result_file": meta.result_file,
                    "session_id": meta.claude_session_id,
                    "error_detail": None,
                    "progress_message": "评标完成",
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                },
            )
        except asyncio.TimeoutError:
            logger.warning(
                "tender_evaluation_timeout",
                extra={
                    "request_id": request_id,
                    "tenant": tenant,
                    "route": "/tender/evaluate",
                    "timeout_sec": TENDER_TIMEOUT_SEC,
                },
            )
            finished_at = utc_now()
            await asyncio.to_thread(
                upsert_tender_task,
                {
                    "request_id": request_id,
                    "tenant": tenant,
                    "status": "failed",
                    "mode": source_mode,
                    "source_mode": source_mode,
                    "case_path": directory_path,
                    "claim_id": None,
                    "result_file": None,
                    "session_id": None,
                    "error_detail": (
                        f"评标超时：超过 {int(TENDER_TIMEOUT_SEC)}s 未返回结果"
                        "（可能模型网关拥塞或标书过大），请稍后重试"
                    ),
                    "progress_message": "评标超时",
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                },
            )
        except Exception as exc:
            logger.exception(
                "tender_evaluation_failed",
                extra={"request_id": request_id, "tenant": tenant, "route": "/tender/evaluate"},
            )
            finished_at = utc_now()
            await asyncio.to_thread(
                upsert_tender_task,
                {
                    "request_id": request_id,
                    "tenant": tenant,
                    "status": "failed",
                    "mode": source_mode,
                    "source_mode": source_mode,
                    "case_path": directory_path,
                    "claim_id": None,
                    "result_file": None,
                    "session_id": None,
                    "error_detail": str(exc),
                    "progress_message": "评标失败",
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                },
            )
        finally:
            flusher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await flusher  # 等 cancel 真正落地（cancel 仅在下个 loop cycle 注入 CancelledError）
            # 遗留① 兜底 final-flush：qwen 等一次性返回端点 on_progress 仅在末尾触发一次，flusher 常在
            # 下个 _PROGRESS_FLUSH_SEC(1.5s) 周期前已被 cancel → 末次累积的思考/分析文本永不落库，前端
            # 区3 停在"运行中"。退出前补写一次，确保末态分析文本至少可见（逐字实时需端点流式 partial，
            # 见 _STREAM_PARTIAL 开关）。在 cancel 之后做，无与 flusher 并发写竞争。
            if progress_state["text"]:
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(
                        update_tender_progress, request_id, progress_state["text"]
                    )


def _backfill_criteria(
    project_id: str | None,
    tenant: str,
    criteria: object,
) -> None:
    """回填评标 criteria 到招标层（首个写入者赢，已存不覆盖，散单/异常静默跳过）。

    评标 completed 后，若 payload.extracted_data.criteria 存在，调本函数把评分标准
    持久化到 tender_project_docs.criteria（项目级复用，后续家评标 S1 可读层命中秒过）。

    Args:
        project_id: 招标项目 ID；为 None（散单）时直接返回。
        tenant: 租户作用域。
        criteria: 已解析的 criteria 对象（dict）；为 None/空时跳过。
    """
    if not project_id or not criteria:
        return
    try:
        import json as _json

        existing = get_project_doc(project_id, tenant)
        if existing is None:
            # 招标层记录不存在（旧散单迁移等），安全跳过。
            return
        if existing.get("criteria"):
            # 已存非空 → 首个写入者赢，不覆盖。
            return
        criteria_json = _json.dumps(criteria, ensure_ascii=False)
        update_project_doc_criteria(project_id, tenant, criteria_json)
        logger.info(
            "tender_criteria_backfilled",
            extra={"project_id": project_id, "tenant": tenant or "default"},
        )
    except Exception:
        logger.warning(
            "tender_criteria_backfill_failed",
            extra={"project_id": project_id, "tenant": tenant or "default"},
            exc_info=True,
        )


def schedule_tender_evaluation_task(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    source_mode: str,
    project_id: str | None = None,
    bid_id: str | None = None,
) -> None:
    """Fire-and-forget: schedule the evaluation task as a tracked asyncio background task."""
    task = asyncio.create_task(
        execute_tender_evaluation_task(
            request_id=request_id,
            tenant=tenant,
            directory_path=directory_path,
            source_mode=source_mode,
            project_id=project_id,
            bid_id=bid_id,
        )
    )
    _track_task(task)  # round4 F5：留引用防 GC + 计入在途（准入闸）
