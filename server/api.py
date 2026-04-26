"""HTTP API and runtime diagnostics for the local serve layer."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from server.command_adapter import run_command_json
from server.platform.config import get_app_settings, load_tenant_keys, tenant_keys_are_default
from server.platform.logging_setup import logging_context
from server.platform.paths import PROJECT_ROOT, SUBMISSION_ROOT_DIR
from server.core import DEFAULT_OUTPUT_SCHEMA_NAME
from server.platform.diagnostics import collect_runtime_diagnostics
from server.platform.logging_setup import configure_logging
from server.platform.storage import append_json_file
from server.stores.audit_task_store import (
    get_audit_task,
    list_audit_tasks,
    recover_stale_audit_tasks,
    upsert_audit_task,
)
from server.stores.request_store import new_request_id, utc_now
from server.stores.result_store import get_result_payload_by_request_id

configure_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="kv" if os.getenv("DEV", "").lower() in {"1", "true", "yes", "on"} or os.getenv("LOG_FORMAT") == "kv" else "json",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    settings = get_app_settings()
    recover_stale_audit_tasks(settings.audit_task_running_timeout_seconds)
    yield


app = FastAPI(title="Enterprise Agent API", version="0.1.0", lifespan=app_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TENANT_KEYS = load_tenant_keys()
ALLOWED_DIRECTORY_ROOT = (PROJECT_ROOT / "data").resolve()


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


def verify_tenant(api_key: str) -> str:
    if tenant_keys_are_default():
        allow_default = os.getenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "").lower() in {"1", "true", "yes", "on"}
        if not allow_default:
            raise HTTPException(
                status_code=503,
                detail="Server is not configured with tenant keys. Set the TENANT_KEYS environment variable.",
            )
    token = api_key.replace("Bearer ", "", 1).strip()
    for tenant, key in TENANT_KEYS.items():
        if key == token:
            return tenant
    raise HTTPException(status_code=401, detail="Invalid API key")


def _public_runtime_status() -> dict[str, Any]:
    diagnostics = collect_runtime_diagnostics()
    checks = diagnostics.get("checks", {})
    raw_app_server = checks.get("app_server") or {}
    app_server = {"ok": bool(raw_app_server.get("ok")), "running": bool(raw_app_server.get("running"))}
    failing_checks = [
        name
        for name, check in checks.items()
        if name != "app_server" and not bool(check.get("ok"))
    ]
    advisories = [
        advisory
        for advisory in diagnostics.get("advisories", [])
        if advisory != "app-server process is not running."
    ]
    return {
        "status": diagnostics.get("status", "degraded"),
        "app_server": app_server,
        "failing_checks": failing_checks,
        "advisories": advisories,
    }


def _http_error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        415: "unsupported_media_type",
        422: "validation_error",
        500: "internal_server_error",
        502: "bad_gateway",
        503: "service_unavailable",
    }.get(status_code, "http_error")


def _coerce_error_message(detail: Any, *, fallback: str) -> str:
    if isinstance(detail, str) and detail.strip():
        return detail
    return fallback


def _error_response_content(
    request: Request,
    *,
    status_code: int,
    detail: Any,
    code: str | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    correlation_id = getattr(request.state, "correlation_id", None)
    serialized_detail = detail if isinstance(detail, str) else jsonable_encoder(detail)
    error_message = message or _coerce_error_message(serialized_detail, fallback="Request failed")
    payload: dict[str, Any] = {
        "detail": serialized_detail,
        "error": {
            "code": code or _http_error_code(status_code),
            "message": error_message,
            "status_code": status_code,
            "path": request.url.path,
            "correlation_id": correlation_id,
        },
    }
    if not isinstance(serialized_detail, str):
        payload["error"]["details"] = serialized_detail
    return payload




@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.correlation_id = correlation_id
    with logging_context(correlation_id=correlation_id):
        response = await call_next(request)
    response.headers["X-Request-ID"] = correlation_id
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_response_content(
            request,
            status_code=exc.status_code,
            detail=exc.detail,
        ),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    detail = exc.errors()
    return JSONResponse(
        status_code=422,
        content=_error_response_content(
            request,
            status_code=422,
            detail=detail,
            code="validation_error",
            message="Request validation failed",
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_http_exception",
        extra={"path": request.url.path, "correlation_id": getattr(request.state, "correlation_id", None)},
    )
    return JSONResponse(
        status_code=500,
        content=_error_response_content(
            request,
            status_code=500,
            detail="Internal server error",
            code="internal_server_error",
            message="Internal server error",
        ),
    )


async def _submit_audit_directory(*, request_id: str) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "status": "accepted",
        "mode": "directory",
        "task_status_url": f"/audit/tasks/{request_id}",
    }


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


def _schedule_directory_audit_task(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    source_mode: str,
) -> None:
    asyncio.create_task(
        _execute_directory_audit_task(
            request_id=request_id,
            tenant=tenant,
            directory_path=directory_path,
            source_mode=source_mode,
        )
    )


def _sanitize_upload_name(name: str, index: int) -> str:
    sanitized = Path(name).name
    if not sanitized:
        raise HTTPException(status_code=400, detail=f"File {index} is missing a filename")
    return sanitized


def _validate_upload_bytes(content: bytes) -> None:
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file cannot be empty")
    if len(content) > get_app_settings().max_upload_file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file exceeds size limit")


def _append_form_field(fields: dict[str, Any], key: str, value: str) -> None:
    current = fields.get(key)
    if current is None:
        fields[key] = value
    elif isinstance(current, list):
        current.append(value)
    else:
        fields[key] = [current, value]


def _collect_scalar_form_fields(form_data: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    iterator = form_data.multi_items() if hasattr(form_data, "multi_items") else form_data.items()
    for key, value in iterator:
        field_name = str(key)
        if field_name in {"mode", "form_json", "files"}:
            continue
        if hasattr(value, "filename"):
            continue
        _append_form_field(fields, field_name, str(value))
    return fields


def _parse_optional_form_json(form_json: str | None) -> dict[str, Any]:
    normalized = str(form_json or "").strip()
    if not normalized:
        return {}
    try:
        parsed_form = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid form_json") from exc
    if not isinstance(parsed_form, dict):
        raise HTTPException(status_code=400, detail="form_json must decode to a JSON object")
    return parsed_form


def _validate_directory_case_path(case_path: str) -> str:
    path = Path(case_path)
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail="directory_path must point to an existing directory")

    resolved = path.resolve()
    try:
        resolved.relative_to(ALLOWED_DIRECTORY_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="directory_path is outside allowed roots") from exc

    return _serialize_case_path(resolved)


def _serialize_case_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


async def _materialize_upload_submission(
    *,
    request_id: str,
    form_json: str | None,
    form_data: Any,
) -> str:
    parsed_form = _parse_optional_form_json(form_json)
    scalar_fields = _collect_scalar_form_fields(form_data)
    files = form_data.getlist("files")
    if not parsed_form and not scalar_fields and not files:
        raise HTTPException(status_code=400, detail="upload mode requires form_json, form fields, or files")

    case_dir = SUBMISSION_ROOT_DIR / request_id
    case_dir.mkdir(parents=True, exist_ok=True)

    attachments: list[dict[str, Any]] = []
    try:
        for index, upload in enumerate(files, start=1):
            safe_name = _sanitize_upload_name(getattr(upload, "filename", "") or "", index)
            target_path = case_dir / safe_name
            content = await upload.read()
            _validate_upload_bytes(content)
            target_path.write_bytes(content)
            attachments.append(
                {
                    "type": "uploaded",
                    "name": safe_name,
                    "path": _serialize_case_path(target_path),
                }
            )

        append_json_file(
            case_dir / "audit-request.json",
            {
                "form": parsed_form,
                "fields": scalar_fields,
                "attachments": attachments,
            },
        )
    except Exception:
        shutil.rmtree(case_dir, ignore_errors=True)
        raise

    return _serialize_case_path(case_dir)


async def _run_directory_audit(*, request_id: str, tenant: str, directory_path: str):
    return await run_command_json(
        "audit",
        directory_path,
        schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
        request_id=request_id,
        tenant=tenant,
    )


async def _execute_directory_audit_task(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    source_mode: str = "directory",
) -> None:
    started_at = utc_now()
    with logging_context(request_id=request_id, tenant=tenant):
        upsert_audit_task(
            {
                "request_id": request_id,
                "tenant": tenant,
                "status": "running",
                "mode": source_mode,
                "source_mode": source_mode,
                "case_path": directory_path,
                "claim_id": None,
                "result_file": None,
                "session_id": None,
                "error_detail": None,
                "progress_message": "正在调用 Claude 审核",
                "started_at": started_at,
                "updated_at": started_at,
            }
        )
        try:
            payload, meta = await _run_directory_audit(
                request_id=request_id,
                tenant=tenant,
                directory_path=directory_path,
            )
            finished_at = utc_now()
            upsert_audit_task(
                {
                    "request_id": request_id,
                    "tenant": tenant,
                    "status": "completed",
                    "mode": source_mode,
                    "source_mode": source_mode,
                    "case_path": directory_path,
                    "claim_id": payload.get("claim_id") if isinstance(payload, dict) else None,
                    "result_file": meta.result_file,
                    "session_id": meta.claude_session_id,
                    "error_detail": None,
                    "progress_message": "审核完成",
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                }
            )
        except Exception as exc:
            logger.exception(
                "directory_audit_failed",
                extra={"request_id": request_id, "tenant": tenant, "route": "/audit/submit"},
            )
            finished_at = utc_now()
            upsert_audit_task(
                {
                    "request_id": request_id,
                    "tenant": tenant,
                    "status": "failed",
                    "mode": source_mode,
                    "source_mode": source_mode,
                    "case_path": directory_path,
                    "claim_id": None,
                    "result_file": None,
                    "session_id": None,
                    "error_detail": str(exc),
                    "progress_message": "审核失败",
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                }
            )

@app.post("/audit/submit", response_model=AuditSubmitAcceptedResponse)
async def audit_submit(
    request: Request,
    authorization: str = Header(...),
) -> AuditSubmitAcceptedResponse:
    tenant = verify_tenant(authorization)
    request_id = new_request_id()

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            payload = DirectoryAuditSubmitRequest.model_validate(await request.json())
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc
        mode = payload.mode
        case_path = _validate_directory_case_path(payload.directory_path)
    elif content_type.startswith("multipart/form-data"):
        form_data = await request.form()
        mode = str(form_data.get("mode") or "").strip()
        if mode != "upload":
            raise HTTPException(status_code=400, detail="multipart requests must use mode=upload")
        case_path = await _materialize_upload_submission(
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
    response = await _submit_audit_directory(request_id=request_id)
    _schedule_directory_audit_task(
        request_id=request_id,
        tenant=tenant,
        directory_path=case_path,
        source_mode=mode,
    )
    return AuditSubmitAcceptedResponse(
        request_id=response["request_id"],
        status=response["status"],
        mode=mode,
        task_status_url=response["task_status_url"],
    )


@app.get("/audit/tasks", response_model=list[AuditTaskStatusResponse])
async def list_audit_tasks_endpoint(
    authorization: str = Header(...),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[AuditTaskStatusResponse]:
    tenant = verify_tenant(authorization)
    records = list_audit_tasks(tenant, status=status, limit=limit, offset=offset)
    return [_public_audit_task(r) for r in records]


@app.get("/audit/tasks/{request_id}", response_model=AuditTaskStatusResponse)
async def audit_task_status(
    request_id: str,
    authorization: str = Header(...),
) -> AuditTaskStatusResponse:
    tenant = verify_tenant(authorization)
    record = get_audit_task(request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Audit task not found")
    return _public_audit_task(record)


@app.get("/audit/tasks/{request_id}/result")
async def audit_task_result(request_id: str, authorization: str = Header(...)) -> dict[str, Any]:
    tenant = verify_tenant(authorization)
    record = get_audit_task(request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Audit task not found")
    if record.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Audit task is not completed yet")
    payload = get_result_payload_by_request_id(request_id=request_id, tenant=tenant)
    if payload is None or not isinstance(payload.get("response"), dict):
        raise HTTPException(status_code=404, detail="Audit result not found")
    return payload["response"]

@app.get("/health")
async def health() -> JSONResponse:
    payload = _public_runtime_status()
    status_code = 200 if payload["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=payload)
