"""HTTP API and runtime diagnostics for the local serve layer."""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, model_validator

from server.platform.config import get_app_settings, load_tenant_keys
from server.core import (
    DEFAULT_OUTPUT_SCHEMA_NAME,
    JSONContractError,
    run_agent_json,
)
from server.platform.diagnostics import collect_runtime_diagnostics
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


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    resume_session_id: str | None = None
    fork_from_session_id: str | None = None
    continue_recent: bool = False
    schema_name: str | None = None

    @model_validator(mode="after")
    def validate_session_controls(self) -> "ChatRequest":
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


class ChatResponse(BaseModel):
    request_id: str
    tenant: str
    conversation_id: str
    claude_session_id: str | None = None
    schema_name: str
    result_file: str | None = None
    response: dict[str, Any] | list[Any]
    cost: float


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
    request: ChatRequest,
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
        conversation_id=request.conversation_id,
        claude_session_id=claude_session_id,
        resume_session_id=request.resume_session_id,
        fork_from_session_id=request.fork_from_session_id,
        schema_name=request.schema_name or DEFAULT_OUTPUT_SCHEMA_NAME,
        prompt_preview=request.message[:200],
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


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, authorization: str = Header(...)) -> ChatResponse:
    """Return a full JSON response for a single prompt."""
    started = time.perf_counter()
    request_id = new_request_id()
    tenant = verify_tenant(authorization)
    try:
        payload, meta = await run_agent_json(
            req.message,
            conversation_id=req.conversation_id,
            resume_session_id=req.resume_session_id,
            fork_from_session_id=req.fork_from_session_id,
            continue_recent=req.continue_recent,
            schema_name=req.schema_name or DEFAULT_OUTPUT_SCHEMA_NAME,
            request_id=request_id,
            tenant=tenant,
        )
    except JSONContractError as exc:
        append_request_audit(
            _build_request_audit_record(
                request_id=request_id,
                route="/chat",
                method="POST",
                tenant=tenant,
                request=req,
                status_code=502,
                status="error",
                started=started,
                error_detail=str(exc),
            )
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        append_request_audit(
            _build_request_audit_record(
                request_id=request_id,
                route="/chat",
                method="POST",
                tenant=tenant,
                request=req,
                status_code=500,
                status="error",
                started=started,
                error_detail=str(exc),
            )
        )
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    append_request_audit(
        RequestAuditRecord(
            request_id=meta.request_id,
            route="/chat",
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

    return ChatResponse(
        request_id=meta.request_id,
        tenant=tenant,
        conversation_id=meta.conversation_id,
        claude_session_id=meta.claude_session_id,
        schema_name=meta.schema_name or DEFAULT_OUTPUT_SCHEMA_NAME,
        result_file=meta.result_file,
        response=payload,
        cost=meta.cost_usd,
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
