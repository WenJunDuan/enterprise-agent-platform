"""Shared runtime diagnostics for API health and local maintenance commands."""

from __future__ import annotations

from typing import Any

from server.platform.config import load_tenant_keys, runtime_setting_snapshot
from server.core import DEFAULT_OUTPUT_SCHEMA_NAME, build_output_format
from server.stores.request_store import describe_request_store
from server.stores.result_store import describe_result_store
from server.stores.runtime_store import runtime_status_snapshot
from server.stores.session_store import describe_session_store


def collect_runtime_diagnostics() -> dict[str, Any]:
    """Collect a shared runtime health snapshot for API and CLI diagnostics."""
    session_store = describe_session_store()
    request_store = describe_request_store()
    result_store = describe_result_store()
    runtime_status = runtime_status_snapshot()

    tenant_keys, tenant_error = _load_tenant_key_report()
    default_contract, contract_error = _load_schema_report()
    runtime_settings = runtime_setting_snapshot()

    checks = {
        "tenant_keys": {
            "ok": tenant_error is None and bool(tenant_keys),
            "count": len(tenant_keys),
            "error": tenant_error,
        },
        "default_output_schema": {
            "ok": contract_error is None,
            "schema_name": DEFAULT_OUTPUT_SCHEMA_NAME,
            "title": default_contract["schema"].get("title") if default_contract else None,
            "error": contract_error,
        },
        "session_store": {
            "ok": session_store["parent_exists"] and session_store["writable"],
            **session_store,
        },
        "request_store": {
            "ok": request_store["parent_exists"] and request_store["writable"],
            **request_store,
        },
        "result_store": {
            "ok": result_store["parent_exists"] and result_store["writable"],
            **result_store,
        },
        "runtime_config": {
            "ok": True,
            **runtime_settings,
        },
        "app_server": {
            "ok": True,
            **runtime_status,
        },
    }

    advisories: list[str] = []
    if not (
        runtime_settings["anthropic_api_key_configured"]
        or runtime_settings["anthropic_auth_token_configured"]
    ):
        advisories.append("Neither ANTHROPIC_API_KEY nor ANTHROPIC_AUTH_TOKEN is configured.")
    if not runtime_status["running"]:
        advisories.append("app-server process is not running.")

    status = "ok" if all(check["ok"] for check in checks.values()) else "degraded"
    return {
        "status": status,
        "storage_backend": "local-jsonl-and-json",
        "checks": checks,
        "advisories": advisories,
    }


def _load_tenant_key_report() -> tuple[dict[str, str], str | None]:
    try:
        tenant_keys = load_tenant_keys()
    except Exception as exc:  # pragma: no cover - defensive guard
        return {}, str(exc)
    return tenant_keys, None


def _load_schema_report() -> tuple[dict[str, Any] | None, str | None]:
    try:
        default_contract = build_output_format(DEFAULT_OUTPUT_SCHEMA_NAME)
    except Exception as exc:  # pragma: no cover - defensive guard
        return None, str(exc)
    return default_contract, None
