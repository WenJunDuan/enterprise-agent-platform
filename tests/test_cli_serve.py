from __future__ import annotations

import json

from server import api as api_module
from server import app_server as app_server_module
from server import cli as cli_module
from server.stores import review_delta_store as review_delta_store_module
from server.platform import config as config_module
from typer.testing import CliRunner


RUNNER = CliRunner()


def test_cli_serve_uses_env_host_and_port_by_default(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(app: str, *, host: str, port: int, reload: bool) -> None:
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port
        captured["reload"] = reload

    config_module.get_app_settings.cache_clear()
    monkeypatch.setenv("APP_SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("APP_SERVER_PORT", "9999")
    monkeypatch.setattr(cli_module.uvicorn, "run", fake_run)

    result = RUNNER.invoke(cli_module.app, ["serve"])

    assert result.exit_code == 0, result.stdout

    assert captured == {
        "app": "server.api:app",
        "host": "0.0.0.0",
        "port": 9999,
        "reload": False,
    }


def test_cli_serve_explicit_args_override_env(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(app: str, *, host: str, port: int, reload: bool) -> None:
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port
        captured["reload"] = reload

    config_module.get_app_settings.cache_clear()
    monkeypatch.setenv("APP_SERVER_HOST", "0.0.0.0")
    monkeypatch.setenv("APP_SERVER_PORT", "9999")
    monkeypatch.setattr(cli_module.uvicorn, "run", fake_run)

    result = RUNNER.invoke(
        cli_module.app,
        ["serve", "--host", "127.0.0.1", "--port", "8000"],
    )

    assert result.exit_code == 0, result.stdout

    assert captured == {
        "app": "server.api:app",
        "host": "127.0.0.1",
        "port": 8000,
        "reload": False,
    }


def test_distill_memory_is_not_exposed_as_http_api() -> None:
    paths = {route.path for route in api_module.app.routes}

    assert "/distill-memory" not in paths
    assert "/ready" not in paths
    assert "/chat" not in paths
    assert "/chat/stream" not in paths
    assert "/audit" not in paths
    assert "/init-rules" not in paths
    assert "/requests" not in paths
    assert "/results" not in paths
    assert "/memories" not in paths
    assert "/review-deltas" not in paths
    assert "/governance/assets" not in paths


def test_app_server_help_does_not_expose_inspect_command() -> None:
    result = RUNNER.invoke(app_server_module.app, ["--help"])

    assert result.exit_code == 0, result.stdout
    assert "inspect" not in result.stdout


def test_app_server_doctor_help_does_not_expose_require_ready() -> None:
    result = RUNNER.invoke(app_server_module.app, ["doctor", "--help"])

    assert result.exit_code == 0, result.stdout
    assert "--require-ready" not in result.stdout


def test_cli_validate_assets_returns_ok_report() -> None:
    result = RUNNER.invoke(cli_module.app, ["validate-assets"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"


def test_cli_review_delta_detail_returns_payload() -> None:
    review_delta_store_module.archive_review_delta_payload(
        request_id="req-cli-review-1",
        tenant=None,
        conversation_id="conv-cli-review-1",
        claude_session_id="sess-cli-review-1",
        payload={
            "claim_id": "EXP-CLI-001",
            "initial_verdict": "approved",
            "reviewer_verdict": "manual_review",
            "agrees_with_initial": False,
            "escalation_recommended": True,
            "confirmed_points": [],
            "disagreement_points": [
                {
                    "field": "approval",
                    "initial_assessment": "初审通过",
                    "reviewer_assessment": "复核认为审批不完整",
                    "evidence_basis": "缺少审批记录",
                }
            ],
            "additional_policy_refs": ["expense.general.001"],
            "additional_evidence_chain": [],
            "final_recommendation": "manual_review",
            "explanation": "缺少审批记录。",
            "reviewed_by": "expense-reviewer",
            "timestamp": "2026-04-21T12:00:00+08:00",
        },
        created_at="2026-04-21T04:00:00+00:00",
    )

    result = RUNNER.invoke(cli_module.app, ["review-delta-detail", "req-cli-review-1"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["record"]["request_id"] == "req-cli-review-1"
    assert payload["payload"]["claim_id"] == "EXP-CLI-001"
