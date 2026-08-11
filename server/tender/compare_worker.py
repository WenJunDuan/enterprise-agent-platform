"""Background execution for tender price-comparison (project-level cross-bid).

本模块只管**任务生命周期**：并发闸 → 组装输入（判据在 ``server.tender.compare_input``）→
调命令(``archive_to_results=False``，不污染 ``results``，codex P1.1) → 服务端护栏兜底 →
把横比结论存 ``tender_compare_results``(带输入签名供 stale，codex P2.6)。

任务状态机走独立的 ``tender_compare_tasks`` 表(codex P1.2)，与单投标人评标任务隔离。
横比的触发不再依赖前端在场：评标 worker 每家终态后调 ``maybe_schedule_compare``（KD2）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from server.common.command_adapter import run_command_json
from server.platform.logging_setup import logging_context
from server.stores.request_store import new_request_id, utc_now
from server.stores.session_store import new_conversation_id
from server.stores.tender_compare_store import (
    compute_input_signature,
    get_compare_result,
    upsert_compare_result,
)
from server.stores.tender_compare_task_store import list_compare_tasks, upsert_compare_task
from server.stores.tender_project_store import get_project
from server.tender.compare_guard import COMPARE_TIMEOUT_REASON, enforce_compare_guardrails
from server.tender.compare_input import collect_compare_input

logger = logging.getLogger(__name__)

COMPARE_SCHEMA_NAME = "tender/compare-result.schema.json"
COMPARE_TIMEOUT_SEC = float(os.getenv("TENDER_COMPARE_TIMEOUT_SEC", "300"))

_COMPARE_SEMAPHORE = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_COMPARE", "1")))
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def _track(task: asyncio.Task[None]) -> None:
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


def has_active_compare(tenant: str, project_id: str) -> bool:
    """该招标项目下是否已有在途(accepted/running) compare 任务（防并发双击重复算，cc C1）。"""
    return any(
        t.get("status") in {"accepted", "running"}
        for t in list_compare_tasks(tenant, group_id=project_id, limit=50)
    )


def current_compare_signature(
    tenant: str, project_id: str, project: dict[str, Any]
) -> str | None:
    """当前参与集的输入签名；池内结论不足 2 条（无法 compare）时 None。"""
    collected = collect_compare_input(tenant, project_id, project)
    if collected is None:
        return None
    _input, signature = collected
    return compute_input_signature(signature.input_result_ids, signature.criteria_hash)


def compare_recompute_needed(tenant: str, project_id: str) -> bool:
    """当前参与集是否需要（重新）横比 —— **只读判定，可在工作线程执行**。

    两个闸：参与集 ≥2 家可组池；输入签名相对已存结果**有变**（签名未变说明现有横比结果
    仍对应当前参与集，重算是纯浪费）。"在途去重"不在这里判——那一步必须与"写 accepted 行"
    在同一线程内不可分割地做（见 ``_schedule_if_idle``），放这里会留 TOCTOU 窗口。

    Args:
        tenant: 租户作用域。
        project_id: 招标项目 ID。
    """
    project = get_project(project_id, tenant)
    if project is None:
        return False
    signature = current_compare_signature(tenant, project_id, project)
    if signature is None:
        return False
    stored = get_compare_result(project_id, tenant)
    return stored is None or stored.get("input_signature") != signature


async def maybe_schedule_compare(tenant: str, project_id: str) -> str | None:
    """评标终态后由服务端自动判定是否入队横比（KD2：触发不再依赖前端在场）。

    **必须在事件循环线程 await**：重活（读全池结论、算签名）经 ``to_thread`` 移出 loop，
    但真正的"查在途 + 写 accepted 行 + 起协程"三步留在 loop 线程同步做——三步之间没有
    await 断点，故 check-then-act 天然原子（单线程 loop），也才拿得到 running loop
    去 ``create_task``（旧实现整段进 to_thread，``create_task`` 在无 loop 的工作线程
    必抛 RuntimeError，且 accepted 行已写下 → 项目被幽灵任务永久锁死）。

    Args:
        tenant: 租户作用域。
        project_id: 招标项目 ID。

    Returns:
        新建的 compare request_id；未满足触发条件时 None。
    """
    if not await asyncio.to_thread(compare_recompute_needed, tenant, project_id):
        return None
    return _schedule_if_idle(tenant, project_id)


def _schedule_if_idle(tenant: str, project_id: str) -> str | None:
    """loop 线程内同步完成"查在途 → 入队"（无 await 断点 = 并发双触发只会有一个入队）。"""
    if has_active_compare(tenant, project_id):
        return None
    request_id = new_request_id()
    schedule_compare_task(request_id=request_id, tenant=tenant, project_id=project_id)
    logger.info(
        "tender_compare_auto_scheduled",
        extra={"project_id": project_id, "tenant": tenant or "default",
               "request_id": request_id},
    )
    return request_id


async def _run_compare(*, request_id: str, tenant: str, compare_input: dict[str, Any]):
    # archive_to_results=False：compare 结论不进 results 表（codex P1.1）。
    return await run_command_json(
        "tender-compare",
        json.dumps(compare_input, ensure_ascii=False),
        schema_name=COMPARE_SCHEMA_NAME,
        request_id=request_id,
        tenant=tenant,
        archive_to_results=False,
        conversation_id=new_conversation_id(),
    )


async def execute_compare_task(
    *,
    request_id: str,
    tenant: str,
    project_id: str,
) -> None:
    """Gate on semaphore, run compare, persist to tender_compare_results."""
    async with _COMPARE_SEMAPHORE:
        await _execute_inner(request_id=request_id, tenant=tenant, project_id=project_id)


async def _execute_inner(*, request_id: str, tenant: str, project_id: str) -> None:
    started_at = utc_now()
    with logging_context(request_id=request_id, tenant=tenant):
        await asyncio.to_thread(
            upsert_compare_task,
            _task_row(request_id, tenant, project_id, "running", "横比计算中", started_at),
        )
        try:
            project = get_project(project_id, tenant)
            collected = collect_compare_input(tenant, project_id, project or {})
            if collected is None:
                raise ValueError("参与横比的已完成投标人不足 2 家")
            compare_input, signature = collected
            payload, _meta = await asyncio.wait_for(
                _run_compare(request_id=request_id, tenant=tenant, compare_input=compare_input),
                timeout=COMPARE_TIMEOUT_SEC,
            )
            stored = payload if isinstance(payload, dict) else {"raw": payload}
            # codex P2.4：以服务端 project_id 为准，杜绝 Claude 回填错 project_id 致 GET 自相矛盾。
            if isinstance(stored, dict):
                stored["project_id"] = project_id
                enforce_compare_guardrails(stored, compare_input)
            await asyncio.to_thread(
                upsert_compare_result,
                project_id=project_id,
                tenant=tenant,
                payload=stored,
                signature=signature,
            )
            finished = utc_now()
            await asyncio.to_thread(
                upsert_compare_task,
                _task_row(request_id, tenant, project_id, "completed", "横比完成", finished, finished),
            )
        except Exception as exc:  # noqa: BLE001 - 统一落失败态，详情进任务记录
            logger.exception(
                "tender_compare_failed",
                extra={"request_id": request_id, "tenant": tenant, "project_id": project_id},
            )
            finished = utc_now()
            row = _task_row(request_id, tenant, project_id, "failed", "横比失败", finished, finished)
            # 超时 str(exc) 是空串，用户会看到"失败但没说为什么"；给一句已登记的业务原因
            # （compare_guard.KNOWN_BUSINESS_REASONS 白名单内，可原文回前端）。
            row["error_detail"] = (
                COMPARE_TIMEOUT_REASON if isinstance(exc, asyncio.TimeoutError) else str(exc)
            )
            await asyncio.to_thread(upsert_compare_task, row)


def _task_row(
    request_id: str,
    tenant: str,
    project_id: str,
    status: str,
    progress: str,
    updated_at: str,
    finished_at: str | None = None,
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "tenant": tenant,
        "status": status,
        "mode": "compare",
        "source_mode": "compare",
        "case_path": "-",
        "group_id": project_id,
        "progress_message": progress,
        "started_at": updated_at if status == "running" else None,
        "finished_at": finished_at,
        "updated_at": updated_at,
    }


def schedule_compare_task(*, request_id: str, tenant: str, project_id: str) -> None:
    """Fire-and-forget compare task（tracked，防 GC）。**只能在事件循环线程调用。**

    先同步建 accepted 记录，使紧随的并发请求能经 ``has_active_compare`` 查到在途 → 防重（cc C1）。
    "建 accepted 行"与"起协程"必须**同成败**：起协程失败（无 running loop 等）时把该行落
    failed 再抛，否则 accepted 幽灵行会让 ``has_active_compare`` 恒 True、项目永久卡在
    "横比进行中"，自动与手动触发全被闸死。
    """
    upsert_compare_task(
        _task_row(request_id, tenant, project_id, "accepted", "横比任务已提交", utc_now())
    )
    try:
        task = asyncio.create_task(
            execute_compare_task(request_id=request_id, tenant=tenant, project_id=project_id)
        )
    except RuntimeError as exc:
        finished = utc_now()
        row = _task_row(
            request_id, tenant, project_id, "failed", "横比未能启动", finished, finished
        )
        row["error_detail"] = f"compare task not scheduled: {exc}"
        upsert_compare_task(row)
        raise
    _track(task)
