"""Background execution for tender price-comparison (project-level cross-bid).

收集招标项目下所有 completed 投标人结论(``results``)→校验各家 criteria 一致→组装
``/tender-compare`` 输入→调命令(``archive_to_results=False``，不污染 ``results``，codex P1.1)
→把横比结论存 ``tender_compare_results``(带输入签名供 stale，codex P2.6)。

任务状态机走独立的 ``tender_compare_tasks`` 表(codex P1.2)，与单投标人评标任务隔离。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from server.common.command_adapter import run_command_json
from server.platform.logging_setup import logging_context
from server.stores.request_store import utc_now
from server.stores.result_store import list_results_by_project
from server.stores.session_store import new_conversation_id
from server.stores.tender_compare_store import (
    CompareSignature,
    compute_criteria_hash,
    upsert_compare_result,
)
from server.stores.tender_compare_task_store import upsert_compare_task
from server.stores.tender_project_store import get_project

logger = logging.getLogger(__name__)

COMPARE_SCHEMA_NAME = "tender/compare-result.schema.json"
COMPARE_TIMEOUT_SEC = float(os.getenv("TENDER_COMPARE_TIMEOUT_SEC", "300"))

_COMPARE_SEMAPHORE = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_COMPARE", "1")))
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def _track(task: asyncio.Task[None]) -> None:
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


def collect_compare_input(
    tenant: str, project_id: str, project: dict[str, Any]
) -> tuple[dict[str, Any], CompareSignature] | None:
    """收集 completed 投标人评分事实 → ``/tender-compare`` 输入 + 输入签名。

    返回 None 表示参与的 completed 投标人 < 2（compare 无意义，调用方回 400）。
    各家 criteria 取出算 hash 作一致性指纹（codex P1.4/P2.6）；具体一致性判定交 Claude。
    """
    rows = list_results_by_project(tenant, project_id, limit=200)
    bidders: list[dict[str, Any]] = []
    result_ids: list[str] = []
    criteria_seen: Any = None
    price_item: Any = None
    for row in rows:
        # list_results_by_project 的 payload 列是未解析 JSON 字符串（SELECT *），需 loads。
        payload = row.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (TypeError, ValueError):
                continue
        response = payload.get("response") if isinstance(payload, dict) else None
        if not isinstance(response, dict):
            continue
        extracted = response.get("extracted_data") or {}
        if criteria_seen is None and extracted.get("criteria"):
            criteria_seen = extracted["criteria"]
            price_item = _find_price_item(criteria_seen)
        result_ids.append(str(row["request_id"]))
        bidders.append(
            {
                "claim_id": response.get("claim_id") or row.get("claim_id"),
                "bid_price": extracted.get("bid_price"),
                "scoring": extracted.get("scoring", []),
                "verdict": response.get("verdict"),
            }
        )
    if len(bidders) < 2:
        return None
    compare_input = {
        "project_id": project_id,
        "method": (criteria_seen or {}).get("method") if isinstance(criteria_seen, dict) else None,
        "funding_type": project.get("funding_type") or "unknown",
        "control_price": project.get("control_price"),
        "criteria_price_item": price_item,
        "bidders": bidders,
    }
    signature = CompareSignature(
        input_result_ids=result_ids,
        criteria_hash=compute_criteria_hash(criteria_seen),
    )
    return compare_input, signature


def _find_price_item(criteria: Any) -> Any:
    """从 criteria.items 找价格项（tag=requires_cross_bid_comparison）。"""
    if not isinstance(criteria, dict):
        return None
    for item in criteria.get("items", []):
        if isinstance(item, dict) and item.get("tag") == "requires_cross_bid_comparison":
            return {
                "item": item.get("item"),
                "max": item.get("max"),
                "scoring_rule": item.get("scoring_rule"),
            }
    return None


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
            await asyncio.to_thread(
                upsert_compare_result,
                project_id=project_id,
                tenant=tenant,
                payload=payload if isinstance(payload, dict) else {"raw": payload},
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
            row["error_detail"] = str(exc)
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
    """Fire-and-forget compare task（tracked，防 GC）。"""
    task = asyncio.create_task(
        execute_compare_task(request_id=request_id, tenant=tenant, project_id=project_id)
    )
    _track(task)
