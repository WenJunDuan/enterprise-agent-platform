"""Tender 招标项目实体资源：CRUD + 多投标人名册聚合 + 结果回看（``/projects*``）。

D2（design T4）从原 912 行 ``routes/tender.py`` 按 banner 分节拆出（纯路由分组，业务逻辑
不变）。项目下追加评标（``/projects/{id}/evaluate``）复用
``server.routes.tender.tasks._submit_bid_evaluation``；项目详情的 compare 联动复用
``server.routes.tender.compare._current_compare_signature``。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

from fastapi import Header, HTTPException, Query, Request
from pydantic import BaseModel

from server.core import enrich_audit_decision
from server.ocr.prewarm_scheduler import cancel_project_ocr_tasks as _cancel_project_ocr_tasks
from server.routes.deps import verify_tenant
from server.routes.tender import router
from server.routes.tender.compare import _current_compare_signature
from server.routes.tender.tasks import TenderSubmitAcceptedResponse, _submit_bid_evaluation
from server.routes.upload_helpers import remove_project_submission_dir, remove_submission_dir
from server.stores.result_store import get_result_payload_by_request_id, list_results_by_project
from server.stores.tender_compare_store import get_compare_result, is_stale
from server.stores.tender_project_store import (
    DEFAULT_PROJECT_SCENARIO,
    count_active_bids,
    delete_project_cascade,
    get_or_create_project,
    get_project,
    list_projects,
)
from server.stores.tender_task_store import list_tender_tasks_by_project
from server.tender.compare_worker import has_active_compare

logger = logging.getLogger(__name__)

TenderScenario = Literal["bidder_self_check", "expert_assist", "post_eval_monitor"]


class TenderProjectCreateRequest(BaseModel):
    scenario: TenderScenario = DEFAULT_PROJECT_SCENARIO
    tender_no: str | None = None
    title: str | None = None
    tenderee: str | None = None
    method: str | None = None
    control_price: str | None = None
    funding_type: str | None = None  # state_funded/other/unknown（compare 推荐终局护栏）


class TenderProjectResponse(BaseModel):
    project_id: str
    scenario: TenderScenario
    tender_no: str | None = None
    title: str | None = None
    tenderee: str | None = None
    method: str | None = None
    control_price: str | None = None
    funding_type: str | None = None
    status: str
    created_at: str
    updated_at: str


class TenderProjectBid(BaseModel):
    request_id: str
    claim_id: str | None = None
    status: str  # completed / running / accepted / failed
    verdict: str | None = None


class TenderProjectDetailResponse(TenderProjectResponse):
    bidder_count: int
    bids: list[TenderProjectBid]
    recommended_bidder: str | None = None  # 仅 compare 已跑、非 stale、有终局 recommended 时填
    compare_stale: bool = False  # compare 已跑但参与集已变（需重跑）


def _public_project(record: dict[str, Any]) -> TenderProjectResponse:
    return TenderProjectResponse(
        project_id=str(record["project_id"]),
        scenario=record.get("scenario") or DEFAULT_PROJECT_SCENARIO,
        tender_no=record.get("tender_no"),
        title=record.get("title"),
        tenderee=record.get("tenderee"),
        method=record.get("method"),
        control_price=record.get("control_price"),
        funding_type=record.get("funding_type"),
        status=str(record["status"]),
        created_at=str(record["created_at"]),
        updated_at=str(record["updated_at"]),
    )


def _project_bid_roster(tenant: str, project_id: str) -> list[TenderProjectBid]:
    """招标项目投标人名册 = ``results.project_id``(已完成,durable) ∪ 活跃 ``tender_tasks``(在途)。

    删任务不丢已完成投标人（结论仍在 results，codex P1.1）；按 request_id 去重，优先 results。
    """
    bids: list[TenderProjectBid] = []
    seen: set[str] = set()
    for r in list_results_by_project(tenant, project_id):
        rid = str(r["request_id"])
        seen.add(rid)
        bids.append(
            TenderProjectBid(
                request_id=rid,
                claim_id=r.get("claim_id"),
                status="completed",
                verdict=r.get("verdict"),
            )
        )
    for t in list_tender_tasks_by_project(tenant, project_id):
        rid = str(t["request_id"])
        if rid in seen or t.get("status") == "completed":
            continue  # 已在 results / 残留完成态 → 跳过
        bids.append(
            TenderProjectBid(
                request_id=rid,
                claim_id=t.get("claim_id"),
                status=str(t["status"]),
                verdict=None,
            )
        )
    return bids


@router.post("/projects", response_model=TenderProjectResponse)
async def create_tender_project(
    body: TenderProjectCreateRequest,
    authorization: str | None = Header(None),
) -> TenderProjectResponse:
    """建招标项目；get-or-create 幂等（同 tenant+tender_no 已存在则返回现有，codex P1.2）。"""
    tenant = verify_tenant(authorization)
    record = await asyncio.to_thread(
        get_or_create_project,
        tenant=tenant,
        scenario=body.scenario,
        tender_no=body.tender_no,
        title=body.title,
        tenderee=body.tenderee,
        method=body.method,
        control_price=body.control_price,
        funding_type=body.funding_type,
    )
    return _public_project(record)


@router.get("/projects", response_model=list[TenderProjectResponse])
async def list_tender_projects_endpoint(
    authorization: str | None = Header(None),
    status: str | None = Query(None),
    scenario: TenderScenario | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[TenderProjectResponse]:
    tenant = verify_tenant(authorization)
    records = list_projects(
        tenant,
        status=status,
        scenario=scenario,
        limit=limit,
        offset=offset,
    )
    return [_public_project(r) for r in records]


@router.get("/projects/{project_id}", response_model=TenderProjectDetailResponse)
async def get_tender_project_detail(
    project_id: str,
    authorization: str | None = Header(None),
) -> TenderProjectDetailResponse:
    """项目详情 + 投标人名册（合并 results∪活跃 tasks）+ bidder_count + compare 联动。"""
    tenant = verify_tenant(authorization)
    record = get_project(project_id, tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Tender project not found")
    bids = _project_bid_roster(tenant, project_id)
    base = _public_project(record)
    # compare 联动（codex P1.5/P2.6）：recommendedBidder 仅当 compare 已跑、非 stale、
    # 有终局 recommended（非 provisional）时展示——计算不存储，从 compare 结果实时取。
    recommended_bidder: str | None = None
    compare_stale = False
    compare = get_compare_result(project_id, tenant)
    if compare is not None:
        current_sig = _current_compare_signature(tenant, project_id, record)
        compare_stale = current_sig is None or is_stale(compare.get("input_signature"), current_sig)
        payload = compare.get("payload") or {}
        # codex P1.2：必须显式 provisional is False（缺失 ≠ 终局）且 recommended 非空才展示。
        if not compare_stale and payload.get("provisional") is False and payload.get("recommended"):
            recommended_bidder = payload.get("recommended")
    return TenderProjectDetailResponse(
        **base.model_dump(),
        bidder_count=len(bids),
        bids=bids,
        recommended_bidder=recommended_bidder,
        compare_stale=compare_stale,
    )


@router.delete("/projects/{project_id}")
async def delete_tender_project_endpoint(
    project_id: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """删除招标项目及其级联数据（投标任务 / 结论 / 横比 + submission 目录）。

    安全守卫：项目下有 running 投标任务时回 409，避免与执行中的 worker 竞态
    （对齐单任务删除的 idle 守卫）。删成功后逐个清理各投标的 submission 目录。
    """
    tenant = verify_tenant(authorization)
    if get_project(project_id, tenant) is None:
        raise HTTPException(status_code=404, detail="Tender project not found")
    # 守卫：项目下有在途(accepted/running)投标任务 → 拒删（防 worker 把已删项目任务 upsert
    # 成 running 的孤儿竞态，codex P1-1）；有在途价格横比同理（codex P1-2，复用 has_active_compare）。
    if await asyncio.to_thread(count_active_bids, project_id, tenant) > 0:
        raise HTTPException(
            status_code=409,
            detail="项目下仍有在途（已受理/运行中）的评标任务，请等其结束后再删除",
        )
    if await asyncio.to_thread(has_active_compare, tenant, project_id):
        raise HTTPException(
            status_code=409,
            detail="项目下有在途的价格横比任务，请等其结束后再删除",
        )
    # R7-#1：删前先停该项目在跑的上传 OCR（"传错招标文件→删除→停 OCR→重传"诉求）。释放信号量名额，
    # 停掉无谓 OCR 计算；DB 行随级联删除消失，被取消任务的后续写入命中 0 行自然 no-op。
    cancelled_ocr = _cancel_project_ocr_tasks(project_id)
    if cancelled_ocr:
        logger.info(
            "tender_project_ocr_cancelled_on_delete",
            extra={"project_id": project_id, "cancelled": cancelled_ocr},
        )
    outcome = await asyncio.to_thread(delete_project_cascade, project_id, tenant)
    if outcome is None:
        raise HTTPException(status_code=404, detail="Tender project not found")
    for case_path in outcome["case_paths"]:
        remove_submission_dir(case_path)
    # 遗留④：再清整个项目 submission 目录树——P3「上传即 OCR」的 tender-doc/bids 预热目录无对应
    # 评标 task、不在 case_paths 里，仅靠上面逐 case 清会残留磁盘。整目录兜底清干净。
    await asyncio.to_thread(remove_project_submission_dir, tenant, project_id)
    return {"project_id": project_id, "status": "deleted", "deleted": outcome["deleted"]}


@router.post("/projects/{project_id}/evaluate", response_model=TenderSubmitAcceptedResponse)
async def tender_project_evaluate(
    project_id: str,
    request: Request,
    authorization: str | None = Header(None),
) -> TenderSubmitAcceptedResponse:
    """追加一家投标评标到该招标项目（挂 project_id）。"""
    tenant = verify_tenant(authorization)
    if get_project(project_id, tenant) is None:
        raise HTTPException(status_code=404, detail="Tender project not found")
    return await _submit_bid_evaluation(request, tenant, project_id=project_id)


@router.get("/projects/{project_id}/results")
async def get_tender_project_results(
    project_id: str,
    authorization: str | None = Header(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    """该招标下所有结论回看（走 results.project_id，**独立于任务删除**）。

    返回结论摘要列表；完整 payload 仍走 ``GET /tender/tasks/{request_id}/result``。
    """
    tenant = verify_tenant(authorization)
    if get_project(project_id, tenant) is None:
        raise HTTPException(status_code=404, detail="Tender project not found")
    rows = list_results_by_project(tenant, project_id, limit=limit, offset=offset)
    return [
        {
            "request_id": r["request_id"],
            "claim_id": r.get("claim_id"),
            "verdict": r.get("verdict"),
            "manual_review_reason": r.get("manual_review_reason"),
            "created_at": r.get("created_at"),
        }
        for r in rows
    ]


@router.get("/projects/{project_id}/results/{request_id}")
async def get_tender_project_result_detail(
    project_id: str,
    request_id: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """取该招标项目下单条结论的**完整** payload，**不依赖 tender_tasks 是否存在**。

    P1.1 回看的详情层（cc-impl-review P1）：``GET /tasks/{id}/result`` 删任务后会 404，
    但结论仍在 results。本端点直读 ``results.payload``（tenant + project 双作用域），
    使删任务后完整结论（criteria/scoring/evidence）仍可取。
    """
    tenant = verify_tenant(authorization)
    if get_project(project_id, tenant) is None:
        raise HTTPException(status_code=404, detail="Tender project not found")
    payload = get_result_payload_by_request_id(request_id=request_id, tenant=tenant)
    if (
        payload is None
        or payload.get("project_id") != project_id
        or not isinstance(payload.get("response"), dict)
    ):
        raise HTTPException(status_code=404, detail="Tender result not found in this project")
    response = enrich_audit_decision(payload["response"])
    return response if isinstance(response, dict) else payload["response"]
