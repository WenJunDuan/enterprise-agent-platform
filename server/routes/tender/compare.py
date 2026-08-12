"""Tender 价格横比（Phase 2：多家比选 / 排名 / 推荐中标人）：``/projects/{id}/compare``。

D2（design T4）从原 912 行 ``routes/tender.py`` 按 banner 分节拆出（纯路由分组，业务逻辑
已下沉 ``server.tender.compare_worker`` / ``compare_input``）。``_current_compare_signature``
也供 ``server.routes.tender.projects`` 的项目详情端点判断 compare 是否 stale。

KD2：GET **恒 200**，返回 ``status`` 生命周期（none/pending/running/failed/ready）。旧实现无结果
即 404、失败态只写任务表无任何路由暴露 → 前端永远轮询 null，横比失败对用户完全不可见。
"""

from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException

from server.routes.deps import verify_tenant
from server.routes.tender import router
from server.routes.tender.tasks import TenderSubmitAcceptedResponse
from server.stores.request_store import new_request_id
from server.stores.tender_compare_store import get_compare_result, is_stale
from server.stores.tender_compare_task_store import list_compare_tasks
from server.stores.tender_project_store import get_project
from server.tender.compare_guard import sanitize_error_detail
from server.tender.compare_worker import (
    current_compare_signature,
    has_active_compare,
    schedule_compare_task,
)

_ACTIVE_TASK_STATUS = {"accepted": "pending", "running": "running"}


def _current_compare_signature(tenant: str, project_id: str, project: dict[str, Any]) -> str | None:
    """当前 completed 投标人集的输入签名；不足 2 家返回 None（无法 compare）。

    薄别名：签名计算已下沉 ``compare_worker.current_compare_signature``（自动触发与本路由
    共用同一实现）；本名保留是因为 ``routes.tender.projects`` 已按此名 import。
    """
    return current_compare_signature(tenant, project_id, project)


@router.post("/projects/{project_id}/compare", response_model=TenderSubmitAcceptedResponse)
async def trigger_tender_compare(
    project_id: str,
    authorization: str | None = Header(None),
) -> TenderSubmitAcceptedResponse:
    """手动触发 / 重跑招标项目价格横比（异步）。

    KD2 后横比由评标终态自动入队，本端点保留作**重新横比**入口（前端"重新横比"按钮、
    自动触发被跳过时的兜底）。要求该招标下 ≥2 家投标人已完成评标。
    """
    tenant = verify_tenant(authorization)
    project = get_project(project_id, tenant)
    if project is None:
        raise HTTPException(status_code=404, detail="Tender project not found")
    if current_compare_signature(tenant, project_id, project) is None:
        raise HTTPException(status_code=400, detail="参与横比的已完成投标人不足 2 家")
    # cc C1：防并发双击重复算（同 project 已有在途 compare 则拒）。
    if has_active_compare(tenant, project_id):
        raise HTTPException(status_code=409, detail="该招标项目横比正在进行中，请稍后查看结果")
    request_id = new_request_id()
    schedule_compare_task(request_id=request_id, tenant=tenant, project_id=project_id)
    return TenderSubmitAcceptedResponse(
        request_id=request_id,
        status="accepted",
        mode="compare",
        task_status_url=f"/tender/projects/{project_id}/compare",
    )


@router.get("/projects/{project_id}/compare")
async def get_tender_compare(
    project_id: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """横比生命周期查询（恒 200）：``none/pending/running/failed/ready`` + 结果 + stale。

    在途任务优先于已有结果，使"有旧结果且正在重算"能同时展示旧结果与进行中状态；
    失败时透传**脱敏后**的 error_detail（无 stack trace / 无服务器路径）。
    """
    tenant = verify_tenant(authorization)
    project = get_project(project_id, tenant)
    if project is None:
        raise HTTPException(status_code=404, detail="Tender project not found")
    record = get_compare_result(project_id, tenant)
    status, error_detail = _compare_status(tenant, project_id, record is not None)
    stale = False
    if record is not None:
        current_sig = _current_compare_signature(tenant, project_id, project)
        stale = current_sig is None or is_stale(record.get("input_signature"), current_sig)
    return {
        "project_id": project_id,
        "status": status,
        "error_detail": error_detail,
        "result": record["payload"] if record else None,
        "stale": stale,
        "computed_at": record.get("computed_at") if record else None,
        "input_result_ids": record.get("input_result_ids") if record else None,
    }


def _compare_status(tenant: str, project_id: str, has_result: bool) -> tuple[str, str | None]:
    """据任务表 + 结果表推导生命周期状态与失败原因（脱敏）。

    优先级：在途（pending/running）> 已有结果（ready）> 最近一次失败（failed）> none。
    ``list_compare_tasks`` 按更新时间倒序，故首个 failed 即最近一次失败。
    """
    tasks = list_compare_tasks(tenant, group_id=project_id, limit=50)
    for task in tasks:
        active = _ACTIVE_TASK_STATUS.get(str(task.get("status")))
        if active:
            return active, None
    if has_result:
        return "ready", None
    for task in tasks:
        if task.get("status") == "failed":
            return "failed", sanitize_error_detail(task.get("error_detail"))
    return "none", None
