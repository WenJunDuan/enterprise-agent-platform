"""Tender 价格横比（Phase 2：多家比选 / 排名 / 推荐中标人）：``/projects/{id}/compare``。

D2（design T4）从原 912 行 ``routes/tender.py`` 按 banner 分节拆出（纯路由分组，业务逻辑
已下沉 ``server.tender.compare_worker``）。``_current_compare_signature`` 也供
``server.routes.tender.projects`` 的项目详情端点判断 compare 是否 stale。
"""

from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException

from server.routes.deps import verify_tenant
from server.routes.tender import router
from server.routes.tender.tasks import TenderSubmitAcceptedResponse
from server.stores.request_store import new_request_id
from server.stores.tender_compare_store import compute_input_signature, get_compare_result, is_stale
from server.stores.tender_project_store import get_project
from server.tender.compare_worker import collect_compare_input, has_active_compare, schedule_compare_task


def _current_compare_signature(tenant: str, project_id: str, project: dict[str, Any]) -> str | None:
    """当前 completed 投标人集的输入签名；不足 2 家返回 None（无法 compare）。"""
    collected = collect_compare_input(tenant, project_id, project)
    if collected is None:
        return None
    _input, signature = collected
    return compute_input_signature(signature.input_result_ids, signature.criteria_hash)


@router.post("/projects/{project_id}/compare", response_model=TenderSubmitAcceptedResponse)
async def trigger_tender_compare(
    project_id: str,
    authorization: str | None = Header(None),
) -> TenderSubmitAcceptedResponse:
    """触发招标项目价格横比（异步）。要求该招标下 ≥2 家投标人已完成评标。"""
    tenant = verify_tenant(authorization)
    project = get_project(project_id, tenant)
    if project is None:
        raise HTTPException(status_code=404, detail="Tender project not found")
    if _current_compare_signature(tenant, project_id, project) is None:
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
    """取招标项目最新横比结果；追加投标 / 重评后参与集变化则标 ``stale=true``（codex P2.6）。"""
    tenant = verify_tenant(authorization)
    project = get_project(project_id, tenant)
    if project is None:
        raise HTTPException(status_code=404, detail="Tender project not found")
    record = get_compare_result(project_id, tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="尚未生成横比结果，请先触发 compare")
    current_sig = _current_compare_signature(tenant, project_id, project)
    stale = current_sig is None or is_stale(record.get("input_signature"), current_sig)
    return {
        "project_id": project_id,
        "result": record["payload"],
        "stale": stale,
        "computed_at": record.get("computed_at"),
        "input_result_ids": record.get("input_result_ids"),
    }
