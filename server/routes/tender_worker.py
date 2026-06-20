"""Background task execution for tender bid evaluation.

镜像 ``audit_worker``：准入闸 + 引用集 + 信号量限并发 + 硬超时 + 任务状态机更新。区别是调
``/tender-evaluate`` 五步内联命令（而非 inline audit runner）。结果归档由
``run_command_json → run_agent_json`` 内部的 ``archive_result_payload`` 完成，
故必须透传 ``request_id`` / ``tenant``，GET 结果端点才能取到。
"""

from __future__ import annotations

import asyncio
import logging
import os

from server.common.command_adapter import run_command_json
from server.common.contract import DEFAULT_OUTPUT_SCHEMA_NAME
from server.platform.logging_setup import logging_context
from server.stores.request_store import utc_now
from server.stores.session_store import new_conversation_id
from server.stores.tender_task_store import upsert_tender_task

logger = logging.getLogger(__name__)

# 评标硬超时（秒）。标书数据量大（40MB+/~18 章节），S2 事实抽取慢，默认放宽到 600s。
TENDER_TIMEOUT_SEC = float(os.getenv("TENDER_TIMEOUT_SEC", "600"))

# 同时进行的评标上限。单标已重（多章节多跳），默认 1，超额提交在信号量处排队。
MAX_CONCURRENT_TENDER = int(os.getenv("MAX_CONCURRENT_TENDER", "1"))
_TENDER_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_TENDER)

# 准入上限（round4 F5，对齐 audit_worker）：信号量只限执行，accepted 任务会在信号量处无界
# 堆积 → 内存 DoS。在途(排队+执行)任务数达此上限时，evaluate/retry 直接回 503，不再无界接单。
MAX_PENDING_TENDERS = int(os.getenv("MAX_PENDING_TENDERS", "50"))

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
    *, request_id: str, tenant: str, directory_path: str, project_id: str | None = None
):
    return await run_command_json(
        "tender-evaluate",
        directory_path,
        schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
        request_id=request_id,
        tenant=tenant,
        project_id=project_id,  # 显式透传 → 结论落 results.project_id（codex P1.3）
        conversation_id=new_conversation_id(),
    )


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
        try:
            payload, meta = await asyncio.wait_for(
                _run_evaluation(
                    request_id=request_id,
                    tenant=tenant,
                    directory_path=directory_path,
                    project_id=project_id,
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
