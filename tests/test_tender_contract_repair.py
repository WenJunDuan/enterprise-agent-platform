"""D. 契约失败改 resume 修补轮，不再整单从头重跑。

原实现：模型写坏 JSON → 整个 prompt（命令正文 + ~83K token 底稿）原样重发，模型从头再评
一遍标，最多 2 次。评标 happy path 已是 7-12 轮 × 1-3 分钟，一次整单重跑就把 10 分钟档
推成 20 分钟档——而失败的只是**最后一步的 JSON 序列化**，评标结论本身已经在会话里。

改法：抛 ``JSONContractError`` 时戳上产生它的 CLI 会话 id，重试环据它 resume 同一会话，
只发一条短修补指令（"别重评、别读文件，把 JSON 改对再发一次"）。

保留的既有语义：不可重试错误（爆窗）仍立即上抛；拿不到会话 id 时回落整单重跑；
重试次数上限与 ``meta.retry_count`` 不变。
"""

from __future__ import annotations

import asyncio

import pytest
from claude_agent_sdk import ResultMessage, SystemMessage

from server.common import json_bridge
from server.common.agent_bridge import AgentRunMeta
from server.common.contract import JSONContractError
from server.tender import contract_repair, doc_layer

SESSION_ID = "sess-from-cli-42"


def _fake_meta(request_id: str) -> AgentRunMeta:
    return AgentRunMeta(
        request_id=request_id,
        conversation_id="conv-test",
        claude_session_id=SESSION_ID,
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="common/audit-result.schema.json",
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


class TestErrorCarriesTheSession:
    def test_default_session_id_is_none(self):
        assert JSONContractError("boom").session_id is None

    def test_bridge_stamps_the_cli_session_on_contract_failure(self, monkeypatch):
        """没有会话 id 就没法 resume——这是整条修补路径的前提，必须真的从 bridge 里带出来。"""

        async def fake_query(*, prompt, options):  # noqa: ARG001
            yield SystemMessage(subtype="init", data={"session_id": SESSION_ID})
            yield ResultMessage(
                subtype="success",
                duration_ms=1,
                duration_api_ms=1,
                is_error=False,
                num_turns=1,
                session_id=SESSION_ID,
                result="这不是 JSON，模型又写散文了",
            )

        monkeypatch.setattr(json_bridge, "query", fake_query)

        with pytest.raises(JSONContractError) as excinfo:
            asyncio.run(
                json_bridge.run_agent_json(
                    "prompt",
                    schema_name=None,
                    structured=False,
                    archive_to_results=False,
                    tenant="acme",
                )
            )

        assert excinfo.value.session_id == SESSION_ID


class TestRepairPrompt:
    def test_prompt_forbids_re_evaluating_and_re_reading(self):
        prompt = contract_repair.build_repair_prompt(JSONContractError("坏 JSON"))

        assert "不要重新评标" in prompt
        assert "不要重新读取任何文件" in prompt

    def test_prompt_carries_the_actual_contract_error(self):
        prompt = contract_repair.build_repair_prompt(JSONContractError("缺 pending_reason"))

        assert "缺 pending_reason" in prompt

    def test_prompt_is_short_enough_to_be_worth_it(self):
        """修补轮的全部意义是不重发 ~83K token；指令本身必须是常数级小。"""
        prompt = contract_repair.build_repair_prompt(JSONContractError("x" * 10_000))

        assert len(prompt.encode("utf-8")) < 4_000

    def test_session_id_reader_ignores_non_contract_errors(self):
        assert contract_repair.repair_session_id(RuntimeError("nope")) is None
        assert contract_repair.repair_session_id(JSONContractError("no session")) is None
        assert (
            contract_repair.repair_session_id(JSONContractError("x", session_id=SESSION_ID))
            == SESSION_ID
        )


def _stub_context(monkeypatch, runner) -> None:
    monkeypatch.setattr(doc_layer, "load_doc_layer_context", lambda *_a, **_kw: None)
    monkeypatch.setattr(doc_layer, "load_doc_layer_context_slim", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: "底稿")
    monkeypatch.setattr(runner, "resolve_project_criteria", lambda *_a, **_kw: (None, None))


class TestRunnerUsesRepairInsteadOfFullRerun:
    def test_second_attempt_resumes_the_session_with_a_repair_prompt(self, monkeypatch):
        from server.tender import runner

        full_runs: list[str] = []
        repairs: list[dict] = []

        async def failing_run_command_json(command_name, *arguments, schema_name, **opts):
            full_runs.append(opts["request_id"])
            raise JSONContractError("坏 JSON", session_id=SESSION_ID)

        async def fake_repair(prompt, **opts):
            repairs.append({"prompt": prompt, **opts})
            return {"verdict": "approved"}, _fake_meta(opts["request_id"])

        _stub_context(monkeypatch, runner)
        monkeypatch.setattr(runner, "run_command_json", failing_run_command_json)
        monkeypatch.setattr(runner, "run_agent_json", fake_repair)

        payload, meta = asyncio.run(
            runner.run_tender_evaluation(
                request_id="rid-repair",
                tenant="acme",
                directory_path="/fake/dir",
                project_id="tp-test",
            )
        )

        assert payload["verdict"] == "approved"
        assert len(full_runs) == 1, "整单只应跑一次，第二次必须是修补轮"
        assert len(repairs) == 1
        assert repairs[0]["resume_session_id"] == SESSION_ID
        assert meta.retry_count == 1

    def test_repair_turn_does_not_resend_the_draft(self, monkeypatch):
        from server.tender import runner

        repairs: list[dict] = []

        async def failing_run_command_json(command_name, *arguments, schema_name, **opts):
            raise JSONContractError("坏 JSON", session_id=SESSION_ID)

        async def fake_repair(prompt, **opts):
            repairs.append({"prompt": prompt, **opts})
            return {"verdict": "approved"}, _fake_meta(opts["request_id"])

        _stub_context(monkeypatch, runner)
        monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: "底稿" * 5_000)
        monkeypatch.setattr(runner, "run_command_json", failing_run_command_json)
        monkeypatch.setattr(runner, "run_agent_json", fake_repair)

        asyncio.run(
            runner.run_tender_evaluation(
                request_id="rid-repair-small",
                tenant="acme",
                directory_path="/fake/dir",
                project_id="tp-test",
            )
        )

        assert "底稿底稿" not in repairs[0]["prompt"]

    def test_repair_keeps_the_evidence_gate_wired(self, monkeypatch):
        """修补轮产出的仍是本单结论，出处回查闸不能因为换了入口就掉线。"""
        from server.tender import runner

        repairs: list[dict] = []

        async def failing_run_command_json(command_name, *arguments, schema_name, **opts):
            raise JSONContractError("坏 JSON", session_id=SESSION_ID)

        async def fake_repair(prompt, **opts):
            repairs.append(opts)
            return {"verdict": "approved"}, _fake_meta(opts["request_id"])

        _stub_context(monkeypatch, runner)
        monkeypatch.setattr(runner, "run_command_json", failing_run_command_json)
        monkeypatch.setattr(runner, "run_agent_json", fake_repair)

        asyncio.run(
            runner.run_tender_evaluation(
                request_id="rid-repair-evidence",
                tenant="acme",
                directory_path="/fake/dir",
                project_id="tp-test",
                bid_id="bid-1",
            )
        )

        assert repairs[0]["evidence_source"] == "底稿"
        assert repairs[0]["schema_name"] == runner.TENDER_OUTPUT_SCHEMA_NAME
        assert repairs[0]["bid_id"] == "bid-1"
        assert repairs[0]["structured"] is False

    def test_repeated_failures_still_stop_at_the_retry_ceiling(self, monkeypatch):
        from server.tender import runner

        calls: list[str] = []

        async def failing_run_command_json(command_name, *arguments, schema_name, **opts):
            calls.append("full")
            raise JSONContractError("坏 JSON", session_id=SESSION_ID)

        async def failing_repair(prompt, **opts):
            calls.append("repair")
            raise JSONContractError("还是坏 JSON", session_id=SESSION_ID)

        _stub_context(monkeypatch, runner)
        monkeypatch.setattr(runner, "run_command_json", failing_run_command_json)
        monkeypatch.setattr(runner, "run_agent_json", failing_repair)

        with pytest.raises(JSONContractError):
            asyncio.run(
                runner.run_tender_evaluation(
                    request_id="rid-repair-exhausted",
                    tenant="acme",
                    directory_path="/fake/dir",
                    project_id="tp-test",
                )
            )

        assert len(calls) == runner.TENDER_CONTRACT_MAX_RETRY + 1
        assert calls == ["full", "repair", "repair"]

    def test_no_session_id_falls_back_to_the_full_rerun(self, monkeypatch):
        """拿不到会话（失败发生在会话建立之前）→ 保留原来的整单重跑，不静默少跑一轮。"""
        from server.tender import runner

        calls: list[str] = []

        async def failing_run_command_json(command_name, *arguments, schema_name, **opts):
            calls.append("full")
            raise JSONContractError("坏 JSON")

        def explode(*_a, **_kw):
            raise AssertionError("没有会话 id 时不得走修补轮")

        _stub_context(monkeypatch, runner)
        monkeypatch.setattr(runner, "run_command_json", failing_run_command_json)
        monkeypatch.setattr(runner, "run_agent_json", explode)

        with pytest.raises(JSONContractError):
            asyncio.run(
                runner.run_tender_evaluation(
                    request_id="rid-repair-nosession",
                    tenant="acme",
                    directory_path="/fake/dir",
                    project_id="tp-test",
                )
            )

        assert calls == ["full"] * (runner.TENDER_CONTRACT_MAX_RETRY + 1)

    def test_non_retryable_failure_never_reaches_the_repair_turn(self, monkeypatch):
        """爆窗是一次性硬失败：resume 同一会话只会再爆一次窗。"""
        from server.tender import runner

        async def failing_run_command_json(command_name, *arguments, schema_name, **opts):
            raise JSONContractError("Prompt is too long: 78000 tokens", session_id=SESSION_ID)

        def explode(*_a, **_kw):
            raise AssertionError("不可重试错误不得走修补轮")

        _stub_context(monkeypatch, runner)
        monkeypatch.setattr(runner, "run_command_json", failing_run_command_json)
        monkeypatch.setattr(runner, "run_agent_json", explode)

        with pytest.raises(JSONContractError):
            asyncio.run(
                runner.run_tender_evaluation(
                    request_id="rid-repair-toolong",
                    tenant="acme",
                    directory_path="/fake/dir",
                    project_id="tp-test",
                )
            )
