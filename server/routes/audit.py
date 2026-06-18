"""Audit task routes: /audit/submit, /audit/tasks/*.

Upload and directory path helpers live in upload_helpers.py.
Background task execution lives in audit_worker.py.
All paths here are relative to the /audit prefix applied when the router is included.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from server.core import enrich_audit_decision
from server.routes.audit_worker import schedule_directory_audit_task
from server.routes.deps import verify_tenant
from server.routes.upload_helpers import (
    materialize_upload_submission,
    remove_submission_dir,
    validate_directory_case_path,
)
from server.stores.audit_task_store import (
    delete_audit_task,
    get_audit_task,
    list_audit_tasks,
    upsert_audit_task,
)
from server.stores.request_store import new_request_id, utc_now
from server.stores.result_store import get_result_payload_by_request_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])


class DirectoryAuditSubmitRequest(BaseModel):
    mode: Literal["directory"]
    directory_path: str


class AuditSubmitAcceptedResponse(BaseModel):
    request_id: str
    status: str
    mode: str
    task_status_url: str


class AuditTaskStatusResponse(BaseModel):
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


def _public_audit_task(record: dict[str, Any]) -> AuditTaskStatusResponse:
    return AuditTaskStatusResponse(
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


@router.post("/submit", response_model=AuditSubmitAcceptedResponse)
async def audit_submit(
    request: Request,
    authorization: str | None = Header(None),
) -> AuditSubmitAcceptedResponse:
    tenant = verify_tenant(authorization)
    request_id = new_request_id()

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            req_payload = DirectoryAuditSubmitRequest.model_validate(await request.json())
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
    upsert_audit_task(
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
            "progress_message": "任务已提交",
            "submitted_at": submitted_at,
            "started_at": None,
            "finished_at": None,
            "updated_at": submitted_at,
        }
    )
    schedule_directory_audit_task(
        request_id=request_id,
        tenant=tenant,
        directory_path=case_path,
        source_mode=mode,
    )
    return AuditSubmitAcceptedResponse(
        request_id=request_id,
        status="accepted",
        mode=mode,
        task_status_url=f"/audit/tasks/{request_id}",
    )


@router.get("/tasks", response_model=list[AuditTaskStatusResponse])
async def list_audit_tasks_endpoint(
    authorization: str | None = Header(None),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[AuditTaskStatusResponse]:
    tenant = verify_tenant(authorization)
    records = list_audit_tasks(tenant, status=status, limit=limit, offset=offset)
    return [_public_audit_task(r) for r in records]


@router.get("/tasks/{request_id}", response_model=AuditTaskStatusResponse)
async def audit_task_status(
    request_id: str,
    authorization: str | None = Header(None),
) -> AuditTaskStatusResponse:
    tenant = verify_tenant(authorization)
    record = get_audit_task(request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Audit task not found")
    return _public_audit_task(record)


@router.get("/tasks/{request_id}/result")
async def audit_task_result(
    request_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    tenant = verify_tenant(authorization)
    record = get_audit_task(request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Audit task not found")
    if record.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Audit task is not completed yet")
    payload = get_result_payload_by_request_id(request_id=request_id, tenant=tenant)
    if payload is None or not isinstance(payload.get("response"), dict):
        raise HTTPException(status_code=404, detail="Audit result not found")
    # 归一化函数上线前存档的旧结果，reasons / policy_refs 仍可能是对象数组。
    # 在出口处再拍平一次，避免前端按字符串渲染对象触发 React #31 整页白屏。
    response = enrich_audit_decision(payload["response"])
    return response if isinstance(response, dict) else payload["response"]


@router.post("/tasks/{request_id}/retry", response_model=AuditTaskStatusResponse)
async def retry_audit_task(
    request_id: str,
    authorization: str | None = Header(None),
) -> AuditTaskStatusResponse:
    tenant = verify_tenant(authorization)
    record = get_audit_task(request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Audit task not found")
    if record.get("status") == "running":
        raise HTTPException(status_code=409, detail="Audit task is still running")
    case_path = str(record.get("case_path") or "").strip()
    if not case_path:
        raise HTTPException(status_code=400, detail="Audit task has no source path to re-audit")
    mode = str(record.get("mode") or "directory")
    started_at = utc_now()
    upsert_audit_task(
        {
            "request_id": request_id,
            "tenant": tenant,
            "status": "running",
            "mode": mode,
            "source_mode": mode,
            "case_path": case_path,
            "claim_id": None,
            "result_file": None,
            "session_id": None,
            "error_detail": None,
            "progress_message": "重新审核中",
            "started_at": started_at,
            "finished_at": None,
            "updated_at": started_at,
        }
    )
    schedule_directory_audit_task(
        request_id=request_id,
        tenant=tenant,
        directory_path=case_path,
        source_mode=mode,
    )
    refreshed = get_audit_task(request_id, tenant=tenant)
    return _public_audit_task(refreshed if refreshed is not None else record)


@router.delete("/tasks/{request_id}")
async def delete_audit_task_endpoint(
    request_id: str,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    tenant = verify_tenant(authorization)
    record = get_audit_task(request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Audit task not found")
    if record.get("status") == "running":
        raise HTTPException(status_code=409, detail="Cannot delete a running audit task")
    remove_submission_dir(record.get("case_path"))
    delete_audit_task(request_id, tenant=tenant)
    return {"request_id": request_id, "status": "deleted"}
