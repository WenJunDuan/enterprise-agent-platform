"""Background task execution for tender bid evaluation.

镜像 ``audit_worker``：准入闸 + 引用集 + 信号量限并发 + 硬超时 + 任务状态机更新。评标核心
（doc-layer 读取 + OCR 回落 + criteria 注入 + 契约重试）已下沉 ``server.tender.runner``
（D1 T2，公开名 ``run_tender_evaluation``，本模块以 ``_run_evaluation`` 别名调用）——本模块只留
调度壳：准入闸/信号量/超时/思考流式进度落库/任务状态机更新，调 ``/tender-evaluate`` 五步内联命令
的结果归档由 ``run_command_json → run_agent_json`` 内部的 ``archive_result_payload`` 完成，
故必须透传 ``request_id`` / ``tenant``，GET 结果端点才能取到。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os

from server.platform.logging_setup import logging_context
from server.stores.request_store import utc_now
from server.stores.result_store import update_result_criteria_ref
from server.stores.tender_doc_store import (
    backfill_bid_doc_bidder_name,
    get_project_doc,
    update_project_doc_criteria,
)
from server.stores.tender_task_store import update_tender_progress, upsert_tender_task
from server.tender.compare_worker import maybe_schedule_compare
from server.tender.runner import run_tender_evaluation as _run_evaluation

logger = logging.getLogger(__name__)

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

# 思考流式（轮询伪流式）：on_progress 累积 agent 文本片段；flusher 节流写 task.progress_message。
_PROGRESS_FLUSH_SEC = float(os.getenv("TENDER_PROGRESS_FLUSH_SEC", "1.5"))  # 写 DB 节流间隔
_PROGRESS_MAX_CHARS = int(os.getenv("TENDER_PROGRESS_MAX_CHARS", "4000"))  # progress_message 留最新尾部
_PROGRESS_LOG_SNIPPET = 500  # 每片段落思考日志的截断长度
# 思考日志节流：每积累多少字符记一次 INFO（partial 流式逐字回调 1000+ 次，否则日志爆炸）。
_PROGRESS_LOG_EVERY = int(os.getenv("TENDER_PROGRESS_LOG_EVERY", "800"))

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
                became_authority = await asyncio.to_thread(
                    _backfill_criteria, project_id, tenant, criteria
                )
                # KD1：ref 补写进已归档结论（归档早于 runner 打标），并消解 backfill 竞态。
                await asyncio.to_thread(
                    _persist_criteria_ref, request_id, tenant, payload, became_authority
                )
            # X2：投标单位名称只填空回填（bids 层），挂靠同一 completed 分支。
            # bid_id=None（散单/非 prewarm）时无法定位 (project_id, bid_id) 行，安全跳过。
            if project_id and bid_id and isinstance(payload, dict):
                bidder_info = (payload.get("extracted_data") or {}).get("bidder_info") or {}
                bidder_name = (
                    bidder_info.get("bidder_name") if isinstance(bidder_info, dict) else None
                )
                await asyncio.to_thread(
                    _backfill_bidder_name, project_id, bid_id, tenant, bidder_name
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
            # KD2：**任何终态**（completed / timeout / failed）后都由服务端复查一次是否该入队横比
            # ——横比触发不再依赖前端在场（旧实现唯一触发点是前端 fire-and-forget，失败即静默）。
            # 放 finally 是因为"某家 failed、其余 ≥2 家已完成"同样应该出横比结果。
            if project_id:
                await asyncio.to_thread(maybe_schedule_compare, tenant, project_id)
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
) -> bool:
    """回填评标 criteria 到招标层（首个写入者赢，已存不覆盖，散单/异常静默跳过）。

    评标 completed 后，若 payload.extracted_data.criteria 存在，调本函数把评分标准
    持久化到 tender_project_docs.criteria（项目级复用，后续家评标 S1 可读层命中秒过）。

    Args:
        project_id: 招标项目 ID；为 None（散单）时直接返回。
        tenant: 租户作用域。
        criteria: 已解析的 criteria 对象（dict）；为 None/空时跳过。

    Returns:
        True 当且仅当**本次**写入使该家 criteria 成为项目权威（KD1 据此把 ref 升为 project）。
    """
    if not project_id or not criteria:
        return False
    try:
        import json as _json

        existing = get_project_doc(project_id, tenant)
        if existing is None:
            # 招标层记录不存在（旧散单迁移等），安全跳过。
            return False
        if existing.get("criteria"):
            # 已存非空 → 首个写入者赢，不覆盖。
            return False
        criteria_json = _json.dumps(criteria, ensure_ascii=False)
        update_project_doc_criteria(project_id, tenant, criteria_json)
        logger.info(
            "tender_criteria_backfilled",
            extra={"project_id": project_id, "tenant": tenant or "default"},
        )
        return True
    except Exception:
        logger.warning(
            "tender_criteria_backfill_failed",
            extra={"project_id": project_id, "tenant": tenant or "default"},
            exc_info=True,
        )
        return False


def _persist_criteria_ref(
    request_id: str,
    tenant: str,
    payload: dict[str, object],
    became_authority: bool,
) -> None:
    """把 runner 打的 ``criteria_ref`` 补写进已归档结论，并消解 backfill 竞态（KD1）。

    评标开始时项目权威缺位 → runner 记 ``self_parsed``；但若本家 criteria 恰好赢得 backfill，
    本家**就是**权威，ref 须升为 ``project``（否则横比会把唯一权威来源自己排除掉）。
    输给别家则保持 ``self_parsed``，横比时排除该家并提示重评。

    Args:
        request_id: 结论 ID。
        tenant: 租户作用域。
        payload: 评标结论（runner 已打 extracted_data.criteria_ref）。
        became_authority: 本次 backfill 是否使本家 criteria 成为项目权威。
    """
    extracted = payload.get("extracted_data")
    ref = extracted.get("criteria_ref") if isinstance(extracted, dict) else None
    if not isinstance(ref, dict):
        return
    if became_authority and ref.get("source") == "self_parsed":
        ref = {**ref, "source": "project"}
        extracted["criteria_ref"] = ref
    try:
        update_result_criteria_ref(request_id, tenant, ref)
    except Exception:
        logger.warning(
            "tender_criteria_ref_persist_failed",
            extra={"request_id": request_id, "tenant": tenant or "default"},
            exc_info=True,
        )


def _backfill_bidder_name(
    project_id: str | None,
    bid_id: str | None,
    tenant: str,
    bidder_name: object,
) -> None:
    """只填空回填投标单位名称到 bids 层（X2，挂靠 _backfill_criteria 同一 completed 分支）。

    评标 completed 后，若 payload.extracted_data.bidder_info.bidder_name 存在，调本函数
    尝试写入 tender_bid_docs.bidder_name（手填优先，任何情况下不覆盖非空手填，见
    tender_doc_store.backfill_bid_doc_bidder_name 的三键原子 UPDATE 语义）。

    Args:
        project_id: 招标项目 ID；为 None（散单）时直接返回。
        bid_id: 投标文档 ID；为 None（散单/非 prewarm）时无法定位行，直接返回。
        tenant: 租户作用域。
        bidder_name: agent 识别到的投标单位名称；为 None/空时跳过（不编造）。
    """
    if not project_id or not bid_id or not bidder_name:
        return
    try:
        backfill_bid_doc_bidder_name(project_id, bid_id, tenant, str(bidder_name))
        logger.info(
            "tender_bidder_name_backfilled",
            extra={"project_id": project_id, "bid_id": bid_id, "tenant": tenant or "default"},
        )
    except Exception:
        logger.warning(
            "tender_bidder_name_backfill_failed",
            extra={"project_id": project_id, "bid_id": bid_id, "tenant": tenant or "default"},
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
