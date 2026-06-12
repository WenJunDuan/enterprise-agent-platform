"""Unit tests for server/api.py – verify_tenant authentication logic.

Importing server.api triggers configure_logging + CORSMiddleware setup at module level.
We set up the minimal required env vars before import to suppress undesired side effects.
No network calls, no real claude_agent_sdk invocations.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

# Env-var offline-guard bypass is now centralised in tests/conftest.py.

from server.api import verify_tenant


# ═════════════════════════════════════════════════════════════════════════════
# verify_tenant
# ═════════════════════════════════════════════════════════════════════════════


class TestVerifyTenant:
    """Tests for the Bearer-token tenant authentication gate."""

    # ── helpers ──────────────────────────────────────────────────────────────

    def _patch(self, monkeypatch, *, tenant_keys: dict[str, str], is_default: bool = False):
        """Patch tenant key config so tests don't depend on env-var state."""
        monkeypatch.setattr("server.api.TENANT_KEYS", tenant_keys)
        monkeypatch.setattr(
            "server.platform.config.tenant_keys_are_default",
            lambda raw=None: is_default,
        )
        # Also patch the version imported directly into server.api
        import server.api as api_module

        monkeypatch.setattr(api_module, "tenant_keys_are_default", lambda: is_default)

    # ── missing Authorization header ─────────────────────────────────────────

    def test_missing_auth_header_non_default_config_raises_401(self, monkeypatch):
        self._patch(monkeypatch, tenant_keys={"acme": "test-fake-token-acme-xyz"}, is_default=False)
        monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
        with pytest.raises(HTTPException) as exc_info:
            verify_tenant(None)
        assert exc_info.value.status_code == 401

    def test_missing_auth_header_insecure_dev_mode_returns_default(self, monkeypatch):
        """在 ALLOW_INSECURE_DEFAULT_TENANT_KEY=1 模式下，缺头时直接返回 'default'。"""
        self._patch(monkeypatch, tenant_keys={"default": "test-fake-token-default-xyz"}, is_default=True)
        monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "1")
        result = verify_tenant(None)
        assert result == "default"

    # ── non-Bearer scheme ────────────────────────────────────────────────────

    def test_non_bearer_scheme_raises_401(self, monkeypatch):
        self._patch(monkeypatch, tenant_keys={"acme": "test-fake-token-acme-xyz"}, is_default=False)
        monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
        with pytest.raises(HTTPException) as exc_info:
            verify_tenant("Basic dXNlcjpwYXNz")
        assert exc_info.value.status_code == 401
        assert "Bearer" in exc_info.value.detail

    def test_empty_credentials_after_bearer_raises_401(self, monkeypatch):
        self._patch(monkeypatch, tenant_keys={"acme": "test-fake-token-acme-xyz"}, is_default=False)
        monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
        with pytest.raises(HTTPException) as exc_info:
            verify_tenant("Bearer   ")
        assert exc_info.value.status_code == 401

    # ── invalid token ────────────────────────────────────────────────────────

    def test_invalid_token_raises_401(self, monkeypatch):
        self._patch(monkeypatch, tenant_keys={"acme": "test-fake-token-acme-xyz"}, is_default=False)
        monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
        with pytest.raises(HTTPException) as exc_info:
            verify_tenant("Bearer test-fake-token-wrong-one")
        assert exc_info.value.status_code == 401

    # ── valid token ──────────────────────────────────────────────────────────

    def test_valid_token_returns_tenant_name(self, monkeypatch):
        self._patch(monkeypatch, tenant_keys={"acme": "test-fake-token-acme-xyz"}, is_default=False)
        monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
        result = verify_tenant("Bearer test-fake-token-acme-xyz")
        assert result == "acme"

    def test_valid_token_with_extra_whitespace(self, monkeypatch):
        """Authorization 值前后的空白应被 strip 掉。"""
        self._patch(monkeypatch, tenant_keys={"acme": "test-fake-token-acme-xyz"}, is_default=False)
        monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
        result = verify_tenant("  Bearer test-fake-token-acme-xyz  ")
        assert result == "acme"

    def test_multiple_tenants_correct_one_returned(self, monkeypatch):
        keys = {
            "tenant_a": "test-fake-token-a-aaaa",
            "tenant_b": "test-fake-token-b-bbbb",
        }
        self._patch(monkeypatch, tenant_keys=keys, is_default=False)
        monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
        assert verify_tenant("Bearer test-fake-token-b-bbbb") == "tenant_b"

    # ── default-keys guard ───────────────────────────────────────────────────

    def test_default_keys_without_insecure_flag_raises_503(self, monkeypatch):
        """生产环境若未配置 TENANT_KEYS，拒绝所有请求，返回 503。"""
        self._patch(monkeypatch, tenant_keys={"default": "sk-default"}, is_default=True)
        monkeypatch.setenv("ALLOW_INSECURE_DEFAULT_TENANT_KEY", "")
        with pytest.raises(HTTPException) as exc_info:
            verify_tenant("Bearer sk-default")
        assert exc_info.value.status_code == 503
