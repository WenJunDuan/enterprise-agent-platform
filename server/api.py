"""HTTP API and runtime diagnostics for the local serve layer."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, model_validator

from server.command_adapter import run_command_json
from server.core import AgentRunMeta
from server.platform.config import get_app_settings, load_tenant_keys
from server.platform.paths import PROJECT_ROOT, SUBMISSION_ROOT_DIR
from server.core import (
    DEFAULT_OUTPUT_SCHEMA_NAME,
    INIT_RULES_REPORT_SCHEMA_NAME,
    JSONContractError,
    run_agent_json,
)
from server.platform.diagnostics import collect_runtime_diagnostics
from server.platform.source_proxy import prepare_text_proxy
from server.platform.storage import append_json_file
from server.stores.audit_task_store import get_audit_task, upsert_audit_task
from server.stores.request_store import (
    RequestAuditRecord,
    append_request_audit,
    get_request_audit_by_request_id,
    list_request_audits,
    new_request_id,
    utc_now,
)
from server.stores.result_store import (
    get_result_payload_by_request_id,
    get_result_record_by_request_id,
    list_result_records,
)
from server.stores.session_store import (
    get_sdk_session_transcript,
    get_session_record_by_session_id,
    list_conversation_summaries,
    list_known_session_ids,
    list_logged_sessions,
    list_sdk_session_summaries,
)

app = FastAPI(title="Enterprise Agent API", version="0.1.0")
TENANT_KEYS = load_tenant_keys()


def _load_tenant_keys() -> dict[str, str]:
    """Backward-compatible helper for tests and bootstrap checks."""
    return load_tenant_keys()


class SessionControlRequest(BaseModel):
    conversation_id: str | None = None
    resume_session_id: str | None = None
    fork_from_session_id: str | None = None
    continue_recent: bool = False

    @model_validator(mode="after")
    def validate_session_controls(self) -> "SessionControlRequest":
        enabled = sum(
            bool(value)
            for value in [self.resume_session_id, self.fork_from_session_id, self.continue_recent]
        )
        if enabled > 1:
            raise ValueError(
                "resume_session_id, fork_from_session_id, and continue_recent are mutually exclusive."
            )
        if self.continue_recent and not get_app_settings().allow_unscoped_continue_recent:
            raise ValueError(
                "continue_recent is disabled for HTTP serve mode. Use conversation_id or resume_session_id."
            )
        return self


class ChatRequest(SessionControlRequest):
    message: str
    schema_name: str | None = None


class CommandRequest(SessionControlRequest):
    schema_name: str | None = None


class AuditRequest(CommandRequest):
    path: str


class InitRulesRequest(CommandRequest):
    source_path: str
    domain: str


class DirectoryAuditSubmitRequest(BaseModel):
    mode: Literal["directory"]
    directory_path: str


class ChatResponse(BaseModel):
    request_id: str
    tenant: str
    conversation_id: str
    claude_session_id: str | None = None
    schema_name: str
    result_file: str | None = None
    response: dict[str, Any] | list[Any]
    cost: float


class AuditSubmitAcceptedResponse(BaseModel):
    request_id: str
    status: str
    mode: str
    task_status_url: str
    result_url: str


def verify_tenant(api_key: str) -> str:
    token = api_key.replace("Bearer ", "", 1).strip()
    for tenant, key in TENANT_KEYS.items():
        if key == token:
            return tenant
    raise HTTPException(status_code=401, detail="Invalid API key")


def _build_request_audit_record(
    *,
    request_id: str,
    route: str,
    method: str,
    tenant: str | None,
    request: BaseModel,
    status_code: int,
    status: str,
    started: float,
    claude_session_id: str | None = None,
    session_log_file: str | None = None,
    result_file: str | None = None,
    error_detail: str | None = None,
) -> RequestAuditRecord:
    return RequestAuditRecord(
        request_id=request_id,
        route=route,
        method=method,
        tenant=tenant,
        conversation_id=getattr(request, "conversation_id", None),
        claude_session_id=claude_session_id,
        resume_session_id=getattr(request, "resume_session_id", None),
        fork_from_session_id=getattr(request, "fork_from_session_id", None),
        schema_name=getattr(request, "schema_name", None) or DEFAULT_OUTPUT_SCHEMA_NAME,
        prompt_preview=(getattr(request, "message", "") or "")[:200],
        request_payload=request.model_dump(),
        session_log_file=session_log_file,
        result_file=result_file,
        status_code=status_code,
        status=status,
        error_detail=error_detail,
        duration_ms=int((time.perf_counter() - started) * 1000),
        created_at=utc_now(),
    )


def _require_session_access(session_id: str, tenant: str) -> None:
    if get_session_record_by_session_id(session_id=session_id, tenant=tenant) is None:
        raise HTTPException(status_code=404, detail="Session not found")


def _runtime_status() -> dict[str, Any]:
    return collect_runtime_diagnostics()


def _build_chat_response(
    *,
    tenant: str,
    meta: AgentRunMeta,
    payload: dict[str, Any] | list[Any],
    default_schema_name: str,
) -> ChatResponse:
    return ChatResponse(
        request_id=meta.request_id,
        tenant=tenant,
        conversation_id=meta.conversation_id,
        claude_session_id=meta.claude_session_id,
        schema_name=meta.schema_name or default_schema_name,
        result_file=meta.result_file,
        response=payload,
        cost=meta.cost_usd,
    )


def _append_success_request_audit(
    *,
    route: str,
    tenant: str,
    request: BaseModel,
    meta: AgentRunMeta,
    started: float,
    prompt_preview: str,
) -> None:
    append_request_audit(
        RequestAuditRecord(
            request_id=meta.request_id,
            route=route,
            method="POST",
            tenant=tenant,
            conversation_id=meta.conversation_id,
            claude_session_id=meta.claude_session_id,
            resume_session_id=meta.resume_session_id,
            fork_from_session_id=meta.fork_from_session_id,
            schema_name=meta.schema_name,
            prompt_preview=prompt_preview[:200],
            request_payload=request.model_dump(),
            session_log_file=meta.log_file,
            result_file=meta.result_file,
            status_code=200,
            status="success",
            duration_ms=int((time.perf_counter() - started) * 1000),
            created_at=utc_now(),
        )
    )


def _raise_endpoint_error(
    *,
    request_id: str,
    route: str,
    tenant: str,
    request: BaseModel,
    started: float,
    status_code: int,
    detail: str,
    exc: Exception | None = None,
) -> None:
    append_request_audit(
        _build_request_audit_record(
            request_id=request_id,
            route=route,
            method="POST",
            tenant=tenant,
            request=request,
            status_code=status_code,
            status="error",
            started=started,
            error_detail=detail,
        )
    )
    raise HTTPException(status_code=status_code, detail=detail) from exc


async def _execute_json_endpoint(
    *,
    route: str,
    tenant: str,
    request: BaseModel,
    started: float,
    request_id: str,
    prompt_preview: str,
    default_schema_name: str,
    runner: Any,
) -> ChatResponse:
    try:
        payload, meta = await runner
    except JSONContractError as exc:
        _raise_endpoint_error(
            request_id=request_id,
            route=route,
            tenant=tenant,
            request=request,
            started=started,
            status_code=502,
            detail=str(exc),
            exc=exc,
        )
    except Exception as exc:
        _raise_endpoint_error(
            request_id=request_id,
            route=route,
            tenant=tenant,
            request=request,
            started=started,
            status_code=500,
            detail="Internal server error",
            exc=exc,
        )

    _append_success_request_audit(
        route=route,
        tenant=tenant,
        request=request,
        meta=meta,
        started=started,
        prompt_preview=prompt_preview,
    )
    return _build_chat_response(
        tenant=tenant,
        meta=meta,
        payload=payload,
        default_schema_name=default_schema_name,
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, authorization: str = Header(...)) -> ChatResponse:
    """Return a full JSON response for a single prompt."""
    started = time.perf_counter()
    request_id = new_request_id()
    tenant = verify_tenant(authorization)
    return await _execute_json_endpoint(
        route="/chat",
        tenant=tenant,
        request=req,
        started=started,
        request_id=request_id,
        prompt_preview=req.message,
        default_schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
        runner=run_agent_json(
            req.message,
            conversation_id=req.conversation_id,
            resume_session_id=req.resume_session_id,
            fork_from_session_id=req.fork_from_session_id,
            continue_recent=req.continue_recent,
            schema_name=req.schema_name or DEFAULT_OUTPUT_SCHEMA_NAME,
            request_id=request_id,
            tenant=tenant,
        )
    )


async def _run_command_json_endpoint(
    *,
    command_name: str,
    command_args: list[str],
    schema_name: str,
    tenant: str,
    request_id: str,
    request: BaseModel,
) -> tuple[dict | list, AgentRunMeta]:
    return await run_command_json(
        command_name,
        *command_args,
        conversation_id=getattr(request, "conversation_id", None),
        resume_session_id=getattr(request, "resume_session_id", None),
        fork_from_session_id=getattr(request, "fork_from_session_id", None),
        continue_recent=getattr(request, "continue_recent", False),
        schema_name=schema_name,
        request_id=request_id,
        tenant=tenant,
    )


async def _submit_audit_directory(*, request_id: str, directory_path: str) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "status": "accepted",
        "mode": "directory",
        "task_status_url": f"/audit/tasks/{request_id}",
        "result_url": f"/results/{request_id}",
        "directory_path": directory_path,
    }


def _schedule_directory_audit_task(*, request_id: str, tenant: str, directory_path: str) -> None:
    asyncio.create_task(
        _execute_directory_audit_task(
            request_id=request_id,
            tenant=tenant,
            directory_path=directory_path,
        )
    )


def _sanitize_upload_name(name: str, index: int) -> str:
    sanitized = Path(name).name or f"upload-{index}"
    return sanitized


def _serialize_case_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


async def _materialize_upload_submission(
    *,
    request_id: str,
    form_json: str,
    form_data: Any,
) -> str:
    try:
        parsed_form = json.loads(form_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid form_json") from exc

    if not isinstance(parsed_form, dict):
        raise HTTPException(status_code=400, detail="form_json must decode to a JSON object")

    files = form_data.getlist("files")
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required for upload mode")

    case_dir = SUBMISSION_ROOT_DIR / request_id
    case_dir.mkdir(parents=True, exist_ok=True)

    attachments: list[dict[str, Any]] = []
    for index, upload in enumerate(files, start=1):
        safe_name = _sanitize_upload_name(getattr(upload, "filename", "") or "", index)
        target_path = case_dir / safe_name
        content = await upload.read()
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
            "attachments": attachments,
        },
    )

    return _serialize_case_path(case_dir)


async def _run_directory_audit(*, request_id: str, tenant: str, directory_path: str):
    return await run_command_json(
        "audit",
        directory_path,
        schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
        request_id=request_id,
        tenant=tenant,
    )


async def _execute_directory_audit_task(*, request_id: str, tenant: str, directory_path: str) -> None:
    upsert_audit_task(
        {
            "request_id": request_id,
            "status": "running",
            "mode": "directory",
            "case_path": directory_path,
            "claim_id": None,
            "result_file": None,
            "error_detail": None,
            "updated_at": utc_now(),
        }
    )
    try:
        payload, meta = await _run_directory_audit(
            request_id=request_id,
            tenant=tenant,
            directory_path=directory_path,
        )
        upsert_audit_task(
            {
                "request_id": request_id,
                "status": "completed",
                "mode": "directory",
                "case_path": directory_path,
                "claim_id": payload.get("claim_id") if isinstance(payload, dict) else None,
                "result_file": meta.result_file,
                "error_detail": None,
                "updated_at": utc_now(),
            }
        )
    except Exception as exc:
        upsert_audit_task(
            {
                "request_id": request_id,
                "status": "failed",
                "mode": "directory",
                "case_path": directory_path,
                "claim_id": None,
                "result_file": None,
                "error_detail": str(exc),
                "updated_at": utc_now(),
            }
        )


@app.post("/audit", response_model=ChatResponse)
async def audit(req: AuditRequest, authorization: str = Header(...)) -> ChatResponse:
    """Run audit for a source file path or a directory path."""
    started = time.perf_counter()
    request_id = new_request_id()
    tenant = verify_tenant(authorization)
    return await _execute_json_endpoint(
        route="/audit",
        tenant=tenant,
        request=req,
        started=started,
        request_id=request_id,
        prompt_preview=f"/audit {req.path}",
        default_schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
        runner=_run_command_json_endpoint(
            command_name="audit",
            command_args=[req.path],
            schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
            tenant=tenant,
            request_id=request_id,
            request=req,
        )
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
        payload = DirectoryAuditSubmitRequest.model_validate(await request.json())
        mode = payload.mode
        case_path = payload.directory_path
    elif content_type.startswith("multipart/form-data"):
        form_data = await request.form()
        mode = str(form_data.get("mode") or "").strip()
        if mode != "upload":
            raise HTTPException(status_code=400, detail="multipart requests must use mode=upload")
        form_json = str(form_data.get("form_json") or "").strip()
        if not form_json:
            raise HTTPException(status_code=400, detail="form_json is required for upload mode")
        case_path = await _materialize_upload_submission(
            request_id=request_id,
            form_json=form_json,
            form_data=form_data,
        )
    else:
        raise HTTPException(status_code=415, detail="Unsupported Content-Type")

    upsert_audit_task(
        {
            "request_id": request_id,
            "status": "accepted",
            "mode": mode,
            "case_path": case_path,
            "claim_id": None,
            "result_file": None,
            "error_detail": None,
            "updated_at": utc_now(),
        }
    )
    response = await _submit_audit_directory(request_id=request_id, directory_path=case_path)
    _schedule_directory_audit_task(
        request_id=request_id,
        tenant=tenant,
        directory_path=case_path,
    )
    return AuditSubmitAcceptedResponse(
        request_id=response["request_id"],
        status=response["status"],
        mode=mode,
        task_status_url=response["task_status_url"],
        result_url=response["result_url"],
    )


@app.get("/audit/tasks/{request_id}")
async def audit_task_status(request_id: str, authorization: str = Header(...)) -> dict[str, Any]:
    verify_tenant(authorization)
    record = get_audit_task(request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Audit task not found")
    return record


@app.post("/init-rules", response_model=ChatResponse)
async def init_rules(req: InitRulesRequest, authorization: str = Header(...)) -> ChatResponse:
    started = time.perf_counter()
    request_id = new_request_id()
    tenant = verify_tenant(authorization)
    try:
        canonical_source, _ = prepare_text_proxy(req.source_path, PROJECT_ROOT / "logs" / "service" / "init-rules")
    except ValueError as exc:
        _raise_endpoint_error(
            request_id=request_id,
            route="/init-rules",
            tenant=tenant,
            request=req,
            started=started,
            status_code=400,
            detail=str(exc),
            exc=exc,
        )

    return await _execute_json_endpoint(
        route="/init-rules",
        tenant=tenant,
        request=req,
        started=started,
        request_id=request_id,
        prompt_preview=f"/init-rules {req.source_path} {req.domain}",
        default_schema_name=INIT_RULES_REPORT_SCHEMA_NAME,
        runner=_run_command_json_endpoint(
            command_name="init-rules",
            command_args=[canonical_source, req.domain],
            schema_name=INIT_RULES_REPORT_SCHEMA_NAME,
            tenant=tenant,
            request_id=request_id,
            request=req,
        )
    )


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, authorization: str = Header(...)) -> StreamingResponse:
    """Return an SSE stream whose final payload is structured JSON."""
    started = time.perf_counter()
    request_id = new_request_id()
    tenant = verify_tenant(authorization)

    async def event_generator():
        try:
            response, meta = await run_agent_json(
                req.message,
                conversation_id=req.conversation_id,
                resume_session_id=req.resume_session_id,
                fork_from_session_id=req.fork_from_session_id,
                continue_recent=req.continue_recent,
                schema_name=req.schema_name or DEFAULT_OUTPUT_SCHEMA_NAME,
                request_id=request_id,
                tenant=tenant,
            )
            payload = json.dumps(
                {
                    "type": "result",
                    "request_id": meta.request_id,
                    "tenant": tenant,
                    "conversation_id": meta.conversation_id,
                    "claude_session_id": meta.claude_session_id,
                    "schema_name": meta.schema_name,
                    "result_file": meta.result_file,
                    "content": response,
                    "cost": meta.cost_usd,
                },
                ensure_ascii=False,
            )
            append_request_audit(
                RequestAuditRecord(
                    request_id=meta.request_id,
                    route="/chat/stream",
                    method="POST",
                    tenant=tenant,
                    conversation_id=meta.conversation_id,
                    claude_session_id=meta.claude_session_id,
                    resume_session_id=meta.resume_session_id,
                    fork_from_session_id=meta.fork_from_session_id,
                    schema_name=meta.schema_name,
                    prompt_preview=req.message[:200],
                    request_payload=req.model_dump(),
                    session_log_file=meta.log_file,
                    result_file=meta.result_file,
                    status_code=200,
                    status="success",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    created_at=utc_now(),
                )
            )
            yield f"data: {payload}\n\n"
        except JSONContractError as exc:
            append_request_audit(
                _build_request_audit_record(
                    request_id=request_id,
                    route="/chat/stream",
                    method="POST",
                    tenant=tenant,
                    request=req,
                    status_code=502,
                    status="error",
                    started=started,
                    error_detail=str(exc),
                )
            )
            payload = json.dumps(
                {
                    "type": "error",
                    "request_id": request_id,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
            yield f"data: {payload}\n\n"
        except Exception as exc:
            append_request_audit(
                _build_request_audit_record(
                    request_id=request_id,
                    route="/chat/stream",
                    method="POST",
                    tenant=tenant,
                    request=req,
                    status_code=500,
                    status="error",
                    started=started,
                    error_detail=str(exc),
                )
            )
            payload = json.dumps(
                {
                    "type": "error",
                    "request_id": request_id,
                    "error": "internal_server_error",
                },
                ensure_ascii=False,
            )
            yield f"data: {payload}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/health")
async def health() -> dict[str, Any]:
    return _runtime_status()


@app.get("/ready")
async def ready() -> JSONResponse:
    payload = _runtime_status()
    status_code = 200 if payload["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/sessions")
async def sessions(
    conversation_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
    authorization: str = Header(...),
) -> dict[str, Any]:
    tenant = verify_tenant(authorization)
    known_session_ids = list_known_session_ids(tenant=tenant)
    return {
        "logged_sessions": list_logged_sessions(
            conversation_id=conversation_id,
            tenant=tenant,
            limit=limit,
            offset=offset,
        ),
        "sdk_sessions": list_sdk_session_summaries(limit=limit, session_ids=known_session_ids),
    }


@app.get("/conversations")
async def conversations(
    limit: int = 20,
    offset: int = 0,
    authorization: str = Header(...),
) -> dict[str, Any]:
    tenant = verify_tenant(authorization)
    return {
        "items": list_conversation_summaries(tenant=tenant, limit=limit, offset=offset),
    }


@app.get("/requests")
async def requests(
    conversation_id: str | None = None,
    claude_session_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
    authorization: str = Header(...),
) -> dict[str, Any]:
    tenant = verify_tenant(authorization)
    return {
        "items": list_request_audits(
            tenant=tenant,
            conversation_id=conversation_id,
            claude_session_id=claude_session_id,
            limit=limit,
            offset=offset,
        ),
    }


@app.get("/requests/{request_id}")
async def request_detail(request_id: str, authorization: str = Header(...)) -> dict[str, Any]:
    tenant = verify_tenant(authorization)
    record = get_request_audit_by_request_id(request_id=request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return record


@app.get("/results")
async def results(
    conversation_id: str | None = None,
    claim_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
    authorization: str = Header(...),
) -> dict[str, Any]:
    tenant = verify_tenant(authorization)
    return {
        "items": list_result_records(
            tenant=tenant,
            conversation_id=conversation_id,
            claim_id=claim_id,
            limit=limit,
            offset=offset,
        ),
    }


@app.get("/results/{request_id}")
async def result_detail(request_id: str, authorization: str = Header(...)) -> dict[str, Any]:
    tenant = verify_tenant(authorization)
    record = get_result_record_by_request_id(request_id=request_id, tenant=tenant)
    if record is None:
        raise HTTPException(status_code=404, detail="Result not found")
    payload = get_result_payload_by_request_id(request_id=request_id, tenant=tenant)
    return {
        "record": record,
        "payload": payload,
    }


@app.get("/sessions/{session_id}/messages")
async def session_messages(
    session_id: str,
    limit: int = 100,
    offset: int = 0,
    authorization: str = Header(...),
) -> dict[str, Any]:
    tenant = verify_tenant(authorization)
    _require_session_access(session_id=session_id, tenant=tenant)
    return {
        "session_id": session_id,
        "messages": get_sdk_session_transcript(session_id=session_id, limit=limit, offset=offset),
    }
