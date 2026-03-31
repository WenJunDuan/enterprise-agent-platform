from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

pytest.importorskip("claude_agent_sdk")

from server import api as api_module
from server import app_server as app_server_module
from server import cli as cli_module
from server.api import _load_tenant_keys, verify_tenant
from server.command_adapter import build_audit_prompt, build_command_prompt, run_command_json
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
    validate_structured_output_semantics,
)
from server.platform.config import (
    configure_claude_runtime_env,
    get_claude_runtime_report,
    get_app_settings,
    resolve_second_review_model,
    validate_claude_runtime,
)
from server.platform.diagnostics import collect_runtime_diagnostics


def _clear_settings_cache() -> None:
    get_app_settings.cache_clear()


def _run_check_before_write_hook(
    payload: dict[str, Any], file_path: str
) -> subprocess.CompletedProcess[str]:
    hook_input = {
        "tool_input": {
            "file_path": file_path,
            "content": json.dumps(payload, ensure_ascii=False),
        }
    }
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / ".claude/hooks/check-before-write.py")],
        input=json.dumps(hook_input, ensure_ascii=False),
        capture_output=True,
        text=True,
        check=False,
    )


def test_build_command_prompt_renders_slash_command() -> None:
    assert (
        build_command_prompt("init-rules", "knowledge/external/数睿员工手册.pdf", "expense")
        == "/init-rules knowledge/external/数睿员工手册.pdf expense"
    )


def test_build_command_prompt_allows_directory_path() -> None:
    assert build_command_prompt("audit", "data/case1") == "/audit data/case1"


def test_build_audit_prompt_mentions_directory_and_chinese_audit_fields() -> None:
    prompt = build_audit_prompt("data/case1")
    assert "data/case1" in prompt
    assert "如果输入是目录，先枚举目录下文件" in prompt
    assert "`.claude/contracts/common/audit-result.schema.json`" in prompt
    assert "`result`、`conclusion`、`explanation`" in prompt
    assert "待人工复核" in prompt
    assert "只返回一个 JSON 对象" in prompt
    assert "不要输出 Markdown" in prompt


def test_run_command_json_uses_direct_audit_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_agent_json(prompt: str, **kwargs: Any) -> tuple[dict[str, Any], str]:
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return {"ok": True}, "meta"

    monkeypatch.setattr("server.command_adapter.run_agent_json", fake_run_agent_json)

    payload, meta = asyncio.run(run_command_json("audit", "data/case1", schema_name=DEFAULT_OUTPUT_SCHEMA_NAME))

    assert payload == {"ok": True}
    assert meta == "meta"
    assert captured["prompt"] != "/audit data/case1"
    assert "data/case1" in captured["prompt"]
    assert "如果输入是目录" in captured["prompt"]
    assert captured["kwargs"]["schema_name"] == DEFAULT_OUTPUT_SCHEMA_NAME


def test_run_command_json_keeps_slash_prompt_for_non_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_agent_json(prompt: str, **kwargs: Any) -> tuple[dict[str, Any], str]:
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return {"ok": True}, "meta"

    monkeypatch.setattr("server.command_adapter.run_agent_json", fake_run_agent_json)

    payload, meta = asyncio.run(
        run_command_json(
            "init-rules",
            "knowledge/external/数睿员工手册.pdf",
            "expense",
            schema_name=INIT_RULES_REPORT_SCHEMA_NAME,
        )
    )

    assert payload == {"ok": True}
    assert meta == "meta"
    assert (
        captured["prompt"]
        == "/init-rules knowledge/external/数睿员工手册.pdf expense"
    )
    assert captured["kwargs"]["schema_name"] == INIT_RULES_REPORT_SCHEMA_NAME


def test_build_options_uses_project_settings() -> None:
    options = build_options()
    assert options.cwd == str(PROJECT_ROOT)
    assert options.setting_sources == ["project"]
    assert "Task" in options.allowed_tools


def test_build_options_uses_runtime_resolved_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_BASE_URL", "https://api.infiniteai.cc")
    monkeypatch.setenv("MODEL_API_KEY", "sk-demo")
    monkeypatch.setenv("MODEL_NAME", "gpt-5.4")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_DEFAULT_SONNET_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_DEFAULT_OPUS_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_DEFAULT_HAIKU_MODEL", raising=False)
    configure_claude_runtime_env()
    options = build_options()
    assert options.model == "sonnet"


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


def test_validate_claude_runtime_reports_missing_required_values() -> None:
    errors = validate_claude_runtime({})
    assert "MODEL_BASE_URL or ANTHROPIC_BASE_URL is required" in errors
    assert (
        "MODEL_API_KEY / MODEL_AUTH_TOKEN / ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN is required"
        in errors
    )
    assert "MODEL_NAME or ANTHROPIC_MODEL is required" in errors


def test_get_claude_runtime_report_resolves_gateway_config() -> None:
    env = {
        "MODEL_BASE_URL": "https://api.infiniteai.cc",
        "MODEL_API_KEY": "sk-demo",
        "MODEL_NAME": "gpt-5.4",
    }
    report = get_claude_runtime_report(env)
    assert report["status"] == "ok"
    assert report["runtime"]["anthropic_base_url"] == "https://api.infiniteai.cc"
    assert report["runtime"]["anthropic_model"] == "sonnet"
    assert report["runtime"]["anthropic_default_sonnet_model"] == "gpt-5.4"


def test_resolve_second_review_model_prefers_explicit_override() -> None:
    env = {
        "SECOND_REVIEW_MODEL": "gpt-5.4-mini",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "gpt-5.4",
    }
    assert resolve_second_review_model(env) == "gpt-5.4-mini"


def test_verify_tenant_accepts_bearer_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    api_module.TENANT_KEYS = _load_tenant_keys()
    assert verify_tenant("Bearer sk-demo") == "demo"


def test_load_output_schema_reads_init_rules_contract() -> None:
    schema = load_output_schema(INIT_RULES_REPORT_SCHEMA_NAME)
    assert schema["title"] == "init_rules_report"


def test_build_output_format_uses_json_schema_wrapper() -> None:
    output_format = build_output_format(DEFAULT_OUTPUT_SCHEMA_NAME)
    assert output_format["type"] == "json_schema"
    assert output_format["schema"]["title"] == "audit_result"


def test_resolve_output_schema_rejects_path_escape() -> None:
    with pytest.raises(JSONContractError):
        resolve_output_schema_path("../secrets.json")


def test_validate_init_rules_semantics_rejects_empty_initialized_payload() -> None:
    payload = {
        "status": "initialized",
        "domain": "expense",
        "source_path": "",
        "written_files": [],
        "categories": [],
        "extracted_rule_count": 0,
        "manual_review_items": [],
        "notes": [],
    }
    with pytest.raises(JSONContractError):
        validate_structured_output_semantics(INIT_RULES_REPORT_SCHEMA_NAME, payload)


def test_validate_init_rules_semantics_accepts_written_initialized_payload() -> None:
    payload = {
        "status": "initialized",
        "domain": "expense",
        "source_path": "knowledge/external/数睿员工手册.pdf",
        "written_files": ["knowledge/expense/travel.rules.json"],
        "categories": ["travel"],
        "extracted_rule_count": 8,
        "manual_review_items": [],
        "notes": [],
    }
    validate_structured_output_semantics(INIT_RULES_REPORT_SCHEMA_NAME, payload)


def test_validate_audit_semantics_accepts_manual_review_mapping() -> None:
    payload = {
        "verdict": "manual_review",
        "result": False,
        "conclusion": "待人工复核",
        "explanation": "缺少关键附件，需人工复核。",
    }
    validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_check_before_write_hook_accepts_top_level_manual_review_result() -> None:
    payload = {
        "claim_id": "CLAIM-001",
        "verdict": "manual_review",
        "result": False,
        "conclusion": "待人工复核",
        "explanation": "根据现有材料无法完成自动审核，缺少关键附件。",
        "reasons": ["缺少关键附件"],
        "policy_refs": ["expense.travel.001"],
        "risk_score": 70,
        "extracted_data": {"claim_amount": 1200},
        "evidence_chain": ["OCR extracted amount 1200"],
        "reviewed_by": "expense-auditor",
        "timestamp": "2026-03-31T00:00:00+00:00",
    }

    result = _run_check_before_write_hook(payload, "logs/results/by-request/req-top-level.json")

    assert result.returncode == 0
    assert result.stdout == ""


def test_check_before_write_hook_accepts_envelope_response_manual_review_result() -> None:
    payload = {
        "request_id": "req-envelope-1",
        "tenant": "demo",
        "conversation_id": "conv-envelope-1",
        "schema_name": DEFAULT_OUTPUT_SCHEMA_NAME,
        "response": {
            "claim_id": "CLAIM-001",
            "verdict": "manual_review",
            "result": False,
            "conclusion": "待人工复核",
            "explanation": "根据现有材料无法完成自动审核，缺少关键附件。",
            "reasons": ["缺少关键附件"],
            "policy_refs": ["expense.travel.001"],
            "risk_score": 70,
            "extracted_data": {"claim_amount": 1200},
            "evidence_chain": ["OCR extracted amount 1200"],
            "reviewed_by": "expense-auditor",
            "timestamp": "2026-03-31T00:00:00+00:00",
        },
    }

    result = _run_check_before_write_hook(payload, "logs/results/by-request/req-envelope.json")

    assert result.returncode == 0
    assert result.stdout == ""


def test_check_before_write_hook_rejects_envelope_response_missing_timestamp() -> None:
    payload = {
        "request_id": "req-envelope-2",
        "tenant": "demo",
        "conversation_id": "conv-envelope-2",
        "schema_name": DEFAULT_OUTPUT_SCHEMA_NAME,
        "response": {
            "claim_id": "CLAIM-001",
            "verdict": "manual_review",
            "result": False,
            "conclusion": "待人工复核",
            "explanation": "根据现有材料无法完成自动审核，缺少关键附件。",
            "reasons": ["缺少关键附件"],
            "policy_refs": ["expense.travel.001"],
            "risk_score": 70,
            "extracted_data": {"claim_amount": 1200},
            "evidence_chain": ["OCR extracted amount 1200"],
            "reviewed_by": "expense-auditor",
        },
    }

    result = _run_check_before_write_hook(
        payload,
        "logs/results/by-request/req-envelope-missing-timestamp.json",
    )

    assert result.returncode == 2
    assert "timestamp" in result.stdout


def test_validate_audit_semantics_rejects_manual_review_noncompliant_conclusion() -> None:
    payload = {
        "verdict": "manual_review",
        "result": False,
        "conclusion": "不合规",
        "explanation": "缺少关键附件，需人工复核。",
    }
    with pytest.raises(JSONContractError):
        validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_validate_audit_semantics_accepts_approved_mapping() -> None:
    payload = {
        "verdict": "approved",
        "result": True,
        "conclusion": "合规",
        "explanation": "已满足自动审核条件。",
    }
    validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_validate_audit_semantics_rejects_blank_explanation() -> None:
    payload = {
        "verdict": "rejected",
        "result": False,
        "conclusion": "不合规",
        "explanation": "   ",
    }
    with pytest.raises(JSONContractError):
        validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_audit_semantics_schema_requires_result_fields() -> None:
    schema = load_output_schema(DEFAULT_OUTPUT_SCHEMA_NAME)
    assert schema["properties"]["result"]["type"] == "boolean"
    assert schema["properties"]["conclusion"]["enum"] == ["合规", "不合规", "待人工复核"]
    assert schema["properties"]["explanation"]["minLength"] == 1
    assert "result" in schema["required"]
    assert "conclusion" in schema["required"]
    assert "explanation" in schema["required"]


def test_init_rules_assets_reflect_current_layout() -> None:
    command_text = (PROJECT_ROOT / ".claude/commands/init-rules.md").read_text(encoding="utf-8")
    skill_text = (PROJECT_ROOT / ".claude/skills/system/rule-init/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "knowledge/external/" in command_text
    assert "written_files" in command_text
    assert "manual_review" in command_text
    assert "general.rules.json" in command_text
    assert "transport.rules.json" in command_text
    assert "logs/service/init-rules/" in command_text
    assert "source.path" in skill_text
    assert "general.rules.json" in skill_text
    assert "transport.rules.json" in skill_text


def test_claude_settings_are_hardened_for_project_usage() -> None:
    settings_path = PROJECT_ROOT / ".claude/settings.json"
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["permissions"]["allow"] == ["Read", "Glob", "Grep", "Task", "Skill", "Write"]
    assert "Bash" in payload["permissions"]["deny"]


def test_cli_help_lists_init_rules_without_batch() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_module.app, ["--help"])
    assert result.exit_code == 0
    assert "init-rules" in result.stdout
    assert "batch" not in result.stdout
    assert "chat" not in result.stdout


def test_cli_runtime_command_prints_runtime_report(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli_module,
        "get_claude_runtime_report",
        lambda: {"status": "ok", "runtime": {"anthropic_model": "sonnet"}, "errors": []},
    )
    runner = CliRunner()
    result = runner.invoke(cli_module.app, ["runtime"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["runtime"]["anthropic_model"] == "sonnet"


def test_cli_ask_exits_when_runtime_is_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _unexpected_call(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("run_agent_full should not be called when runtime is invalid")

    monkeypatch.delenv("MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.setattr(cli_module, "run_agent_full", _unexpected_call)
    runner = CliRunner()
    result = runner.invoke(cli_module.app, ["ask", "hello"])
    assert result.exit_code == 1
    assert "MODEL_BASE_URL or ANTHROPIC_BASE_URL is required" in result.stdout


def test_init_rules_cli_returns_structured_json(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_command_json(
        command_name: str, *args: Any, **kwargs: Any
    ) -> tuple[dict[str, Any], AgentRunMeta]:
        captured["command_name"] = command_name
        captured["args"] = args
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
            log_file="logs/sessions/events/init.jsonl",
            result_file="results/by-request/req-init-1.json",
            result_subtype="success",
            cost_usd=0.1,
            finished_at="2026-03-24T00:00:00+00:00",
        )

    monkeypatch.setattr(
        cli_module,
        "prepare_text_proxy",
        lambda source, proxy_root: (source, "logs/service/init-rules/数睿员工手册.txt"),
    )
    monkeypatch.setattr(cli_module, "run_command_json", fake_run_command_json)
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
    assert captured["command_name"] == "init-rules"
    assert captured["args"] == ("knowledge/external/数睿员工手册.pdf", "hr")


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
            log_file="logs/sessions/events/chat.jsonl",
            result_file="results/by-request/req-1.json",
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
    assert payload["response"]["verdict"] == "manual_review"
    assert captured["schema_name"] == DEFAULT_OUTPUT_SCHEMA_NAME
    assert captured["tenant"] == "demo"


def test_audit_endpoint_returns_structured_json(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_command_json(
        command_name: str, *args: Any, **kwargs: Any
    ) -> tuple[dict[str, Any], AgentRunMeta]:
        captured["command_name"] = command_name
        captured["args"] = args
        captured["schema_name"] = kwargs.get("schema_name")
        captured["tenant"] = kwargs.get("tenant")
        return {
            "claim_id": "CLAIM-001",
            "verdict": "manual_review",
            "result": False,
            "conclusion": "待人工复核",
            "explanation": "根据现有材料无法完成自动审核，缺少关键附件。",
            "reasons": ["缺少附件"],
            "policy_refs": ["expense.travel.001"],
            "risk_score": 70,
            "extracted_data": {},
            "evidence_chain": [],
            "reviewed_by": "expense-auditor",
            "timestamp": "2026-03-31T00:00:00+00:00",
        }, AgentRunMeta(
            request_id="req-audit-1",
            conversation_id="conv-audit-1",
            claude_session_id="sess-audit-1",
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
            log_file="logs/sessions/events/audit.jsonl",
            result_file="results/by-request/req-audit-1.json",
            result_subtype="success",
            cost_usd=0.3,
            finished_at="2026-03-31T00:00:00+00:00",
        )

    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    api_module.TENANT_KEYS = _load_tenant_keys()
    monkeypatch.setattr(api_module, "run_command_json", fake_run_command_json)
    client = TestClient(api_module.app)
    response = client.post(
        "/audit",
        headers={"Authorization": "Bearer sk-demo"},
        json={"path": "tests/fixtures/claim.json"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "req-audit-1"
    assert payload["response"]["claim_id"] == "CLAIM-001"
    assert payload["response"]["result"] is False
    assert payload["response"]["conclusion"] == "待人工复核"
    assert payload["response"]["explanation"] == "根据现有材料无法完成自动审核，缺少关键附件。"
    assert captured["command_name"] == "audit"
    assert captured["args"] == ("tests/fixtures/claim.json",)
    assert captured["schema_name"] == DEFAULT_OUTPUT_SCHEMA_NAME
    assert captured["tenant"] == "demo"


def test_audit_endpoint_accepts_directory_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_command_json(
        command_name: str, *args: Any, **kwargs: Any
    ) -> tuple[dict[str, Any], AgentRunMeta]:
        captured["command_name"] = command_name
        captured["args"] = args
        return {
            "claim_id": "CASE-001",
            "verdict": "manual_review",
            "result": False,
            "conclusion": "待人工复核",
            "explanation": "根据《费用报销管理制度》相关条款，现有目录材料不足以自动判断，缺少关键行程凭证。",
            "reasons": ["缺少关键行程凭证"],
            "policy_refs": ["expense.travel.001"],
            "risk_score": 70,
            "extracted_data": {},
            "evidence_chain": [],
            "reviewed_by": "expense-auditor",
            "timestamp": "2026-03-31T00:00:00+00:00",
        }, AgentRunMeta(
            request_id="req-audit-dir-1",
            conversation_id="conv-audit-dir-1",
            claude_session_id="sess-audit-dir-1",
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
            log_file="logs/sessions/events/audit-dir.jsonl",
            result_file="results/by-request/req-audit-dir-1.json",
            result_subtype="success",
            cost_usd=0.3,
            finished_at="2026-03-31T00:00:00+00:00",
        )

    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    api_module.TENANT_KEYS = _load_tenant_keys()
    monkeypatch.setattr(api_module, "run_command_json", fake_run_command_json)
    client = TestClient(api_module.app)
    response = client.post(
        "/audit",
        headers={"Authorization": "Bearer sk-demo"},
        json={"path": "data/case1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "req-audit-dir-1"
    assert payload["response"]["claim_id"] == "CASE-001"
    assert payload["response"]["result"] is False
    assert payload["response"]["conclusion"] == "待人工复核"
    assert captured["command_name"] == "audit"
    assert captured["args"] == ("data/case1",)


def test_init_rules_endpoint_returns_structured_json(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_command_json(
        command_name: str, *args: Any, **kwargs: Any
    ) -> tuple[dict[str, Any], AgentRunMeta]:
        captured["command_name"] = command_name
        captured["args"] = args
        captured["schema_name"] = kwargs.get("schema_name")
        captured["tenant"] = kwargs.get("tenant")
        return {
            "status": "initialized",
            "domain": "expense",
            "source_path": "knowledge/external/数睿员工手册.pdf",
            "written_files": ["knowledge/expense/general.rules.json"],
            "categories": ["general"],
            "extracted_rule_count": 8,
            "manual_review_items": [],
            "notes": [],
        }, AgentRunMeta(
            request_id="req-init-http-1",
            conversation_id="conv-init-http-1",
            claude_session_id="sess-init-http-1",
            resume_session_id=None,
            fork_from_session_id=None,
            schema_name=INIT_RULES_REPORT_SCHEMA_NAME,
            log_file="logs/sessions/events/init-http.jsonl",
            result_file="results/by-request/req-init-http-1.json",
            result_subtype="success",
            cost_usd=0.2,
            finished_at="2026-03-31T00:00:00+00:00",
        )

    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    api_module.TENANT_KEYS = _load_tenant_keys()
    monkeypatch.setattr(
        api_module,
        "prepare_text_proxy",
        lambda source, proxy_root: (source, "logs/service/init-rules/数睿员工手册.txt"),
    )
    monkeypatch.setattr(api_module, "run_command_json", fake_run_command_json)
    client = TestClient(api_module.app)
    response = client.post(
        "/init-rules",
        headers={"Authorization": "Bearer sk-demo"},
        json={"source_path": "knowledge/external/数睿员工手册.pdf", "domain": "expense"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "req-init-http-1"
    assert payload["response"]["domain"] == "expense"
    assert captured["command_name"] == "init-rules"
    assert captured["args"] == ("knowledge/external/数睿员工手册.pdf", "expense")
    assert captured["schema_name"] == INIT_RULES_REPORT_SCHEMA_NAME
    assert captured["tenant"] == "demo"


def test_audit_endpoint_returns_json_contract_error_without_attribute_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_command_json(*args: Any, **kwargs: Any):
        raise JSONContractError("audit boom")

    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    api_module.TENANT_KEYS = _load_tenant_keys()
    monkeypatch.setattr(api_module, "run_command_json", fake_run_command_json)
    client = TestClient(api_module.app)
    response = client.post(
        "/audit",
        headers={"Authorization": "Bearer sk-demo"},
        json={"path": "tests/fixtures/claim.json"},
    )
    assert response.status_code == 502
    assert response.json()["detail"] == "audit boom"


def test_init_rules_endpoint_returns_bad_request_on_proxy_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    api_module.TENANT_KEYS = _load_tenant_keys()
    monkeypatch.setattr(
        api_module,
        "prepare_text_proxy",
        lambda source, proxy_root: (_ for _ in ()).throw(ValueError("proxy boom")),
    )
    client = TestClient(api_module.app)
    response = client.post(
        "/init-rules",
        headers={"Authorization": "Bearer sk-demo"},
        json={"source_path": "knowledge/external/数睿员工手册.pdf", "domain": "expense"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "proxy boom"


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


def test_collect_runtime_diagnostics_contains_advisories() -> None:
    payload = collect_runtime_diagnostics()
    assert "checks" in payload
    assert "advisories" in payload
    assert "app_server" in payload["checks"]


def test_build_service_urls_returns_expected_routes() -> None:
    urls = app_server_module._build_service_urls("127.0.0.1", 8000)
    assert urls["base_url"] == "http://127.0.0.1:8000"
    assert urls["health"] == "http://127.0.0.1:8000/health"
    assert urls["ready"] == "http://127.0.0.1:8000/ready"
    assert urls["audit"] == "http://127.0.0.1:8000/audit"
    assert urls["init_rules"] == "http://127.0.0.1:8000/init-rules"


def test_service_http_snapshot_reports_not_running() -> None:
    payload = app_server_module._service_http_snapshot(
        {"record": {"host": "127.0.0.1", "port": 8000}, "running": False}
    )
    assert payload["running"] is False
    assert payload["health"]["ok"] is False
    assert payload["ready"]["ok"] is False


def test_audit_task_store_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from server.stores import audit_task_store as audit_task_store_module

    monkeypatch.setattr(audit_task_store_module, "AUDIT_TASK_FILE", tmp_path / "audit-tasks.json")

    audit_task_store_module.upsert_audit_task(
        {
            "request_id": "req-1",
            "status": "accepted",
            "mode": "directory",
            "case_path": "data/case1",
            "claim_id": None,
            "result_file": None,
            "error_detail": None,
            "updated_at": "2026-03-31T00:00:00+00:00",
        }
    )

    record = audit_task_store_module.get_audit_task("req-1")
    assert record is not None
    assert record["status"] == "accepted"
    assert record["case_path"] == "data/case1"


def test_audit_submit_directory_returns_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    api_module.TENANT_KEYS = _load_tenant_keys()

    async def fake_submit(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "request_id": "req-submit-1",
            "status": "accepted",
            "mode": "directory",
            "task_status_url": "/audit/tasks/req-submit-1",
            "result_url": "/results/req-submit-1",
        }

    monkeypatch.setattr(api_module, "_submit_audit_directory", fake_submit, raising=False)
    client = TestClient(api_module.app)
    response = client.post(
        "/audit/submit",
        headers={"Authorization": "Bearer sk-demo"},
        json={"mode": "directory", "directory_path": "data/case1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["mode"] == "directory"
    assert payload["request_id"] == "req-submit-1"


def test_audit_task_status_endpoint_returns_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    api_module.TENANT_KEYS = _load_tenant_keys()
    monkeypatch.setattr(
        api_module,
        "get_audit_task",
        lambda request_id: {
            "request_id": request_id,
            "status": "running",
            "mode": "directory",
            "case_path": "data/case1",
            "claim_id": None,
            "result_file": None,
            "error_detail": None,
            "updated_at": "2026-03-31T00:00:00+00:00",
        },
        raising=False,
    )
    client = TestClient(api_module.app)
    response = client.get("/audit/tasks/req-submit-1", headers={"Authorization": "Bearer sk-demo"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "req-submit-1"
    assert payload["status"] == "running"
    assert payload["mode"] == "directory"


def test_audit_submit_directory_marks_task_running_then_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    updates: list[dict[str, Any]] = []

    monkeypatch.setattr(api_module, "upsert_audit_task", lambda record: updates.append(record.copy()), raising=False)

    async def fake_run_directory_audit(*args: Any, **kwargs: Any):
        return (
            {
                "claim_id": "CASE-001",
                "verdict": "manual_review",
                "result": False,
                "conclusion": "待人工复核",
                "explanation": "根据《费用报销管理制度》相关条款，现有材料不足以自动判断。",
                "reasons": ["缺少关键材料"],
                "policy_refs": ["expense.travel.001"],
                "risk_score": 70,
                "extracted_data": {},
                "evidence_chain": [],
                "reviewed_by": "expense-auditor",
                "timestamp": "2026-03-31T00:00:00+00:00",
            },
            AgentRunMeta(
                request_id="req-submit-1",
                conversation_id="conv-1",
                claude_session_id="sess-1",
                resume_session_id=None,
                fork_from_session_id=None,
                schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
                log_file="logs/sessions/events/audit.jsonl",
                result_file="results/by-request/req-submit-1.json",
                result_subtype="success",
                cost_usd=0.2,
                finished_at="2026-03-31T00:00:00+00:00",
            ),
        )

    monkeypatch.setattr(api_module, "_run_directory_audit", fake_run_directory_audit, raising=False)

    asyncio.run(
        api_module._execute_directory_audit_task(
            request_id="req-submit-1",
            tenant="demo",
            directory_path="data/case1",
        )
    )

    assert updates[0]["status"] == "running"
    assert updates[-1]["status"] == "completed"
    assert updates[-1]["claim_id"] == "CASE-001"


def test_audit_submit_upload_writes_submission_case(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TENANT_KEYS", '{"demo":"sk-demo"}')
    api_module.TENANT_KEYS = _load_tenant_keys()
    monkeypatch.setattr(api_module, "SUBMISSION_ROOT_DIR", tmp_path, raising=False)
    monkeypatch.setattr(api_module, "_schedule_directory_audit_task", lambda **kwargs: None, raising=False)

    client = TestClient(api_module.app)
    response = client.post(
        "/audit/submit",
        headers={"Authorization": "Bearer sk-demo"},
        files=[("files", ("invoice.pdf", b"pdf-bytes", "application/pdf"))],
        data={
            "mode": "upload",
            "form_json": json.dumps({"case_id": "case1", "expense_type": "业务招待"}, ensure_ascii=False),
        },
    )

    assert response.status_code == 200
    request_id = response.json()["request_id"]
    case_dir = tmp_path / request_id
    assert (case_dir / "audit-request.json").is_file()
    assert (case_dir / "invoice.pdf").is_file()
