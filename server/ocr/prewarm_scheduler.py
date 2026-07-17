"""OCR prewarm task scheduling: concurrency cap + GC-safe tracking + per-project cancel.

S3 抽离：从 ``routes/tender.py`` 下沉的**通用 OCR 编排基建**——上传即 OCR 的并发上限信号量、
防 fire-and-forget 任务被 GC 静默回收的强引用集、按 ``project_id`` 分桶以便删项目时定向取消。
属 ocr feature 层的通用能力，由同为 feature 层的 ``server.tender.doc_pipeline``（D2 从
``routes/tender_doc_pipeline.py`` 移入）消费；本模块只依赖 stdlib，不引 stores/routes，避免层级反转。
"""

from __future__ import annotations

import asyncio
import os

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


def get_upload_ocr_semaphore() -> asyncio.Semaphore:
    """Return the shared upload-OCR concurrency semaphore (P1-2 并发闸)."""
    return _UPLOAD_OCR_SEMAPHORE


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
