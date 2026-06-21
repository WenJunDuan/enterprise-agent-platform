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
from server.stores.tender_task_store import update_tender_progress, upsert_tender_task

logger = logging.getLogger(__name__)

# 评标硬超时（秒）。标书大（40MB+/百页）+ 模型 extended thinking，单次评标实测可达 ~9min(537s)。
# 前端已解耦【不阻塞等待】（提交即返回、analyzing 独立轮询、可离开回来恢复），故后端超时仅作
# "防无限挂"兜底，默认大幅放宽到 3600s（env TENDER_TIMEOUT_SEC 可调）。
TENDER_TIMEOUT_SEC = float(os.getenv("TENDER_TIMEOUT_SEC", "3600"))

# 同时进行的评标上限。单标已重（多章节多跳），默认 1，超额提交在信号量处排队。
MAX_CONCURRENT_TENDER = int(os.getenv("MAX_CONCURRENT_TENDER", "1"))
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


async def _run_evaluation(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    project_id: str | None = None,
    on_progress: Callable[[str], None] | None = None,
):
    # P4：先确定性 OCR 预处理（pymupdf 直读 / 云 OCR），把底稿注入命令上下文 → 模型不再自己 Read
    # PDF（绕开模型 Read 脆弱点 + poppler 依赖）。经 to_thread 不阻塞事件循环；失败/关闭 → None 回落。
    ocr_block = await asyncio.to_thread(
        ocr_preprocess_block, directory_path, purpose=TENDER_OCR_PURPOSE
    )
    context = (
        f"=== OCR/直读底稿（确定性预处理，优先用此文本，无需再 Read 文件）===\n{ocr_block}"
        if ocr_block
        else None
    )
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
        )


async def _execute_inner(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    source_mode: str,
    project_id: str | None = None,
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
        # 思考流式：on_progress 累积 agent 文本片段（含 deepseek 思考/分析）到内存；flusher 每
        # _PROGRESS_FLUSH_SEC 把最新尾部写 task.progress_message（节流，防每片段写 DB），前端轮询取。
        progress_state = {"text": ""}

        def on_progress(text: str) -> None:
            snippet = text.strip()
            if not snippet:
                return
            progress_state["text"] = (progress_state["text"] + snippet + "\n")[-_PROGRESS_MAX_CHARS:]
            logger.info(
                "tender_progress",
                extra={
                    "request_id": request_id,
                    "tenant": tenant or "default",
                    "snippet": snippet[:_PROGRESS_LOG_SNIPPET],
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
                    on_progress=on_progress,
                ),
                timeout=TENDER_TIMEOUT_SEC,
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


def schedule_tender_evaluation_task(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    source_mode: str,
    project_id: str | None = None,
) -> None:
    """Fire-and-forget: schedule the evaluation task as a tracked asyncio background task."""
    task = asyncio.create_task(
        execute_tender_evaluation_task(
            request_id=request_id,
            tenant=tenant,
            directory_path=directory_path,
            source_mode=source_mode,
            project_id=project_id,
        )
    )
    _track_task(task)  # round4 F5：留引用防 GC + 计入在途（准入闸）
