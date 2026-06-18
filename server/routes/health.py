"""Operational / diagnostics routes: /health.

No business logic here — just the public readiness probe that aggregates
runtime diagnostics into a single JSON response.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from server.ops.diagnostics import collect_runtime_diagnostics

router = APIRouter(tags=["ops"])


def _public_runtime_status() -> dict:
    """Collapse full runtime diagnostics into the fields safe to expose publicly."""
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


@router.get("/health")
async def health() -> JSONResponse:
    payload = _public_runtime_status()
    status_code = 200 if payload["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=payload)
