"""Tender 单投标人评标任务三件套：``/evaluate``、``/tasks/*``（提交→查任务→取结果→重试→删除）。

镜像 ``routes/audit.py`` 的异步任务三件套；D2（design T4）从原 912 行 ``routes/tender.py``
按 banner 分节拆出（纯路由分组，业务逻辑已在 D1/D2 下沉 ``server.tender.worker``）。
``_submit_bid_evaluation`` 是共享提交流程，供本模块的 legacy ``/evaluate`` 与
``server.routes.tender.projects`` 的 ``/projects/{id}/evaluate`` 复用。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Literal

from fastapi import Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from starlette.requests import ClientDisconnect

from server.core import enrich_audit_decision
from server.routes.deps import verify_tenant
from server.routes.tender import router
from server.routes.upload_helpers import (
    UNBOUND_PROJECT,
    materialize_upload_submission,
    remove_submission_dir,
    validate_directory_case_path,
)
from server.stores.request_store import new_request_id, utc_now
from server.stores.result_store import get_result_payload_by_request_id
from server.stores.tender_task_store import (
    delete_tender_task_if_idle,
    get_tender_task,
    list_tender_tasks,
    try_transition_tender_task,
    upsert_tender_task,
)
from server.tender.bid_resolve import resolve_prewarm_bid_id
from server.tender.criteria_gate import criteria_submission_block
from server.tender.worker import admission_available, schedule_tender_evaluation_task

logger = logging.getLogger(__name__)


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
    # P0.4：**等不来结果**的单别收（criteria 解析已失败 / 僵尸任务）。位置必须在**解析请求体
    # 之前**——晚一步就会落上传文件、建任务记录，用户拿到的是一个注定作废却在界面上"进行中"
    # 的 request_id。还在解析的收下即可（2026-08-19 收单等就绪），由 worker 在开跑判分前等
    # criteria 就绪，等不到则任务明确失败（见 ``criteria_gate.criteria_start_failure``）。
    if project_id:
        blocked = await asyncio.to_thread(criteria_submission_block, project_id, tenant)
        if blocked:
            raise HTTPException(status_code=409, detail=blocked)
    request_id = new_request_id()
    # R6-R2：前端传 prewarm bid_id（上传即 OCR 时 uploadBid 返回的）→ 评标据此复用已预热的 OCR 底稿
    # （doc_layer.load_doc_layer_context 按 bid_id 读 doc 层），免重 OCR（实测省一遍 ~5min）。缺省 None
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
        submitted_bid_id: str | None = None
        submitted_bidder_name: str | None = None
        if raw_form:
            try:
                parsed_form = json.loads(raw_form) or {}
            except (ValueError, TypeError):
                parsed_form = {}
            if isinstance(parsed_form, dict):
                submitted_bid_id = parsed_form.get("bid_id") or None
                submitted_bidder_name = parsed_form.get("bidder_name") or None
        # KD5：缺 bid_id 时按投标人名回查预热记录。前端在 uploadBid 未返回就提交（或刷新丢内存
        # 态）会漏传该字段 → 旧行为直接掉 inline OCR，且两层预热随后转 ready，事后完全看不出来。
        prewarm_bid_id, bid_gap_reason = resolve_prewarm_bid_id(
            project_id,
            tenant,
            explicit_bid_id=submitted_bid_id,
            bidder_name=submitted_bidder_name,
        )
        if bid_gap_reason is not None:
            logger.info(
                "tender_prewarm_bid_unresolved",
                extra={
                    "request_id": request_id,
                    "project_id": project_id,
                    "reason": bid_gap_reason,
                },
            )
        case_path = await materialize_upload_submission(
            request_id=request_id,
            tenant=tenant,
            form_json=form_data.get("form_json"),
            form_data=form_data,
            domain="tender",
            project_id=project_id or UNBOUND_PROJECT,
            validate_document_format=True,
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
