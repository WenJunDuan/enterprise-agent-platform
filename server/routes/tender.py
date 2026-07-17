"""Tender evaluation routes: /tender/evaluate, /tender/tasks/*.

镜像 ``routes/audit.py`` 的异步任务三件套（提交→查任务→取结果）。上传与目录校验复用
``upload_helpers``；后台执行在 ``tender_worker.py``。所有路径相对 router 注册时的 /tender 前缀。

P2 新增：
- ``POST /tender/projects/{id}/tender-doc`` — 上传招标文件 + 后台 OCR 预热。
- ``POST /tender/projects/{id}/bids`` — 上传投标文件 + 后台 OCR 预热。
- ``GET  /tender/projects/{id}/docs-status`` — 轮询 OCR 状态（前端用）。

R1 新增：
- ``_extract_project_doc_info`` — OCR ready 后立即抽取 criteria + tender_info。
- ``GET /tender/projects/{id}/tender-doc`` — 读取招标层 OCR + criteria + tender_info。
- ``get_docs_status`` — 增加 criteria_status。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from starlette.requests import ClientDisconnect

from server.core import enrich_audit_decision
from server.ocr.prewarm_scheduler import cancel_project_ocr_tasks as _cancel_project_ocr_tasks
from server.routes.deps import verify_tenant
from server.tender.compare_worker import (
    collect_compare_input,
    has_active_compare,
    schedule_compare_task,
)
from server.routes.tender_doc_pipeline import (
    TENDER_OCR_PURPOSE as _TENDER_OCR_PURPOSE,
    start_bid_doc_ocr_task as _start_bid_doc_ocr_task,
    start_project_doc_ocr_task as _start_project_doc_ocr_task,
)
from server.tender.worker import admission_available, schedule_tender_evaluation_task
from server.routes.upload_helpers import (
    UNBOUND_PROJECT,
    collect_uploaded_files,
    materialize_upload_submission,
    remove_project_submission_dir,
    remove_submission_dir,
    sanitize_upload_name,
    validate_directory_case_path,
)
from server.stores.request_store import new_request_id, utc_now
from server.stores.result_store import get_result_payload_by_request_id, list_results_by_project
from server.stores.tender_compare_store import (
    compute_input_signature,
    get_compare_result,
    is_stale,
)
from server.stores.tender_doc_store import (
    get_project_doc,
    list_bid_docs,
    new_bid_id,
    upsert_bid_doc,
    upsert_project_doc,
)
from server.stores.tender_project_store import (
    DEFAULT_PROJECT_SCENARIO,
    count_active_bids,
    delete_project_cascade,
    get_or_create_project,
    get_project,
    list_projects,
)
from server.stores.tender_task_store import (
    delete_tender_task_if_idle,
    get_tender_task,
    list_tender_tasks,
    list_tender_tasks_by_project,
    try_transition_tender_task,
    upsert_tender_task,
)

logger = logging.getLogger(__name__)

# OCR 上传编排（并发闸/任务追踪/取消）已下沉 server.ocr.prewarm_scheduler；招标/投标文档
# 摄取（后台 OCR → criteria/tender_info 抽取）已下沉 server.routes.tender_doc_pipeline（S3）。
# 本路由模块仅做 HTTP 编排，调用上述模块的公开函数（顶部以旧私有名 import alias 保兼容）。

router = APIRouter(tags=["tender"])
TenderScenario = Literal["bidder_self_check", "expert_assist", "post_eval_monitor"]


class DirectoryTenderSubmitRequest(BaseModel):
    mode: Literal["directory"]
    directory_path: str


class TenderSubmitAcceptedResponse(BaseModel):
    request_id: str
    status: str
    mode: str
    task_status_url: str


class TenderTaskStatusResponse(BaseModel):
    request_id: str
    status: str
    mode: str
    claim_id: str | None = None
    error_detail: str | None = None
    progress_message: str | None = None
    submitted_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str


def _public_tender_task(record: dict[str, Any]) -> TenderTaskStatusResponse:
    return TenderTaskStatusResponse(
        request_id=str(record["request_id"]),
        status=str(record["status"]),
        mode=str(record["mode"]),
        claim_id=record.get("claim_id"),
        error_detail=record.get("error_detail"),
        progress_message=record.get("progress_message"),
        submitted_at=record.get("submitted_at"),
        started_at=record.get("started_at"),
        finished_at=record.get("finished_at"),
        updated_at=str(record["updated_at"]),
    )


# ── 招标项目实体 DTO + 名册聚合 ────────────────────────────────────────────────


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


# ── route handlers ────────────────────────────────────────────────────────────


async def _submit_bid_evaluation(
    request: Request,
    tenant: str,
    *,
    project_id: str | None,
) -> TenderSubmitAcceptedResponse:
    """共享提交流程：解析 directory/upload → 建任务(挂 project) → 排程后台评标。

    ``project_id`` 为该招标项目（``POST /projects/{id}/evaluate``）；旧 ``/tender/evaluate``
    传 None（legacy 散单，不挂 project，codex §7.3）。落 ``tender_tasks.group_id`` 作链接键，
    并透传给 worker → 结论落 ``results.project_id``。
    """
    # round4 F5：准入闸——在途任务满则早拒（在写上传文件/建任务记录之前），不再无界接单。
    if not admission_available():
        raise HTTPException(status_code=503, detail="评标队列已满，请稍后重试")
    request_id = new_request_id()
    # R6-R2：前端传 prewarm bid_id（上传即 OCR 时 uploadBid 返回的）→ 评标据此复用已预热的 OCR 底稿
    # （worker _load_doc_layer_context 按 bid_id 读 doc 层），免重 OCR（实测省一遍 ~5min）。缺省 None
    # → 走原 inline OCR 路径（向后兼容 directory/legacy）。
    prewarm_bid_id: str | None = None

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            req_payload = DirectoryTenderSubmitRequest.model_validate(await request.json())
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc
        mode = req_payload.mode
        case_path = validate_directory_case_path(
            req_payload.directory_path,
            tenant,
            expected_domain="tender",
            expected_project_id=project_id or UNBOUND_PROJECT,
        )
    elif content_type.startswith("multipart/form-data"):
        try:
            form_data = await request.form()
        except ClientDisconnect:
            raise HTTPException(status_code=400, detail="上传连接中断，请重新提交")
        mode = str(form_data.get("mode") or "").strip()
        if mode != "upload":
            raise HTTPException(status_code=400, detail="multipart requests must use mode=upload")
        raw_form = form_data.get("form_json")
        if raw_form:
            try:
                prewarm_bid_id = (json.loads(raw_form) or {}).get("bid_id") or None
            except (ValueError, TypeError):
                prewarm_bid_id = None
        case_path = await materialize_upload_submission(
            request_id=request_id,
            tenant=tenant,
            form_json=form_data.get("form_json"),
            form_data=form_data,
            domain="tender",
            project_id=project_id or UNBOUND_PROJECT,
        )
    else:
        raise HTTPException(status_code=415, detail="Unsupported Content-Type")

    submitted_at = utc_now()
    # round4 F4：与 worker 一致，同步 SQLite 写经 to_thread 移出事件循环（不阻塞 async 路由）。
    await asyncio.to_thread(
        upsert_tender_task,
        {
            "request_id": request_id,
            "tenant": tenant,
            "status": "accepted",
            "mode": mode,
            "source_mode": mode,
            "case_path": case_path,
            "claim_id": None,
            "group_id": project_id,  # 招标项目链接键（tender 边界叫 project_id）
            "result_file": None,
            "session_id": None,
            "error_detail": None,
            "progress_message": "评标任务已提交",
            "submitted_at": submitted_at,
            "started_at": None,
            "finished_at": None,
            "updated_at": submitted_at,
        },
    )
    schedule_tender_evaluation_task(
        request_id=request_id,
        tenant=tenant,
        directory_path=case_path,
        source_mode=mode,
        project_id=project_id,
        bid_id=prewarm_bid_id,  # R6-R2：透传 → worker 复用预热 OCR，免重 OCR
    )
    return TenderSubmitAcceptedResponse(
        request_id=request_id,
        status="accepted",
        mode=mode,
        task_status_url=f"/tender/tasks/{request_id}",
    )


@router.post("/evaluate", response_model=TenderSubmitAcceptedResponse)
async def tender_evaluate(
    request: Request,
    authorization: str | None = Header(None),
) -> TenderSubmitAcceptedResponse:
    """旧单投标人评标入口（向后兼容）：不挂招标项目（project_id=NULL）。"""
    tenant = verify_tenant(authorization)
    return await _submit_bid_evaluation(request, tenant, project_id=None)


@router.get("/tasks", response_model=list[TenderTaskStatusResponse])
async def list_tender_tasks_endpoint(
    authorization: str | None = Header(None),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[TenderTaskStatusResponse]:
    tenant = verify_tenant(authorization)
    records = list_tender_tasks(tenant, status=status, limit=limit, offset=offset)
    return [_public_tender_task(r) for r in records]


@router.get("/tasks/{request_id}", response_model=TenderTaskStatusResponse)
async def tender_task_status(
    request_id: str,
    authorization: str | None = Header(None),
) -> TenderTaskStatusResponse:
    tenant = verify_tenant(authorization)
    record = get_tender_task(request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Tender task not found")
    return _public_tender_task(record)


@router.get("/tasks/{request_id}/result")
async def tender_task_result(
    request_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    tenant = verify_tenant(authorization)
    record = get_tender_task(request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Tender task not found")
    if record.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Tender task is not completed yet")
    payload = get_result_payload_by_request_id(request_id=request_id, tenant=tenant)
    if payload is None or not isinstance(payload.get("response"), dict):
        raise HTTPException(status_code=404, detail="Tender result not found")
    # 归一化结论（reasons / policy_refs 拍平），与 audit 出口一致，避免前端按字符串渲染对象。
    response = enrich_audit_decision(payload["response"])
    return response if isinstance(response, dict) else payload["response"]


@router.post("/tasks/{request_id}/retry", response_model=TenderTaskStatusResponse)
async def retry_tender_task(
    request_id: str,
    authorization: str | None = Header(None),
) -> TenderTaskStatusResponse:
    tenant = verify_tenant(authorization)
    record = get_tender_task(request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Tender task not found")
    case_path = str(record.get("case_path") or "").strip()
    if not case_path:
        raise HTTPException(status_code=400, detail="Tender task has no source path to re-evaluate")
    mode = str(record.get("mode") or "directory")
    # round4 F5：准入闸——在途任务满则拒，不在转移为 running 之前先把队列撑爆。
    if not admission_available():
        raise HTTPException(status_code=503, detail="评标队列已满，请稍后重试")
    started_at = utc_now()
    # round4 F6：原子状态转移替代"读 status→判→写"。并发两次 retry 只有一次成功，
    # 另一次回 409，杜绝双重排程 / 双重成本。
    claimed = try_transition_tender_task(
        request_id,
        tenant,
        updates={
            "status": "running",
            "claim_id": None,
            "result_file": None,
            "session_id": None,
            "error_detail": None,
            "progress_message": "重新评标中",
            "started_at": started_at,
            "finished_at": None,
            "updated_at": started_at,
        },
    )
    if not claimed:
        raise HTTPException(status_code=409, detail="Tender task is still running")
    schedule_tender_evaluation_task(
        request_id=request_id,
        tenant=tenant,
        directory_path=case_path,
        source_mode=mode,
        # codex P1.1：retry 必须保留原招标项目链接，否则 worker 以 project_id=None 归档，
        # INSERT OR REPLACE 会把原 project-scoped 结论覆盖成 NULL，从 /projects/{id}/results 消失。
        project_id=record.get("group_id"),
    )
    refreshed = get_tender_task(request_id, tenant=tenant)
    return _public_tender_task(refreshed if refreshed is not None else record)


@router.delete("/tasks/{request_id}")
async def delete_tender_task_endpoint(
    request_id: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    tenant = verify_tenant(authorization)
    record = get_tender_task(request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Tender task not found")
    # round4 F6：原子守卫删除——running 时删不动（回 409），避免与并发 retry 竞态。
    if not delete_tender_task_if_idle(request_id, tenant):
        raise HTTPException(status_code=409, detail="Cannot delete a running tender task")
    remove_submission_dir(record.get("case_path"))
    return {"request_id": request_id, "status": "deleted"}


# ── 招标项目资源（多投标人追加 / 按招标查看 / 结果回看）────────────────────────


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


# ── P2 OCR 预热辅助（P1-2/P1-3 修复：强引用 + 信号量 + 失败写 failed）──────────────



# ── P2 上传端点（招标文件 / 投标文件 / 轮询状态）────────────────────────────────


@router.post("/projects/{project_id}/tender-doc")
async def upload_tender_doc(
    project_id: str,
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """上传招标文件并触发后台 OCR 预热（P2 上传即 OCR 解耦）。

    落盘到 tender/<project_id>/<request_id>/ 目录；写招标层 ocr_status=running；
    后台 asyncio task 跑 prewarm_and_text → update_project_doc_ocr(ready|failed)。
    不阻塞响应：立即返回 {project_id, ocr_status}。

    ClientDisconnect during multipart parsing → 400（P1 fix）。
    至少 1 个真实文件，否则 400（P1-4 fix）。
    """
    tenant = verify_tenant(authorization)
    project = get_project(project_id, tenant)
    if project is None:
        raise HTTPException(status_code=404, detail="Tender project not found")

    doc_request_id = new_request_id()
    try:
        form_data = await request.form()
    except ClientDisconnect:
        raise HTTPException(status_code=400, detail="上传连接中断，请重新提交")

    # P1-4: at least one real file must be present
    files = collect_uploaded_files(form_data)
    if not files:
        raise HTTPException(status_code=400, detail="必须至少上传 1 个文件")

    case_path = await materialize_upload_submission(
        request_id=doc_request_id,
        tenant=tenant,
        form_json=None,
        form_data=form_data,
        domain="tender",
        project_id=project_id,
    )

    # Collect uploaded filenames for the files JSON list
    file_names = [
        sanitize_upload_name(getattr(f, "filename", "") or "", i)
        for i, f in enumerate(files, start=1)
    ]
    tender_files_json = json.dumps(file_names)

    await asyncio.to_thread(
        upsert_project_doc,
        project_id=project_id,
        tenant=tenant,
        tender_files=tender_files_json,
        ocr_status="running",
    )

    _start_project_doc_ocr_task(project_id, case_path, tenant=tenant, purpose=_TENDER_OCR_PURPOSE)

    return {"project_id": project_id, "ocr_status": "running"}


@router.post("/projects/{project_id}/bids")
async def upload_bid_doc(
    project_id: str,
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """上传投标文件并触发后台 OCR 预热（P2 上传即 OCR 解耦）。

    bidder_name 从 multipart form data 字段读取；落盘写投标层 ocr_status=running；
    后台 asyncio task 跑 prewarm_and_text → update_bid_doc_ocr(ready|failed)。
    不阻塞响应：立即返回 {bid_id, ocr_status}。

    ClientDisconnect during multipart parsing → 400（P1 fix）。
    至少 1 个真实文件，否则 400（P1-4 fix）。
    """
    tenant = verify_tenant(authorization)
    project = get_project(project_id, tenant)
    if project is None:
        raise HTTPException(status_code=404, detail="Tender project not found")

    bid_id = new_bid_id()
    try:
        form_data = await request.form()
    except ClientDisconnect:
        raise HTTPException(status_code=400, detail="上传连接中断，请重新提交")

    bidder_name = str(form_data.get("bidder_name") or "").strip() or None

    # P1-4: at least one real file must be present
    files = collect_uploaded_files(form_data)
    if not files:
        raise HTTPException(status_code=400, detail="必须至少上传 1 个文件")

    case_path = await materialize_upload_submission(
        request_id=bid_id,
        tenant=tenant,
        form_json=None,
        form_data=form_data,
        domain="tender",
        project_id=project_id,
    )

    file_names = [
        sanitize_upload_name(getattr(f, "filename", "") or "", i)
        for i, f in enumerate(files, start=1)
    ]
    bid_files_json = json.dumps(file_names)

    await asyncio.to_thread(
        upsert_bid_doc,
        project_id=project_id,
        bid_id=bid_id,
        tenant=tenant,
        bidder_name=bidder_name,
        bid_files=bid_files_json,
        ocr_status="running",
    )

    _start_bid_doc_ocr_task(project_id, bid_id, case_path, tenant=tenant, purpose=_TENDER_OCR_PURPOSE)

    return {"bid_id": bid_id, "ocr_status": "running"}


@router.get("/projects/{project_id}/tender-doc")
async def get_tender_doc_info(
    project_id: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """R1: 读取招标层文档信息（OCR 状态 + criteria + tender_info）。

    Returns:
        {
            ocr_status, ocr_clarity,
            criteria_status,
            criteria: <object | null>,
            tender_info: <object | null>,
            tender_files: <list>
        }

    Raises:
        404: Project not found or no tender-doc row exists.
        401: Missing / invalid authorization header.
    """
    tenant = verify_tenant(authorization)
    if get_project(project_id, tenant) is None:
        raise HTTPException(status_code=404, detail="Tender project not found")

    project_doc = await asyncio.to_thread(get_project_doc, project_id, tenant)
    if project_doc is None:
        raise HTTPException(
            status_code=404, detail="No tender document uploaded for this project"
        )

    # Decode JSON blobs; return null when absent or unparseable.
    def _safe_json(blob: str | None) -> Any:
        if not blob:
            return None
        try:
            return json.loads(blob)
        except (json.JSONDecodeError, TypeError):
            return None

    tender_files_raw = project_doc.get("tender_files") or "[]"
    # F3 兜底推断：OCR 已 failed 时 criteria 不可能再产出，但若服务在抽取前/中崩溃，criteria_status
    # 可能停在 pending/running（背景 task 不自动恢复）→ 前端轮询永不停。GET 端对外把这种悬空态推断
    # 为 failed（终态），让前端停轮询、显"识别失败"；DB 原值不改（重新上传才重置）。
    criteria_status = project_doc.get("criteria_status", "pending")
    if project_doc.get("ocr_status") == "failed" and criteria_status not in {"ready", "failed"}:
        criteria_status = "failed"
    return {
        "ocr_status": project_doc.get("ocr_status"),
        "ocr_clarity": project_doc.get("ocr_clarity"),
        "criteria_status": criteria_status,
        "criteria": _safe_json(project_doc.get("criteria")),
        "tender_info": _safe_json(project_doc.get("tender_info")),
        "tender_files": _safe_json(tender_files_raw) or [],
    }


@router.get("/projects/{project_id}/docs-status")
async def get_docs_status(
    project_id: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """返回招标层 + 各投标层的 OCR 状态（前端轮询用，P2）。

    R1 extension: tender_doc dict now includes criteria_status for front-end polling.

    Returns:
        {
            tender_doc: {ocr_status, criteria_status} | None,
            bids: [{bid_id, bidder_name, ocr_status}]
        }
    """
    tenant = verify_tenant(authorization)
    if get_project(project_id, tenant) is None:
        raise HTTPException(status_code=404, detail="Tender project not found")

    project_doc = await asyncio.to_thread(get_project_doc, project_id, tenant)
    bid_rows = await asyncio.to_thread(list_bid_docs, project_id, tenant)

    tender_doc_status: dict[str, Any] | None = None
    if project_doc is not None:
        tender_doc_status = {
            "ocr_status": project_doc["ocr_status"],
            "criteria_status": project_doc.get("criteria_status", "pending"),
        }

    bids_status = [
        {
            "bid_id": r["bid_id"],
            "bidder_name": r.get("bidder_name"),
            "ocr_status": r["ocr_status"],
        }
        for r in bid_rows
    ]

    return {"tender_doc": tender_doc_status, "bids": bids_status}


# ── 价格横比（Phase 2：多家比选 / 排名 / 推荐中标人）──────────────────────────


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
