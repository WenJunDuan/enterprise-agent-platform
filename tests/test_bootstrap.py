from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

pytest.importorskip("claude_agent_sdk")

from server import api as api_module
from server import cli as cli_module
from server.api import _load_tenant_keys, verify_tenant
from server.core import (
    AgentRunMeta,
    DEFAULT_OUTPUT_SCHEMA_NAME,
    INIT_RULES_REPORT_SCHEMA_NAME,
    JSONContractError,
    PROJECT_ROOT,
    build_options,
    build_output_format,
    load_output_schema,
    resolve_output_schema_path,
)
from server.platform.diagnostics import collect_runtime_diagnostics
from server.platform.config import (
    configure_claude_runtime_env,
    get_app_settings,
    resolve_second_review_model,
)
from server.stores.request_store import JSONLRequestAuditStore, RequestAuditRecord
from server.stores.result_store import JSONLResultStore, ResultRecord
from server.stores.session_store import JSONLSessionStore, SessionRecord


def _clear_settings_cache() -> None:
    get_app_settings.cache_clear()


def test_build_options_uses_project_settings() -> None:
    options = build_options()
    assert options.cwd == str(PROJECT_ROOT)
    assert options.setting_sources == ["project"]
    assert "Task" in options.allowed_tools


def test_load_tenant_keys_reads_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    assert _load_tenant_keys() == {"demo": "sk-demo"}


def test_configure_claude_runtime_env_maps_model_variables() -> None:
    env = {
        "MODEL_BASE_URL": "https://api.infiniteai.cc",
        "MODEL_API_KEY": "sk-demo",
        "MODEL_NAME": "gpt-5.4",
    }
    mapped = configure_claude_runtime_env(env)
    assert env["ANTHROPIC_BASE_URL"] == "https://api.infiniteai.cc"
    assert env["ANTHROPIC_API_KEY"] == "sk-demo"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "sk-demo"
    assert env["ANTHROPIC_MODEL"] == "sonnet"
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "gpt-5.4"
    assert env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "gpt-5.4"
    assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "gpt-5.4"
    assert mapped["anthropic_base_url"] == "https://api.infiniteai.cc"
    assert mapped["anthropic_auth_token"] == "sk-demo"
    assert mapped["anthropic_default_sonnet_model"] == "gpt-5.4"


def test_configure_claude_runtime_env_prefers_model_auth_token() -> None:
    env = {
        "MODEL_BASE_URL": "https://api.infiniteai.cc",
        "MODEL_API_KEY": "sk-demo",
        "MODEL_AUTH_TOKEN": "token-demo",
        "MODEL_NAME": "gpt-5.4",
    }
    mapped = configure_claude_runtime_env(env)
    assert env["ANTHROPIC_API_KEY"] == "sk-demo"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "token-demo"
    assert mapped["anthropic_auth_token"] == "token-demo"


def test_configure_claude_runtime_env_maps_custom_headers_json() -> None:
    env = {
        "MODEL_CUSTOM_HEADERS": '{"HTTP-Referer":"https://example.com","X-Title":"enterprise-agent-platform"}',
    }
    mapped = configure_claude_runtime_env(env)
    assert env["ANTHROPIC_CUSTOM_HEADERS"] == (
        "HTTP-Referer: https://example.com\nX-Title: enterprise-agent-platform"
    )
    assert mapped["anthropic_custom_headers_configured"] == "1"


def test_resolve_second_review_model_prefers_explicit_override() -> None:
    env = {
        "SECOND_REVIEW_MODEL": "gpt-5.4-mini",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "gpt-5.4",
    }
    assert resolve_second_review_model(env) == "gpt-5.4-mini"


def test_resolve_second_review_model_falls_back_to_external_gateway_model() -> None:
    env = {
        "MODEL_NAME": "gpt-5.4",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "gpt-5.4",
    }
    assert resolve_second_review_model(env) == "gpt-5.4"


def test_verify_tenant_accepts_bearer_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    api_module.TENANT_KEYS = _load_tenant_keys()
    assert verify_tenant("Bearer sk-demo") == "demo"


def test_load_output_schema_reads_default_contract() -> None:
    schema = load_output_schema()
    assert schema["type"] == "object"
    assert "claim_id" in schema["properties"]


def test_load_output_schema_reads_init_rules_contract() -> None:
    schema = load_output_schema(INIT_RULES_REPORT_SCHEMA_NAME)
    assert schema["title"] == "init_rules_report"
    assert schema["properties"]["status"]["enum"] == ["initialized", "manual_review"]


def test_build_output_format_uses_json_schema_wrapper() -> None:
    output_format = build_output_format(DEFAULT_OUTPUT_SCHEMA_NAME)
    assert output_format["type"] == "json_schema"
    assert output_format["schema"]["title"] == "audit_result"


def test_resolve_output_schema_rejects_path_escape() -> None:
    with pytest.raises(JSONContractError):
        resolve_output_schema_path("../secrets.json")


def test_nested_skill_layout_exists() -> None:
    expected_files = [
        PROJECT_ROOT / ".claude/skills/expense-audit/SKILL.md",
        PROJECT_ROOT / ".claude/skills/expense-audit/amount-validate/SKILL.md",
        PROJECT_ROOT / ".claude/skills/common/result-format/SKILL.md",
        PROJECT_ROOT / ".claude/skills/system/rule-init/SKILL.md",
        PROJECT_ROOT / ".claude/contracts/common/audit-result.schema.json",
        PROJECT_ROOT / ".claude/contracts/system/init-rules-report.schema.json",
    ]
    for path in expected_files:
        assert path.exists(), f"Missing skill file: {path}"


def test_init_rules_assets_reflect_current_layout() -> None:
    command_file = PROJECT_ROOT / ".claude/commands/init-rules.md"
    command_text = command_file.read_text(encoding="utf-8")
    assert "knowledge/external/" in command_text
    assert not (PROJECT_ROOT / ".claude/commands/batch-audit.md").exists()


def test_claude_settings_are_hardened_for_project_usage() -> None:
    settings_path = PROJECT_ROOT / ".claude/settings.json"
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["$schema"] == "https://json.schemastore.org/claude-code-settings.json"
    assert payload["cleanupPeriodDays"] == 180
    assert payload["includeGitInstructions"] is False
    assert payload["permissions"]["allow"] == ["Read", "Glob", "Grep", "Task", "Skill", "Write"]
    assert "Bash" in payload["permissions"]["deny"]
    assert "Read(./.env)" in payload["permissions"]["deny"]
    assert "Read(./.env.*)" in payload["permissions"]["deny"]
    assert "Read(./token.json)" in payload["permissions"]["deny"]
    assert "PreToolUse" in payload["hooks"]
    assert "PostToolUse" in payload["hooks"]


def test_cli_help_lists_init_rules_without_batch() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_module.app, ["--help"])
    assert result.exit_code == 0
    assert "init-rules" in result.stdout
    assert "batch" not in result.stdout


def test_init_rules_cli_returns_structured_json(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_agent_json(prompt: str, **kwargs: Any) -> tuple[dict[str, Any], AgentRunMeta]:
        captured["prompt"] = prompt
        captured["schema_name"] = kwargs.get("schema_name")
        return {
            "status": "initialized",
            "domain": "hr",
            "source_path": "knowledge/external/数睿员工手册.pdf",
            "written_files": ["knowledge/hr/attendance.rules.json"],
            "categories": ["attendance"],
            "extracted_rule_count": 2,
            "manual_review_items": [],
            "notes": ["initial import complete"],
        }, AgentRunMeta(
            request_id="req-init-1",
            conversation_id="conv-init-1",
            claude_session_id="sess-init-1",
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=INIT_RULES_REPORT_SCHEMA_NAME,
            log_file="logs/sessions/events/2026/03/24/000000_req-init-1_sess-init-1.jsonl",
            result_file="results/by-request/2026/03/24/req-init-1.json",
            result_subtype="success",
            cost_usd=0.1,
            finished_at="2026-03-24T00:00:00+00:00",
        )

    monkeypatch.setattr(cli_module, "run_agent_json", fake_run_agent_json)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.app,
        ["init-rules", "knowledge/external/数睿员工手册.pdf", "hr"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["request_id"] == "req-init-1"
    assert payload["schema_name"] == INIT_RULES_REPORT_SCHEMA_NAME
    assert payload["response"]["status"] == "initialized"
    assert payload["response"]["written_files"] == ["knowledge/hr/attendance.rules.json"]
    assert captured["prompt"] == "/init-rules knowledge/external/数睿员工手册.pdf hr"
    assert captured["schema_name"] == INIT_RULES_REPORT_SCHEMA_NAME


def test_chat_endpoint_returns_structured_json(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_agent_json(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], AgentRunMeta]:
        captured["schema_name"] = kwargs.get("schema_name")
        captured["tenant"] = kwargs.get("tenant")
        return {
            "verdict": "manual_review",
            "policy_refs": ["expense.travel.001"],
        }, AgentRunMeta(
            request_id="req-1",
            conversation_id="conv-1",
            claude_session_id="sess-1",
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
            log_file="logs/sessions/events/2026/03/23/000000_req-1_sess-1.jsonl",
            result_file="results/by-request/2026/03/23/req-1.json",
            result_subtype="success",
            cost_usd=0.2,
            finished_at="2026-03-23T00:00:00+00:00",
        )

    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    api_module.TENANT_KEYS = _load_tenant_keys()
    monkeypatch.setattr(api_module, "run_agent_json", fake_run_agent_json)

    client = TestClient(api_module.app)
    response = client.post(
        "/chat",
        headers={"Authorization": "Bearer sk-demo"},
        json={"message": "审核 CLAIM-001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "req-1"
    assert payload["tenant"] == "demo"
    assert payload["conversation_id"] == "conv-1"
    assert payload["claude_session_id"] == "sess-1"
    assert payload["result_file"] == "results/by-request/2026/03/23/req-1.json"
    assert payload["response"]["verdict"] == "manual_review"
    assert captured["schema_name"] == DEFAULT_OUTPUT_SCHEMA_NAME
    assert captured["tenant"] == "demo"


def test_chat_request_rejects_conflicting_session_controls() -> None:
    _clear_settings_cache()
    with pytest.raises(ValueError):
        api_module.ChatRequest(
            message="审核",
            resume_session_id="sess-1",
            fork_from_session_id="sess-2",
        )


def test_chat_request_rejects_continue_recent_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALLOW_UNSCOPED_CONTINUE_RECENT", raising=False)
    _clear_settings_cache()
    with pytest.raises(ValueError):
        api_module.ChatRequest(message="审核", continue_recent=True)


def test_health_endpoint_reports_runtime_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    _clear_settings_cache()
    api_module.TENANT_KEYS = _load_tenant_keys()
    client = TestClient(api_module.app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"]["default_output_schema"]["schema_name"] == DEFAULT_OUTPUT_SCHEMA_NAME
    assert payload["checks"]["session_store"]["backend"] == "jsonl-sharded"
    assert payload["checks"]["result_store"]["backend"] == "jsonl-sharded+json-files"


def test_collect_runtime_diagnostics_contains_advisories() -> None:
    payload = collect_runtime_diagnostics()
    assert "checks" in payload
    assert "advisories" in payload
    assert "app_server" in payload["checks"]


def test_jsonl_session_store_builds_conversation_summaries(tmp_path: Path) -> None:
    store = JSONLSessionStore(tmp_path / "index")
    store.append_record(
        SessionRecord(
            request_id="req-1",
            conversation_id="conv-1",
            claude_session_id="sess-1",
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
            request_mode="structured",
            prompt_preview="first",
            log_file="logs/sessions/events/one.jsonl",
            result_file="results/by-request/req-1.json",
            status="success",
            result_subtype="success",
            cost_usd=0.3,
            started_at="2026-03-23T00:00:00+00:00",
            finished_at="2026-03-23T00:00:01+00:00",
            tenant="tenant-a",
        )
    )
    store.append_record(
        SessionRecord(
            request_id="req-2",
            conversation_id="conv-1",
            claude_session_id="sess-1",
            resume_session_id="sess-1",
            fork_from_session_id=None,
            schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
            request_mode="structured",
            prompt_preview="second",
            log_file="logs/sessions/events/two.jsonl",
            result_file="results/by-request/req-2.json",
            status="success",
            result_subtype="success",
            cost_usd=0.2,
            started_at="2026-03-23T00:01:00+00:00",
            finished_at="2026-03-23T00:01:01+00:00",
            tenant="tenant-a",
        )
    )

    summaries = store.list_conversation_summaries(tenant="tenant-a")
    assert len(summaries) == 1
    assert summaries[0]["conversation_id"] == "conv-1"
    assert summaries[0]["request_count"] == 2
    assert summaries[0]["total_cost_usd"] == 0.5
    assert summaries[0]["latest_request_id"] == "req-2"
    assert summaries[0]["latest_result_file"] == "results/by-request/req-2.json"


def test_jsonl_request_store_round_trip(tmp_path: Path) -> None:
    store = JSONLRequestAuditStore(tmp_path / "index")
    store.append_record(
        RequestAuditRecord(
            request_id="req-1",
            route="/chat",
            method="POST",
            tenant="tenant-a",
            conversation_id="conv-1",
            claude_session_id="sess-1",
            schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
            request_payload={"message": "审核"},
            session_log_file="logs/sessions/events/one.jsonl",
            result_file="results/by-request/req-1.json",
            status_code=200,
            status="success",
            duration_ms=10,
            created_at="2026-03-23T00:00:00+00:00",
        )
    )

    record = store.get_record_by_request_id("req-1", tenant="tenant-a")
    assert record is not None
    assert record["request_payload"]["message"] == "审核"
    listed = store.list_records(tenant="tenant-a")
    assert len(listed) == 1
    assert listed[0]["result_file"] == "results/by-request/req-1.json"


def test_jsonl_result_store_round_trip(tmp_path: Path) -> None:
    store = JSONLResultStore(
        tmp_path / "index",
        tmp_path / "logs" / "results" / "by-request",
    )
    store.archive_result(
        ResultRecord(
            request_id="req-1",
            tenant="tenant-a",
            conversation_id="conv-1",
            claude_session_id="sess-1",
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
            request_mode="structured",
            result_subtype="success",
            claim_id="CLAIM-001",
            verdict="manual_review",
            cost_usd=0.2,
            prompt_preview="审核 CLAIM-001",
            created_at="2026-03-23T00:00:00+00:00",
            result_file="results/by-request/2026/03/23/req-1.json",
        ),
        {
            "request_id": "req-1",
            "response": {
                "claim_id": "CLAIM-001",
                "verdict": "manual_review",
            },
        },
    )

    record = store.get_record_by_request_id("req-1", tenant="tenant-a")
    assert record is not None
    assert record["claim_id"] == "CLAIM-001"
    payload = store.get_payload_by_request_id("req-1", tenant="tenant-a")
    assert payload is not None
    assert payload["response"]["verdict"] == "manual_review"
    listed = store.list_records(tenant="tenant-a", claim_id="CLAIM-001")
    assert len(listed) == 1
