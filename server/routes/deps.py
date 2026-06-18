"""Shared FastAPI route dependencies.

Tenant authentication lives here — not in ``server.api`` — so route modules can
depend on it without importing back into the app module. This keeps the
``api → routes`` dependency one-directional and removes the lazy-import
workaround that previously broke the ``api ↔ routes`` cycle.

``server.api`` re-exports ``verify_tenant`` / ``TENANT_KEYS`` for the stable
public import path; new code should import them from here.
"""

from __future__ import annotations

import os
import secrets

from fastapi import HTTPException

from server.platform.config import load_tenant_keys, tenant_keys_are_default

# Tenant keys are resolved once at import. Tests monkeypatch this module global
# (server.routes.deps.TENANT_KEYS) to inject fixtures without touching env state.
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
