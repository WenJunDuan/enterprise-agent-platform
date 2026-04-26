from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from server import api as api_module
from server.platform import config as config_module


def test_default_tenant_keys_are_flagged(
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.delenv("TENANT_KEYS", raising=False)
    monkeypatch.setattr(config_module, "_DEFAULT_TENANT_KEY_WARNING_EMITTED", False)
    caplog.set_level(logging.WARNING)

    config_module.load_tenant_keys()
    snapshot = config_module.runtime_setting_snapshot()

    assert snapshot["tenant_keys_are_default"] is True
    assert "TENANT_KEYS env var not set" in caplog.text


def test_ready_reports_non_default_tenant_keys(
    monkeypatch,
    isolated_local_layout,
) -> None:
    monkeypatch.setenv("TENANT_KEYS", '{"tenantA":"sk-A"}')
    monkeypatch.setattr(config_module, "_DEFAULT_TENANT_KEY_WARNING_EMITTED", False)
    client = TestClient(api_module.app)

    response = client.get("/health")

    assert response.status_code in {200, 503}
    payload = response.json()
    assert "checks" not in payload
    assert "tenant_keys" not in payload["failing_checks"]
