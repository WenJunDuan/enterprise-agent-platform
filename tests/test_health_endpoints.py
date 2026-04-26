from __future__ import annotations

from server import api as api_module


def _diagnostics_payload(*, status: str, failing_tenant_keys: bool = False) -> dict:
    tenant_keys_ok = not failing_tenant_keys
    return {
        "status": status,
        "storage_backend": "sqlite-index+json-archives+jsonl-logs",
        "checks": {
            "tenant_keys": {
                "ok": tenant_keys_ok,
                "count": 0 if failing_tenant_keys else 1,
                "error": None if tenant_keys_ok else "TENANT_KEYS must be a JSON object",
            },
            "default_output_schema": {
                "ok": True,
                "schema_name": "common/audit-result.schema.json",
                "title": "Audit Result",
                "error": None,
            },
            "session_store": {"ok": True, "parent_exists": True, "writable": True},
            "request_store": {"ok": True, "parent_exists": True, "writable": True},
            "result_store": {"ok": True, "parent_exists": True, "writable": True},
            "memory_store": {"ok": True, "parent_exists": True, "writable": True},
            "knowledge_assets": {"ok": True, "status": "ok"},
            "runtime_config": {"ok": True, "tenant_keys_are_default": False},
            "app_server": {
                "ok": True,
                "record": {
                    "process_name": "enterprise-agent-api",
                    "status": "stopped",
                    "pid": None,
                    "host": "0.0.0.0",
                    "port": 9999,
                    "command": ["python", "-m", "uvicorn", "server.api:app"],
                    "started_at": "2026-04-22T02:31:22.156155+00:00",
                    "stopped_at": "2026-04-22T02:35:48.718080+00:00",
                    "updated_at": "2026-04-22T02:35:48.718093+00:00",
                    "pid_file": "/tmp/server.pid",
                    "stdout_log": "/tmp/stdout.log",
                    "stderr_log": "/tmp/stderr.log",
                    "cwd": "/tmp/project",
                    "last_error": None,
                },
                "pid": None,
                "running": False,
                "status_file": "/tmp/server.status.json",
                "stdout_log": "/tmp/stdout.log",
                "stderr_log": "/tmp/stderr.log",
            },
        },
        "advisories": [
            "TENANT_KEYS must be a JSON object"
            if failing_tenant_keys
            else "app-server process is not running."
        ],
    }


def test_health_returns_compact_public_payload(client, monkeypatch) -> None:
    monkeypatch.setattr(
        api_module,
        "collect_runtime_diagnostics",
        lambda: _diagnostics_payload(status="ok"),
    )

    response = client.get("/health")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["app_server"] == {"ok": True, "running": False}
    assert body["failing_checks"] == []
    assert body["advisories"] == []
    assert "checks" not in body
    assert "storage_backend" not in body


def test_health_returns_503_when_degraded(client, monkeypatch) -> None:
    monkeypatch.setattr(
        api_module,
        "collect_runtime_diagnostics",
        lambda: _diagnostics_payload(status="degraded", failing_tenant_keys=True),
    )

    response = client.get("/health")

    assert response.status_code == 503, response.text
    body = response.json()
    assert body["status"] == "degraded"
    assert body["failing_checks"] == ["tenant_keys"]
    assert body["advisories"] == ["TENANT_KEYS must be a JSON object"]
    assert body["app_server"]["running"] is False
    assert "checks" not in body


def test_ready_route_is_not_exposed() -> None:
    paths = {route.path for route in api_module.app.routes}

    assert "/ready" not in paths
