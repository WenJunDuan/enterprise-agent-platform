"""OCR streaming job routes: POST /ocr/jobs, GET /ocr/jobs/{request_id}.

D9 streaming-ocr T2: page-level partial-results OCR, task-ified. Split out of
``ocr.py`` (which stays focused on the synchronous ``/extract`` and ``/fill``
endpoints) once this module crossed the file-length SRP threshold — mirrors how
``/audit`` splits routes / worker / upload-helpers across files.

Contrast with ``/ocr/extract``: submit returns 202 immediately; a background
worker (``ocr_job_worker``) runs the recognition pipeline and appends each
completed unit (page or file, see ``server.ocr.pipeline``) to a per-job
``units.jsonl`` sidecar. Clients poll ``GET /ocr/jobs/{request_id}`` for
progressive results instead of waiting for one large synchronous response.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel

from server.ocr.pipeline import OCR_JOB_UNITS_FILENAME
from server.routes.deps import verify_tenant
from server.routes.ocr_job_worker import admission_available, schedule_ocr_job
from server.routes.upload_helpers import build_case_dir, collect_uploaded_files, materialize_ocr_upload
from server.stores.ocr_job_store import get_ocr_job, upsert_ocr_job
from server.stores.request_store import new_request_id, utc_now

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ocr"])


class OcrJobAcceptedResponse(BaseModel):
    request_id: str
    status: str
    task_status_url: str


class OcrJobStatusResponse(BaseModel):
    request_id: str
    status: str
    progress: dict[str, int] | None = None
    results: list[dict[str, Any]]
    error_detail: str | None = None


def _parse_progress(message: str | None) -> dict[str, int] | None:
    """G2①：解析固定格式 ``{"done": <int>, "total": <int>}``；格式非法按无进度处理，不 500。"""
    if not message:
        return None
    try:
        parsed = json.loads(message)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    done, total = parsed.get("done"), parsed.get("total")
    if not isinstance(done, int) or not isinstance(total, int):
        return None
    return {"done": done, "total": total}


def _read_units(case_dir: Path) -> list[dict[str, Any]]:
    """读 units.jsonl 组装 partial results；文件不存在（尚未产出任何单元）返回空列表。"""
    units_path = case_dir / OCR_JOB_UNITS_FILENAME
    if not units_path.exists():
        return []
    units: list[dict[str, Any]] = []
    for line in units_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            units.append(json.loads(stripped))
        except json.JSONDecodeError:
            # 防御边界：GET 与 worker 的 append 并发读写同一文件，理论上可能读到未 flush 完的
            # 尾行（外部 I/O 竞态，非内部不变量）；跳过半行好过让轮询请求 500。
            continue
    return units


@router.post("/jobs", response_model=OcrJobAcceptedResponse, status_code=202)
async def ocr_jobs_submit(
    request: Request,
    authorization: str | None = Header(None),
    run_seal: bool = Query(False, description="是否对扫描件追加印章识别"),
) -> OcrJobAcceptedResponse:
    """提交页级流式 OCR 任务：multipart 入参对齐 ``/ocr/fill``（``files``/``file`` + 可选
    ``form_schema``，本端点当前不消费 ``form_schema``——纯识别任务化，不做表单回填）。

    落盘后台异步跑（仿 ``/audit/submit``），202 返回 ``request_id`` 供轮询
    ``GET /ocr/jobs/{request_id}``。
    """
    tenant = verify_tenant(authorization)
    if not admission_available():
        raise HTTPException(status_code=503, detail="OCR 任务队列已满，请稍后重试")
    request_id = new_request_id()

    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("multipart/form-data"):
        raise HTTPException(status_code=415, detail="ocr jobs requires multipart/form-data")
    form_data = await request.form()
    case_path = await materialize_ocr_upload(
        request_id=request_id,
        tenant=tenant,
        files=collect_uploaded_files(form_data),
    )

    submitted_at = utc_now()
    # 与 /audit/submit 一致：同步 SQLite 写经 to_thread 移出事件循环，不阻塞 async 路由。
    await asyncio.to_thread(
        upsert_ocr_job,
        {
            "request_id": request_id,
            "tenant": tenant,
            "status": "queued",
            "mode": "upload",
            "source_mode": "upload",
            "case_path": case_path,
            "error_detail": None,
            "progress_message": None,
            "submitted_at": submitted_at,
            "started_at": None,
            "finished_at": None,
            "updated_at": submitted_at,
        },
    )
    schedule_ocr_job(request_id=request_id, tenant=tenant, run_seal=run_seal)
    return OcrJobAcceptedResponse(
        request_id=request_id,
        status="queued",
        task_status_url=f"/ocr/jobs/{request_id}",
    )


@router.get("/jobs/{request_id}", response_model=OcrJobStatusResponse)
async def ocr_job_status(
    request_id: str,
    authorization: str | None = Header(None),
) -> OcrJobStatusResponse:
    """轮询任务状态 + 已产出的 partial 单元结果。

    G2②（信任边界）：units.jsonl 路径一律由服务端从 ``verify_tenant`` 解出的 tenant +
    URL 中的 request_id 经 ``build_case_dir`` 派生，不接受任何客户端传入路径。未知
    request_id 或跨租户访问都在 ``get_ocr_job`` 的 tenant 过滤内落空 → 统一 404（F4，不
    泄漏存在性）。
    """
    tenant = verify_tenant(authorization)
    record = get_ocr_job(request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="OCR job not found")
    case_dir = build_case_dir(tenant, "ocr", request_id)
    return OcrJobStatusResponse(
        request_id=request_id,
        status=str(record["status"]),
        progress=_parse_progress(record.get("progress_message")),
        results=_read_units(case_dir),
        error_detail=record.get("error_detail"),
    )
