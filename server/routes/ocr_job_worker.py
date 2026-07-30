"""Background task execution for OCR streaming jobs (D9 streaming-ocr T3).

Harness mirrors ``server.routes.audit_worker``: admission cap, semaphore gating,
run, three-state (``running`` → ``completed``/``failed``) TaskStore upsert. Isolated
here so the route handlers in ``ocr_jobs.py`` stay focused on HTTP concerns.

Path derivation (G2②, trust boundary): the job's working directory is never taken
from a client-supplied string. It is always recomputed from ``tenant`` (already
verified by ``verify_tenant``) and ``request_id`` (server-generated) via
``build_case_dir`` — the same helper ``materialize_ocr_upload`` used to create it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from server.ocr.pipeline import OCR_JOB_UNITS_FILENAME, count_pending_files, extract_dir
from server.platform.logging_setup import logging_context
from server.routes.upload_helpers import build_case_dir, serialize_case_path
from server.stores.ocr_job_store import update_ocr_job_progress, upsert_ocr_job
from server.stores.request_store import utc_now

logger = logging.getLogger(__name__)

# 单个 OCR job 硬超时（秒）。仅兜底防无限挂起，理由同 AUDIT_TIMEOUT_SEC（audit_worker.py）：
# 识别工作线程不可取消，超时只是让任务记录不再无限期挂着 running，不代表底层线程被真正终止。
OCR_JOB_TIMEOUT_SEC = float(os.getenv("OCR_JOB_TIMEOUT_SEC", "600"))

# 同时执行的 OCR job 上限（理由同 MAX_CONCURRENT_AUDITS：每单跑线程池 OCR，CPU/IO 较重）。
MAX_CONCURRENT_OCR_JOBS = int(os.getenv("MAX_CONCURRENT_OCR_JOBS", "2"))
_OCR_JOB_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_OCR_JOBS)

# 准入上限（理由同 MAX_PENDING_AUDITS）：在途 job 数达上限时 submit 直接 503，不再无界接单。
MAX_PENDING_OCR_JOBS = int(os.getenv("MAX_PENDING_OCR_JOBS", "50"))

# round4 F5 先例：裸 asyncio.create_task 不留引用会被 GC 静默回收。留强引用集，完成即自清；
# 集合大小兼作"在途任务数"供准入闸用。
_BACKGROUND_OCR_JOB_TASKS: set[asyncio.Task[None]] = set()


def _track_task(task: asyncio.Task[None]) -> None:
    """留强引用防 fire-and-forget 任务被 GC 回收；done 时自清（round4 F5 先例）。"""
    _BACKGROUND_OCR_JOB_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_OCR_JOB_TASKS.discard)


def admission_available() -> bool:
    """在途任务数低于上限才接新单，否则路由回 503（防 queued 无界堆积，round4 F5 先例）。"""
    return len(_BACKGROUND_OCR_JOB_TASKS) < MAX_PENDING_OCR_JOBS


def _progress_json(done: int, total: int) -> str:
    """G2①：progress_message 固定编码为 ``{"done": <int>, "total": <int>}``。"""
    return json.dumps({"done": done, "total": total}, ensure_ascii=False)


def _append_unit_locked(units_path: Path, unit: dict[str, Any]) -> None:
    """Append one unit event as a JSON line. Caller must hold the per-job lock."""
    line = json.dumps(unit, ensure_ascii=False)
    with units_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _run_job_sync(
    *, request_id: str, case_dir: Path, run_seal: bool, total: int
) -> None:
    """同步跑 extract_dir，逐单元 append units.jsonl + 更新 progress。

    经调用方 ``asyncio.to_thread`` 移出事件循环执行。``extract_dir`` 多文件并行时会从多个
    worker 线程并发触发 ``on_unit_complete`` —— 用 per-job ``threading.Lock`` 串行化 append +
    计数，append-only 天然单调递增不回退（T3 验收：并发 append 完整性 + partial 单调递增）。
    """
    units_path = case_dir / OCR_JOB_UNITS_FILENAME
    lock = threading.Lock()
    done = 0

    def _on_unit_complete(unit: dict[str, Any]) -> None:
        # progress 的 DB 写必须留在锁内、与 done 自增同一临界区：若移到锁外，并发线程释放锁的
        # 时序与其 DB 写入时序可能不一致（线程 A done=1 释放锁后被线程 B done=2 抢先写库），
        # 写入顺序倒置会让轮询方短暂看到 done 回退——违反"partial 单调递增不回退"（T3 验收）。
        nonlocal done
        with lock:
            _append_unit_locked(units_path, unit)
            done += 1
            update_ocr_job_progress(request_id, _progress_json(done, total))
            if unit.get("status") == "error" and unit.get("page") is None:
                payload = unit.get("payload")
                detail = payload.get("error") if isinstance(payload, dict) else None
                raise RuntimeError(str(detail or "OCR file extraction failed"))

    extract_dir(str(case_dir), run_seal=run_seal, on_unit_complete=_on_unit_complete)


def _upsert(request_id: str, tenant: str, case_dir: Path, **fields: Any) -> None:
    """薄封装：补齐 request_id/tenant/mode/source_mode/case_path 等公共列（DRY，见下方三态调用）。"""
    upsert_ocr_job(
        {
            "request_id": request_id,
            "tenant": tenant,
            "mode": "upload",
            "source_mode": "upload",
            "case_path": serialize_case_path(case_dir),
            **fields,
        }
    )


def _mark_running(
    request_id: str, tenant: str, case_dir: Path, *, progress_total: int, started_at: str | None = None
) -> None:
    """running 态 upsert（初始占位 + total 确定后各调一次，见 ``_execute_inner``）。"""
    fields: dict[str, Any] = {
        "status": "running",
        "error_detail": None,
        "progress_message": _progress_json(0, progress_total),
        "updated_at": utc_now(),
    }
    if started_at is not None:
        fields["started_at"] = started_at
    _upsert(request_id, tenant, case_dir, **fields)


def _mark_completed(
    request_id: str, tenant: str, case_dir: Path, *, progress_total: int | None = None
) -> None:
    """completed 态 upsert。``progress_total`` 只在 F4 空目录直落终态时传（0/0）；正常路径下
    最后一次单元事件已把 progress_message 写到 done==total，此处不覆盖（合并语义保留）。"""
    finished_at = utc_now()
    fields: dict[str, Any] = {
        "status": "completed",
        "error_detail": None,
        "finished_at": finished_at,
        "updated_at": finished_at,
    }
    if progress_total is not None:
        fields["progress_message"] = _progress_json(0, progress_total)
    _upsert(request_id, tenant, case_dir, **fields)


def _mark_failed(request_id: str, tenant: str, case_dir: Path, *, error_detail: str) -> None:
    """failed 态 upsert。F5：不动 progress_message/units.jsonl，已产出的 partial 原样保留。"""
    finished_at = utc_now()
    _upsert(
        request_id,
        tenant,
        case_dir,
        status="failed",
        error_detail=error_detail,
        finished_at=finished_at,
        updated_at=finished_at,
    )


async def _run_with_timeout(*, request_id: str, case_dir: Path, run_seal: bool, total: int) -> None:
    await asyncio.wait_for(
        asyncio.to_thread(
            _run_job_sync, request_id=request_id, case_dir=case_dir, run_seal=run_seal, total=total
        ),
        timeout=OCR_JOB_TIMEOUT_SEC,
    )


async def _execute_inner(*, request_id: str, tenant: str, run_seal: bool) -> None:
    case_dir = build_case_dir(tenant, "ocr", request_id)
    with logging_context(request_id=request_id, tenant=tenant):
        await asyncio.to_thread(
            _mark_running, request_id, tenant, case_dir, progress_total=0, started_at=utc_now()
        )
        total = await asyncio.to_thread(count_pending_files, str(case_dir))
        if total == 0:
            # F4：空目录/全排除 → 立即 completed，不悬空等一个永远不会来的单元事件。
            await asyncio.to_thread(_mark_completed, request_id, tenant, case_dir, progress_total=0)
            return

        await asyncio.to_thread(_mark_running, request_id, tenant, case_dir, progress_total=total)
        try:
            await _run_with_timeout(
                request_id=request_id, case_dir=case_dir, run_seal=run_seal, total=total
            )
            await asyncio.to_thread(_mark_completed, request_id, tenant, case_dir)
        except asyncio.TimeoutError:
            logger.warning(
                "ocr_job_timeout",
                extra={
                    "request_id": request_id,
                    "tenant": tenant,
                    "route": "/ocr/jobs",
                    "timeout_sec": OCR_JOB_TIMEOUT_SEC,
                },
            )
            timeout_detail = f"OCR 任务超时：超过 {int(OCR_JOB_TIMEOUT_SEC)}s 未完成，请稍后重试"
            await asyncio.to_thread(_mark_failed, request_id, tenant, case_dir, error_detail=timeout_detail)
        except Exception as exc:
            logger.exception(
                "ocr_job_failed",
                extra={"request_id": request_id, "tenant": tenant, "route": "/ocr/jobs"},
            )
            await asyncio.to_thread(_mark_failed, request_id, tenant, case_dir, error_detail=str(exc))


async def execute_ocr_job(*, request_id: str, tenant: str, run_seal: bool = False) -> None:
    """Gate on the concurrency semaphore, then run the OCR job."""
    async with _OCR_JOB_SEMAPHORE:
        await _execute_inner(request_id=request_id, tenant=tenant, run_seal=run_seal)


def schedule_ocr_job(*, request_id: str, tenant: str, run_seal: bool = False) -> None:
    """Fire-and-forget: schedule the OCR job as a tracked asyncio background task."""
    task = asyncio.create_task(
        execute_ocr_job(request_id=request_id, tenant=tenant, run_seal=run_seal)
    )
    _track_task(task)  # round4 F5 先例：留引用防 GC + 计入在途（准入闸）
