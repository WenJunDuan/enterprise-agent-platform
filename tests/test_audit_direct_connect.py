"""D10① T2: flag-gated dispatch + fallback semantics in server/audit/runner.py.

Mirrors the D8 wiring-assertion style (tests/test_tender_context_slim_wiring.py:51-77):
monkeypatch the dispatch targets with fail-if-called sentinels to prove which path
actually ran, rather than asserting on byte-identical output (design T2, critic F3).

Covers design.md T2 acceptance:
- flag off: direct entry never touched, CLI path unchanged (wiring assertion).
- flag on: direct entry used, CLI path never touched.
- fallback semantics (critic F2): transport-class failure falls back to CLI once;
  contract-class failure (retries exhausted) propagates without falling back.
"""

from __future__ import annotations

import asyncio

import pytest

from server.audit.direct import DirectContractError, DirectTransportError
from server.audit.output import EXPENSE_OUTPUT_SCHEMA_NAME
from server.common.agent_bridge import AgentRunMeta


def _fake_meta(request_id: str, *, mode: str) -> AgentRunMeta:
    return AgentRunMeta(
        request_id=request_id,
        conversation_id="conv-test",
        claude_session_id="sess-test" if mode == "cli" else None,
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="common/audit-result.schema.json",
        log_file="logs/test.log" if mode == "cli" else "",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def _fail_if_called(*_args, **_kwargs):
    raise AssertionError("this entry point must not be called on this path")


def test_flag_off_never_touches_direct_entry(monkeypatch, tmp_path):
    """flag off (unset) → dispatcher must go straight to the CLI path (D8-style wiring assertion)."""
    from server.audit import runner

    monkeypatch.delenv("AUDIT_DIRECT_CONNECT", raising=False)
    monkeypatch.setattr(runner, "run_direct_audit", _fail_if_called)

    seen = {}

    async def fake_run_agent_json(prompt, *, schema_name, request_id, tenant, **opts):
        seen["schema_name"] = schema_name
        seen.update(opts)
        return {"verdict": "manual_review"}, _fake_meta(request_id, mode="cli")

    monkeypatch.setattr(runner, "run_agent_json", fake_run_agent_json)
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runner, "EXPENSE_RULES_DIR", tmp_path / "no-rules")

    output, meta = asyncio.run(
        runner.run_inline_directory_audit(
            "no/such/dir", request_id="rid-off", tenant="acme"
        )
    )

    assert output == {"verdict": "manual_review"}
    assert meta.claude_session_id == "sess-test"
    assert seen["schema_name"] == EXPENSE_OUTPUT_SCHEMA_NAME
    assert seen["tools"] == []
    assert seen["allowed_tools"] == []


def test_flag_on_dispatches_direct_entry_and_skips_cli(monkeypatch, tmp_path):
    """flag on → direct path used; CLI path (run_agent_json) must never run."""
    from server.audit import runner

    monkeypatch.setenv("AUDIT_DIRECT_CONNECT", "1")
    monkeypatch.setattr(runner, "run_agent_json", _fail_if_called)
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runner, "EXPENSE_RULES_DIR", tmp_path / "no-rules")

    async def fake_run_direct_audit(
        prompt, *, request_id, tenant, schema_name, contract_max_retry, **_opts
    ):
        return {"verdict": "approved"}, _fake_meta(request_id, mode="direct")

    monkeypatch.setattr(runner, "run_direct_audit", fake_run_direct_audit)

    output, meta = asyncio.run(
        runner.run_inline_directory_audit(
            "no/such/dir", request_id="rid-on", tenant="acme"
        )
    )

    assert output == {"verdict": "approved"}
    assert meta.claude_session_id is None


def test_transport_failure_falls_back_to_cli_once(monkeypatch, tmp_path):
    """critic F2: transport-class failure (connection/auth/gateway/timeout) → single fallback."""
    from server.audit import runner

    monkeypatch.setenv("AUDIT_DIRECT_CONNECT", "1")
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runner, "EXPENSE_RULES_DIR", tmp_path / "no-rules")

    calls = {"direct": 0, "cli": 0}

    async def failing_direct(
        prompt, *, request_id, tenant, schema_name, contract_max_retry, **_opts
    ):
        calls["direct"] += 1
        raise DirectTransportError("connection refused")

    async def fake_run_agent_json(prompt, *, schema_name, request_id, tenant, **opts):
        calls["cli"] += 1
        return {"verdict": "manual_review"}, _fake_meta(request_id, mode="cli")

    monkeypatch.setattr(runner, "run_direct_audit", failing_direct)
    monkeypatch.setattr(runner, "run_agent_json", fake_run_agent_json)

    output, meta = asyncio.run(
        runner.run_inline_directory_audit(
            "no/such/dir", request_id="rid-fallback", tenant="acme"
        )
    )

    assert calls == {"direct": 1, "cli": 1}
    assert output == {"verdict": "manual_review"}
    assert meta.claude_session_id == "sess-test"


def test_contract_failure_does_not_fall_back(monkeypatch, tmp_path):
    """critic F2: contract-class failure (retries exhausted) → raise, never fall back to CLI."""
    from server.audit import runner

    monkeypatch.setenv("AUDIT_DIRECT_CONNECT", "1")
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runner, "EXPENSE_RULES_DIR", tmp_path / "no-rules")

    async def failing_direct(
        prompt, *, request_id, tenant, schema_name, contract_max_retry, **_opts
    ):
        raise DirectContractError("model output failed schema validation after retries")

    monkeypatch.setattr(runner, "run_direct_audit", failing_direct)
    monkeypatch.setattr(runner, "run_agent_json", _fail_if_called)

    with pytest.raises(DirectContractError):
        asyncio.run(
            runner.run_inline_directory_audit(
                "no/such/dir", request_id="rid-no-fallback", tenant="acme"
            )
        )


def test_flag_on_forwards_archive_to_results_opt(monkeypatch, tmp_path):
    """review F3: flag-on 分支显式转发 archive_to_results 给直连路径（不静默丢弃）。"""
    from server.audit import runner

    monkeypatch.setenv("AUDIT_DIRECT_CONNECT", "1")
    monkeypatch.setattr(runner, "run_agent_json", _fail_if_called)
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runner, "EXPENSE_RULES_DIR", tmp_path / "no-rules")

    seen = {}

    async def capture_direct(
        prompt, *, request_id, tenant, schema_name, contract_max_retry, **opts
    ):
        seen.update(opts)
        return {"verdict": "approved"}, _fake_meta(request_id, mode="direct")

    monkeypatch.setattr(runner, "run_direct_audit", capture_direct)

    asyncio.run(
        runner.run_inline_directory_audit(
            "no/such/dir",
            request_id="rid-archive-opt",
            tenant="acme",
            archive_to_results=False,
            project_id="proj-9",
        )
    )

    assert seen["archive_to_results"] is False
    assert seen["project_id"] == "proj-9"


def test_flag_on_rejects_unsupported_opt(monkeypatch, tmp_path):
    """review F3: 直连路径遇未声明 opt（如 evidence_source）→ fail-fast，不静默漂移。"""
    from server.audit import runner

    monkeypatch.setenv("AUDIT_DIRECT_CONNECT", "1")
    monkeypatch.setattr(runner, "run_direct_audit", _fail_if_called)
    monkeypatch.setattr(runner, "run_agent_json", _fail_if_called)
    monkeypatch.setattr(runner, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(runner, "EXPENSE_RULES_DIR", tmp_path / "no-rules")

    with pytest.raises(ValueError, match="evidence_source"):
        asyncio.run(
            runner.run_inline_directory_audit(
                "no/such/dir",
                request_id="rid-bad-opt",
                tenant="acme",
                evidence_source="some-corpus",
            )
        )
