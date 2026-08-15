"""Tender 招标/投标文件上传 + OCR 预热轮询端点（P2）。

``POST /projects/{id}/tender-doc``、``POST /projects/{id}/bids``、
``GET /projects/{id}/tender-doc``、``GET /projects/{id}/docs-status``。

D2（design T4）从原 912 行 ``routes/tender.py`` 按 banner 分节拆出（纯路由分组，OCR 摄取
编排本体已在 D2 T3 下沉 ``server.tender.doc_pipeline``）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import Header, HTTPException, Request
from starlette.requests import ClientDisconnect

from server.routes.deps import verify_tenant
from server.routes.tender import router
from server.routes.upload_helpers import (
    collect_uploaded_files,
    materialize_upload_submission,
    sanitize_upload_name,
)
from server.stores.request_store import new_request_id
from server.stores.tender_doc_store import (
    get_project_doc,
    list_bid_docs,
    new_bid_id,
    upsert_bid_doc,
    upsert_project_doc,
)
from server.stores.tender_project_store import get_project
from server.tender.doc_pipeline import (
    TENDER_OCR_PURPOSE as _TENDER_OCR_PURPOSE,
)
from server.tender.doc_pipeline import (
    start_bid_doc_ocr_task as _start_bid_doc_ocr_task,
)
from server.tender.doc_pipeline import (
    start_project_doc_ocr_task as _start_project_doc_ocr_task,
)


@router.post("/projects/{project_id}/tender-doc")
async def upload_tender_doc(
    project_id: str,
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """上传招标文件并触发后台 OCR 预热（P2 上传即 OCR 解耦）。

    落盘到 tender/<project_id>/<request_id>/ 目录；写招标层 ocr_status=running；
    后台 asyncio task 跑 prewarm_and_report → update_project_doc_ocr(ready|degraded|partial|failed)。
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
        validate_document_format=True,
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
        case_path=case_path,  # H3 KD2：评标入口据此对非 ready 底稿重跑一次预热 OCR
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
    后台 asyncio task 跑 prewarm_and_report → update_bid_doc_ocr(ready|degraded|partial|failed)。
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
        validate_document_format=True,
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
        case_path=case_path,  # H3 KD2：同上
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
            # AC3：failed 时告诉用户**具体缺什么**，而不是只显示"识别失败"。
            "criteria_error": project_doc.get("criteria_error"),
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
