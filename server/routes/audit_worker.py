"""Background task execution for directory audits.

Handles the async fire-and-forget lifecycle: admission cap, semaphore gating,
run, and task-record update on success / timeout / error.  Isolated here so the
route handlers in audit.py stay focused on HTTP concerns.
"""

from __future__ import annotations

import asyncio
import logging
import os

from server.audit.runner import CASE_REQUEST_FILE, run_inline_directory_audit
from server.ocr.pipeline import ocr_preprocess_block
from server.platform.logging_setup import logging_context
from server.stores.audit_task_store import upsert_audit_task
from server.stores.request_store import utc_now

logger = logging.getLogger(__name__)

# 单次审核硬超时（秒）。仅兜底防无限挂起，不是目标耗时：造假快判仍 ~1 跳返回。
# 默认放宽到 180s，给"读附件"等多跳常规审核留余量（网关 ~17-48s/跳，最坏 3 跳 ~144s）。
AUDIT_TIMEOUT_SEC = float(os.getenv("AUDIT_TIMEOUT_SEC", "180"))

# 同时进行的审核上限。每单审核会拉起一个 claude CLI 子进程，无上限并发会打爆内网机内存/CPU。
# 超额的提交在信号量处排队，任务状态保持 accepted 直到有空位（排队时间不计入 AUDIT_TIMEOUT_SEC）。
MAX_CONCURRENT_AUDITS = int(os.getenv("MAX_CONCURRENT_AUDITS", "2"))
_AUDIT_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_AUDITS)

# 准入上限（round4 F5）：信号量只限执行(2)，但 accepted 任务会在信号量处无界堆积 → 内存 DoS。
# 在途(排队+执行)任务数达此上限时，submit/retry 直接回 503，不再无界接单。
MAX_PENDING_AUDITS = int(os.getenv("MAX_PENDING_AUDITS", "50"))

# round4 F5：裸 asyncio.create_task 不留引用 → 待定任务可被 GC 静默回收。这里留强引用集，
# 完成即自清；集合大小兼作"在途任务数"供准入闸用。
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def _track_task(task: asyncio.Task[None]) -> None:
    """留强引用防 fire-and-forget 任务被 GC 回收；done 时自清（round4 F5）。"""
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


def admission_available() -> bool:
    """round4 F5 准入闸：在途任务数低于上限才接新单，否则路由回 503（防 accepted 无界堆积）。"""
    return len(_BACKGROUND_TASKS) < MAX_PENDING_AUDITS


async def _run_directory_audit(*, request_id: str, tenant: str, directory_path: str):
    # P4：附件确定性 OCR 预处理放路由层做（routes 可依赖 ocr 域；feature 域 audit/ 不可跨域 import，
    # 见 test_layering）。经 to_thread 不阻塞事件循环；失败/关闭 → None，runner 回落模型自己 Read。
    ocr_block = await asyncio.to_thread(
        ocr_preprocess_block, directory_path, skip={CASE_REQUEST_FILE}
    )
    return await run_inline_directory_audit(
        directory_path,
        request_id=request_id,
        tenant=tenant,
        ocr_block=ocr_block,
    )


async def execute_directory_audit_task(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    source_mode: str = "directory",
) -> None:
    """Gate on the concurrency semaphore, then run the audit task."""
    # 并发闸：拿不到名额就在此 await 排队，排队期间任务保持 accepted（不计入审核超时）。
    async with _AUDIT_SEMAPHORE:
        await _execute_inner(
            request_id=request_id,
            tenant=tenant,
            directory_path=directory_path,
            source_mode=source_mode,
        )


async def _execute_inner(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    source_mode: str,
) -> None:
    started_at = utc_now()
    with logging_context(request_id=request_id, tenant=tenant):
        # round4 F4：同步 SQLite 写经 to_thread 移出事件循环，写争用时不阻塞整个 loop。
        await asyncio.to_thread(
            upsert_audit_task,
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
                "progress_message": "Agent 正在运行中",
                "started_at": started_at,
                "updated_at": started_at,
            },
        )
        try:
            payload, meta = await asyncio.wait_for(
                _run_directory_audit(
                    request_id=request_id,
                    tenant=tenant,
                    directory_path=directory_path,
                ),
                timeout=AUDIT_TIMEOUT_SEC,
            )
            finished_at = utc_now()
            await asyncio.to_thread(
                upsert_audit_task,
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
                    "progress_message": "审核完成",
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                },
            )
        except asyncio.TimeoutError:
            logger.warning(
                "directory_audit_timeout",
                extra={
                    "request_id": request_id,
                    "tenant": tenant,
                    "route": "/audit/submit",
                    "timeout_sec": AUDIT_TIMEOUT_SEC,
                },
            )
            finished_at = utc_now()
            await asyncio.to_thread(
                upsert_audit_task,
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
                        f"审核超时：超过 {int(AUDIT_TIMEOUT_SEC)}s 未返回结果"
                        "（可能模型网关拥塞），请稍后重试"
                    ),
                    "progress_message": "审核超时",
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                },
            )
        except Exception as exc:
            logger.exception(
                "directory_audit_failed",
                extra={"request_id": request_id, "tenant": tenant, "route": "/audit/submit"},
            )
            finished_at = utc_now()
            await asyncio.to_thread(
                upsert_audit_task,
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
                    "progress_message": "审核失败",
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                },
            )


def schedule_directory_audit_task(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    source_mode: str,
) -> None:
    """Fire-and-forget: schedule the audit task as a tracked asyncio background task."""
    task = asyncio.create_task(
        execute_directory_audit_task(
            request_id=request_id,
            tenant=tenant,
            directory_path=directory_path,
            source_mode=source_mode,
        )
    )
    _track_task(task)  # round4 F5：留引用防 GC + 计入在途（准入闸）
