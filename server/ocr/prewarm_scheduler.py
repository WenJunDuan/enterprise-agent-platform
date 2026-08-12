"""OCR prewarm task scheduling: concurrency cap + GC-safe tracking + per-project cancel.

S3 抽离：从 ``routes/tender.py`` 下沉的**通用 OCR 编排基建**——上传即 OCR 的并发上限信号量、
防 fire-and-forget 任务被 GC 静默回收的强引用集、按 ``project_id`` 分桶以便删项目时定向取消。
属 ocr feature 层的通用能力，由同为 feature 层的 ``server.tender.doc_pipeline``（D2 从
``routes/tender_doc_pipeline.py`` 移入）消费；本模块只依赖 stdlib，不引 stores/routes，避免层级反转。
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from functools import partial
from typing import Any, TypeVar

from server.platform.config import get_ocr_concurrency_settings

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

# P1-2: 强引用集防 fire-and-forget OCR 任务被 GC 回收；done 后自清。
_UPLOAD_OCR_TASKS: set[asyncio.Task[None]] = set()

# R7-#1: 按 project_id 分桶在跑的上传 OCR 任务 → 删项目时可 task.cancel() 真正"停止 OCR 服务"
# （释放信号量名额，停掉无谓计算）。DB-gone 守卫已保证停后写入 no-op，故 cancel 仅作提速、无脏数据。
_PROJECT_OCR_TASKS: dict[str, set[asyncio.Task[None]]] = {}

# P1-2: 上传即 OCR 并发上限（云 OCR 有限流；本地并行也消耗内存）；OCR_PREWARM_MAX env 可调。
# R4-B 提速：默认 2→4（招标 + 多投标同时 OCR，多家上传不再串行排队）。云 PaddleOCR(aistudio) 限流时
# 可经 .env 调回/再调高（实测云端并发上限后定值）。
_DEFAULT_UPLOAD_OCR_CONCURRENCY = 4
_UPLOAD_OCR_SEMAPHORE = asyncio.Semaphore(
    int(os.getenv("OCR_PREWARM_MAX", str(_DEFAULT_UPLOAD_OCR_CONCURRENCY)))
)


_OCR_EXECUTOR: ThreadPoolExecutor | None = None
_OCR_EXECUTOR_LOCK = threading.Lock()


def get_ocr_executor() -> ThreadPoolExecutor:
    """进程级命名 OCR 线程池（KD4）。

    OCR 是分钟级阻塞调用；此前它和 DB 读写、轮询共用 asyncio 默认 to_thread 池（4 核机 ≈8 线程），
    双标并发时 OCR 占满默认池 → **连状态写库都排队**，任务状态机看起来"卡死"。把 OCR 挪到独立
    命名池后，默认池只剩毫秒级短调用，状态更新不再被饿死。

    懒建（不在 import 期开线程），加锁防并发首调建出两个池。
    """
    global _OCR_EXECUTOR
    if _OCR_EXECUTOR is None:
        with _OCR_EXECUTOR_LOCK:
            if _OCR_EXECUTOR is None:
                _OCR_EXECUTOR = ThreadPoolExecutor(
                    max_workers=get_ocr_concurrency_settings().executor_workers,
                    thread_name_prefix="ocr",
                )
    return _OCR_EXECUTOR


async def run_in_ocr_executor(func: Callable[..., _T], /, *args: Any, **kwargs: Any) -> _T:
    """在命名 OCR 池里跑同步 OCR 调用（``asyncio.to_thread`` 的分池替身，KD4）。

    Args:
        func: 同步的 OCR 入口（如 ``prewarm_and_report`` / ``ocr_preprocess_block``）。
        *args: 位置参数。
        **kwargs: 关键字参数。

    Returns:
        ``func`` 的返回值。
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(get_ocr_executor(), partial(func, *args, **kwargs))


def get_upload_ocr_semaphore() -> asyncio.Semaphore:
    """Return the shared upload-OCR concurrency semaphore (P1-2 并发闸)."""
    return _UPLOAD_OCR_SEMAPHORE


# 预热心跳周期（秒）。必须 ≪ OCR_PREWARM_STALE_SEC（默认 300），否则评标侧的 in-flight oracle
# 会在两次心跳之间把真在途的预热误判成僵尸 running。
PREWARM_TOUCH_INTERVAL_SEC = 60.0


async def _heartbeat_loop(touch: Callable[[], None]) -> None:
    """立即刷一次 doc 行 updated_at，此后按周期刷，直到被取消。

    **首次立即执行**是关键（review F2）：心跳覆盖的窗口必须从"排队等上传 OCR 名额"就开始——
    前一个大标占满名额时，后来者可能排队数百秒，期间没有心跳就会被判 stale → 评标另起 inline
    OCR → 双跑复活。心跳自身失败只记 debug：它是可观测性设施，不能反过来打断 OCR。
    """
    while True:
        try:
            await asyncio.to_thread(touch)
        except Exception:
            logger.debug("prewarm heartbeat touch failed", exc_info=True)
        await asyncio.sleep(PREWARM_TOUCH_INTERVAL_SEC)


async def run_prewarm_with_heartbeat(
    func: Callable[..., _T], case_path: str, *, purpose: str | None, touch: Callable[[], None]
) -> _T:
    """跑一次目录预热 OCR：全程 doc 级心跳 + 上传并发闸 + 命名 OCR 池（KD4/KD5 的调度归属地）。

    时序：起心跳（立即 touch）→ 排队取上传 OCR 名额 → 在命名池跑 ``func`` → 停心跳。
    排队与识别**都**在心跳覆盖内，评标侧据此判"预热确实在途"。

    Args:
        func: 同步预热入口（``pipeline.prewarm_and_report``）。
        case_path: 文件目录。
        purpose: OCR 场景提示。
        touch: 刷新本 doc 行 updated_at 的同步函数。

    Returns:
        ``func`` 的返回值。
    """
    ticker = asyncio.create_task(_heartbeat_loop(touch))
    try:
        async with get_upload_ocr_semaphore():
            return await run_in_ocr_executor(func, case_path, purpose=purpose)
    finally:
        ticker.cancel()
        with suppress(asyncio.CancelledError):
            await ticker


def track_upload_ocr_task(task: asyncio.Task[None], project_id: str | None = None) -> None:
    """留强引用防 fire-and-forget OCR 任务被 GC 回收；done 时自清（P1-2）。

    R7-#1：同时按 project_id 分桶，供删项目时定向 cancel（停 OCR）。

    Args:
        task: 后台 OCR 任务。
        project_id: 所属招标项目；None 则仅入全局集（不参与 per-project cancel）。
    """
    _UPLOAD_OCR_TASKS.add(task)
    task.add_done_callback(_UPLOAD_OCR_TASKS.discard)
    if project_id:
        bucket = _PROJECT_OCR_TASKS.setdefault(project_id, set())
        bucket.add(task)

        def _discard_from_project(done: asyncio.Task[None]) -> None:
            remaining = _PROJECT_OCR_TASKS.get(project_id)
            if remaining is None:
                return
            remaining.discard(done)
            if not remaining:
                _PROJECT_OCR_TASKS.pop(project_id, None)

        task.add_done_callback(_discard_from_project)


def cancel_project_ocr_tasks(project_id: str) -> int:
    """R7-#1：取消某项目所有在跑的上传 OCR 任务（删项目时调用，"停止 OCR 服务"）。

    Args:
        project_id: 招标项目标识。

    Returns:
        实际请求取消的任务数（已完成的不计）。
    """
    tasks = _PROJECT_OCR_TASKS.get(project_id)
    if not tasks:
        return 0
    cancelled = 0
    for task in list(tasks):
        if not task.done():
            task.cancel()
            cancelled += 1
    return cancelled
