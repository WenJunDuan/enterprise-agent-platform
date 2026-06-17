"""HTTP API assembly and tenant authentication for the Enterprise Agent Platform.

Responsibilities:
- App factory: FastAPI instance, middleware stack, lifespan, exception handlers.
- Tenant authentication: ``verify_tenant`` and ``TENANT_KEYS`` (re-exported here so
  external callers such as tests and route modules can import from a single stable
  location without knowing the internal layout).
- Router wiring: delegates all HTTP route logic to ``server.routes.*``.

Route implementations live in:
- ``server/routes/audit.py``    — audit task CRUD (/audit/*)
- ``server/routes/health.py``   — readiness probe (/health)
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match
from starlette.types import ASGIApp, Receive, Scope, Send

from server.platform.config import get_app_settings, load_tenant_keys, tenant_keys_are_default
from server.platform.logging_setup import configure_logging, logging_context
from server.platform.paths import PROJECT_ROOT
from server.stores.audit_task_store import recover_stale_audit_tasks

configure_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format=(
        "kv"
        if os.getenv("DEV", "").lower() in {"1", "true", "yes", "on"}
        or os.getenv("LOG_FORMAT") == "kv"
        else "json"
    ),
)
logger = logging.getLogger(__name__)


# ── tenant authentication ─────────────────────────────────────────────────────

TENANT_KEYS = load_tenant_keys()


def _authorization_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def verify_tenant(authorization: str | None) -> str:
    """Validate the Bearer token and return the matching tenant name.

    Raises:
        HTTPException: 401 when credentials are missing or invalid.
        HTTPException: 503 when the server has not been configured with tenant keys.
    """
    allow_default = os.getenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if tenant_keys_are_default():
        if not allow_default:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Server is not configured with tenant keys. "
                    "Set the TENANT_KEYS environment variable."
                ),
            )
    if not authorization:
        # When running in insecure dev mode, skip auth header requirement entirely.
        if allow_default:
            return "default"
        raise _authorization_error("Missing Authorization header")
    scheme, _, credentials = authorization.strip().partition(" ")
    if scheme.lower() != "bearer" or not credentials.strip():
        raise _authorization_error("Authorization header must use Bearer token")
    token = credentials.strip()
    for tenant, key in TENANT_KEYS.items():
        if secrets.compare_digest(key, token):
            return tenant
    raise _authorization_error("Invalid tenant token")


# ── lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    settings = get_app_settings()
    recover_stale_audit_tasks(settings.audit_task_running_timeout_seconds)
    yield


# ── app ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Enterprise Agent API", version="0.1.0", lifespan=app_lifespan)


# ── CORS middleware ───────────────────────────────────────────────────────────


def _resolve_cors_origins() -> tuple[list[str], list[str]]:
    default_origins = "http://localhost:5173,http://127.0.0.1:5173"
    raw = os.getenv("CORS_ALLOWED_ORIGINS", default_origins)
    origins: list[str] = []
    regexes: list[str] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        if value == "*":
            origins.append("*")
            continue
        if value.startswith("re:"):
            regexes.append(value[len("re:") :])
            continue
        origins.append(value.rstrip("/"))
    return origins, regexes


_cors_origins, _cors_origin_regexes = _resolve_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex="|".join(_cors_origin_regexes) if _cors_origin_regexes else None,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── strict route gate ─────────────────────────────────────────────────────────


class StrictRouteMiddleware:
    """ASGI gate: drop any HTTP request whose path does not match a registered route."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        fastapi_app = scope.get("app")
        if fastapi_app is not None:
            for route in fastapi_app.routes:
                match, _ = route.matches(scope)
                if match != Match.NONE:
                    await self.app(scope, receive, send)
                    return
        client = scope.get("client") or ("", 0)
        logger.warning(
            "rejected_unknown_route",
            extra={
                "path": scope.get("path"),
                "method": scope.get("method"),
                "client_host": client[0],
            },
        )
        response = JSONResponse({"detail": "Not Found"}, status_code=404)
        await response(scope, receive, send)


app.add_middleware(StrictRouteMiddleware)


# ── request correlation middleware ────────────────────────────────────────────


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request.state.correlation_id = correlation_id
    with logging_context(correlation_id=correlation_id):
        response = await call_next(request)
    response.headers["X-Request-ID"] = correlation_id
    return response


# ── error response helpers ────────────────────────────────────────────────────


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


# ── exception handlers ────────────────────────────────────────────────────────


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
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
        extra={
            "path": request.url.path,
            "correlation_id": getattr(request.state, "correlation_id", None),
        },
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


# ── route registration ────────────────────────────────────────────────────────

from server.routes import audit as _audit_routes  # noqa: E402
from server.routes import health as _health_routes  # noqa: E402
from server.routes import ocr as _ocr_routes  # noqa: E402

app.include_router(_audit_routes.router, prefix="/audit")
app.include_router(_ocr_routes.router, prefix="/ocr")
app.include_router(_health_routes.router)


# ── SPA static file serving ───────────────────────────────────────────────────

# 同源部署：让 FastAPI 直接托管前端 dist 静态文件，避免 CORS。
# 关闭方式：设置 SERVE_UI_DIST=false。
def _ui_dist_dir() -> Path | None:
    if os.getenv("SERVE_UI_DIST", "true").lower() in {"0", "false", "no", "off"}:
        logger.info("ui_static_disabled", extra={"reason": "SERVE_UI_DIST=false"})
        return None
    raw = os.getenv("UI_DIST_DIR", "").strip()
    candidate = Path(raw) if raw else (PROJECT_ROOT / "ui" / "dist")
    if not candidate.is_dir():
        logger.warning(
            "ui_static_dir_missing",
            extra={"resolved_path": str(candidate), "project_root": str(PROJECT_ROOT)},
        )
        return None
    if not (candidate / "index.html").is_file():
        logger.warning(
            "ui_static_index_missing",
            extra={"resolved_path": str(candidate), "expected": str(candidate / "index.html")},
        )
        return None
    logger.info("ui_static_enabled", extra={"resolved_path": str(candidate)})
    return candidate


_UI_DIST = _ui_dist_dir()
if _UI_DIST is not None:
    _ASSETS_DIR = _UI_DIST / "assets"
    if _ASSETS_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=_ASSETS_DIR), name="ui-assets")

    @app.get("/{spa_path:path}", include_in_schema=False)
    async def spa_fallback(spa_path: str) -> FileResponse:
        # 已被前面的 API 路由匹配的请求不会进到这里。
        # 仅用来：1) 直接返回 dist 根下的具体文件 (vite.svg、favicon 等)；
        # 2) 任何 SPA 路径回退到 index.html，让前端路由接管。
        index_html = _UI_DIST / "index.html"
        if spa_path:
            candidate = (_UI_DIST / spa_path).resolve()
            try:
                candidate.relative_to(_UI_DIST.resolve())
            except ValueError:
                raise HTTPException(status_code=404, detail="Not Found")
            if candidate.is_file():
                return FileResponse(candidate)
        if not index_html.is_file():
            raise HTTPException(status_code=500, detail=f"index.html not found at {index_html}")
        return FileResponse(index_html)
