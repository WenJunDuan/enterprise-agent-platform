"""Minimal FastAPI service for proxying chat requests to a configured upstream model."""

from contextlib import asynccontextmanager
from time import perf_counter
import uuid

from fastapi import FastAPI, HTTPException
from fastapi import Request
from pydantic import BaseModel, Field

from server.core import MemoryWriteError, run_chat
from server.logging_config import configure_logging, get_logger
from server.model_client import UpstreamError, load_settings


logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging_settings = configure_logging()
    settings = load_settings()

    logger.info(
        "service startup base_url=%s model=%s log_level=%s log_file=%s",
        settings.base_url,
        settings.model,
        logging_settings.level_name,
        logging_settings.log_file,
    )
    if settings.api_key is None:
        logger.warning("upstream api key not configured; requests will be sent without Authorization header")

    yield

    logger.info("service shutdown")


app = FastAPI(title="Enterprise Agent Platform", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    start = perf_counter()

    logger.debug(
        "request started request_id=%s method=%s path=%s",
        request_id,
        request.method,
        request.url.path,
    )

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = (perf_counter() - start) * 1000
        logger.error(
            "request failed request_id=%s method=%s path=%s duration_ms=%.1f error=%s",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
            exc,
        )
        raise

    duration_ms = (perf_counter() - start) * 1000
    if response.status_code >= 500:
        log_method = logger.error
    elif response.status_code >= 400:
        log_method = logger.warning
    else:
        log_method = logger.info

    log_method(
        "request completed request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health")
def health(request: Request) -> dict[str, object]:
    settings = load_settings()
    logger.debug("health requested request_id=%s", getattr(request.state, "request_id", "-"))
    return {
        "status": "ok",
        "base_url": settings.base_url,
        "model": settings.model,
        "api_key_configured": settings.api_key is not None,
    }


@app.post("/chat")
def chat(request: ChatRequest, raw_request: Request) -> dict[str, str]:
    settings = load_settings()
    request_id = getattr(raw_request.state, "request_id", "-")

    logger.debug(
        "chat accepted request_id=%s model=%s message_chars=%s",
        request_id,
        settings.model,
        len(request.message),
    )

    try:
        result = run_chat(
            request.message,
            source="http",
            request_id=request_id,
            settings=settings,
        )
    except UpstreamError as exc:
        logger.error(
            "chat failed request_id=%s model=%s error=%s",
            request_id,
            settings.model,
            exc,
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except MemoryWriteError as exc:
        logger.error(
            "chat failed request_id=%s model=%s error=%s",
            request_id,
            settings.model,
            exc,
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info(
        "chat completed request_id=%s model=%s response_chars=%s",
        request_id,
        settings.model,
        len(result.output_text),
    )
    return {"model": settings.model, "response": result.output_text}
