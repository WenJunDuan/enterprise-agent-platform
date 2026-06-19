"""Contract review routes: /contract/review, /contract/tasks/*.

镜像 ``routes/tender.py`` 的异步任务三件套（提交→查任务→取结果）。上传与目录校验复用
``upload_helpers``；后台执行在 ``contract_worker.py``（含合同结构落库）。
所有路径相对 router 注册时的 /contract 前缀。
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from server.core import enrich_audit_decision
from server.routes.contract_worker import schedule_contract_review_task
from server.routes.deps import verify_tenant
from server.routes.upload_helpers import (
    materialize_upload_submission,
    validate_directory_case_path,
)
from server.stores.contract_task_store import get_contract_task, upsert_contract_task
from server.stores.request_store import new_request_id, utc_now
from server.stores.result_store import get_result_payload_by_request_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["contract"])


class DirectoryContractReviewRequest(BaseModel):
    mode: Literal["directory"]
    directory_path: str


class ContractReviewAcceptedResponse(BaseModel):
    request_id: str
    status: str
    mode: str
    task_status_url: str


class ContractTaskStatusResponse(BaseModel):
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


def _public_contract_task(record: dict[str, Any]) -> ContractTaskStatusResponse:
    return ContractTaskStatusResponse(
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


# ── route handlers ────────────────────────────────────────────────────────────


@router.post("/review", response_model=ContractReviewAcceptedResponse)
async def contract_review(
    request: Request,
    authorization: str | None = Header(None),
) -> ContractReviewAcceptedResponse:
    tenant = verify_tenant(authorization)
    request_id = new_request_id()

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            req_payload = DirectoryContractReviewRequest.model_validate(await request.json())
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc
        mode = req_payload.mode
        case_path = validate_directory_case_path(req_payload.directory_path)
    elif content_type.startswith("multipart/form-data"):
        form_data = await request.form()
        mode = str(form_data.get("mode") or "").strip()
        if mode != "upload":
            raise HTTPException(status_code=400, detail="multipart requests must use mode=upload")
        case_path = await materialize_upload_submission(
            request_id=request_id,
            form_json=form_data.get("form_json"),
            form_data=form_data,
        )
    else:
        raise HTTPException(status_code=415, detail="Unsupported Content-Type")

    submitted_at = utc_now()
    upsert_contract_task(
        {
            "request_id": request_id,
            "tenant": tenant,
            "status": "accepted",
            "mode": mode,
            "source_mode": mode,
            "case_path": case_path,
            "claim_id": None,
            "result_file": None,
            "session_id": None,
            "error_detail": None,
            "progress_message": "合同审查任务已提交",
            "submitted_at": submitted_at,
            "started_at": None,
            "finished_at": None,
            "updated_at": submitted_at,
        }
    )
    schedule_contract_review_task(
        request_id=request_id,
        tenant=tenant,
        directory_path=case_path,
        source_mode=mode,
    )
    return ContractReviewAcceptedResponse(
        request_id=request_id,
        status="accepted",
        mode=mode,
        task_status_url=f"/contract/tasks/{request_id}",
    )


@router.get("/tasks/{request_id}", response_model=ContractTaskStatusResponse)
async def contract_task_status(
    request_id: str,
    authorization: str | None = Header(None),
) -> ContractTaskStatusResponse:
    tenant = verify_tenant(authorization)
    record = get_contract_task(request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Contract review task not found")
    return _public_contract_task(record)


@router.get("/tasks/{request_id}/result")
async def contract_task_result(
    request_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    tenant = verify_tenant(authorization)
    record = get_contract_task(request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Contract review task not found")
    if record.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Contract review task is not completed yet")
    payload = get_result_payload_by_request_id(request_id=request_id, tenant=tenant)
    if payload is None or not isinstance(payload.get("response"), dict):
        raise HTTPException(status_code=404, detail="Contract review result not found")
    # 归一化结论，与 audit/tender 出口一致。
    response = enrich_audit_decision(payload["response"])
    return response if isinstance(response, dict) else payload["response"]
