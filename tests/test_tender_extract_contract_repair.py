"""(b) 抽取侧契约修补轮：criteria 抽取的 JSON 写坏不再一发定生死。

生产事故 2026-08-17：``/tender-extract-info`` 抛
``JSONContractError: 文本模式下未能从模型输出中解析出 JSON 对象``
（``doc_pipeline.py`` 的一次性调用 → ``json_bridge`` 的文本模式解析），一次失败即
``criteria_status=failed``；criteria 缺位 → 证据层跳过 → 整份底稿退回全量注入并被截断。

评标侧的同型失败早就不这么处置了：``runner`` 有重试环、``contract_repair`` 有 resume
修补轮，而 ``json_bridge`` 也早已把产生失败的 CLI 会话 id 戳进异常。抽取侧缺的只是接上——
本文件钉这条接线，以及"什么不该走修补轮"的边界。
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

import server.tender.doc_pipeline as tender_module
from server.common.agent_bridge import AgentRunMeta
from server.common.contract import JSONContractError

SESSION_ID = "sess-extract-77"

_SAMPLE_CRITERIA = {
    "source_ref": "招标文件 第三章 评标办法",
    "method": "综合评估法",
    "total_max": 100,
    "items": [{"item": "技术方案", "max": 40, "tag": "scored", "score_mode": "banded"}],
}


def _meta(rid: str = "rid-extract") -> AgentRunMeta:
    return AgentRunMeta(
        request_id=rid,
        conversation_id="conv-extract",
        claude_session_id=SESSION_ID,
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=None,
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def _make_project_doc(tenant: str) -> str:
    from server.stores.tender_doc_store import upsert_project_doc

    pid = f"tp-{uuid.uuid4().hex[:16]}"
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready")
    return pid


def _row(pid: str, tenant: str) -> dict:
    from server.stores.tender_doc_store import get_project_doc

    row = get_project_doc(pid, tenant)
    assert row is not None
    return row


def _repair_prompt(error_text: str) -> str:
    from server.tender.contract_repair import build_extraction_repair_prompt

    return build_extraction_repair_prompt(JSONContractError(error_text))


class TestExtractionRepairPrompt:
    def test_prompt_forbids_re_reading_and_re_extracting(self):
        prompt = _repair_prompt("坏 JSON")

        assert "不要重新读取" in prompt
        assert "不要重新抽取" in prompt

    def test_prompt_is_about_extraction_not_evaluation(self):
        """抽取会话里没有"评标结论"可言——照抄评标措辞会让模型去找一个不存在的上一轮。"""
        assert "评标" not in _repair_prompt("坏 JSON")

    def test_prompt_names_the_contract_that_must_hold(self):
        assert "criteria" in _repair_prompt("坏 JSON")

    def test_prompt_carries_the_actual_contract_error(self):
        assert "缺 items" in _repair_prompt("缺 items")

    def test_prompt_is_short_enough_to_be_worth_it(self):
        """修补轮的全部意义是不重发那份底稿；指令本身必须是常数级小。"""
        assert len(_repair_prompt("x" * 10_000).encode("utf-8")) < 4_000


class TestExtractionResumesInsteadOfRerunning:
    def test_second_attempt_resumes_the_session_with_a_repair_prompt(self, monkeypatch):
        tenant = "t-extract-repair"
        pid = _make_project_doc(tenant)
        full_runs: list[str] = []
        repairs: list[dict] = []

        async def failing_run_command_json(command_name, *args, **kwargs):
            full_runs.append(command_name)
            raise JSONContractError(
                "文本模式下未能从模型输出中解析出 JSON 对象（模型可能没按要求只输出 JSON）。",
                session_id=SESSION_ID,
            )

        async def fake_repair(prompt, **opts):
            repairs.append({"prompt": prompt, **opts})
            return {"criteria": _SAMPLE_CRITERIA, "tender_info": {"tenderee": "甲方建设有限公司"}}, _meta()

        monkeypatch.setattr(tender_module, "run_command_json", failing_run_command_json)
        monkeypatch.setattr(tender_module, "run_agent_json", fake_repair)

        asyncio.run(tender_module.extract_project_doc_info(pid, "/fake/case", "OCR 底稿", tenant))

        assert full_runs == ["tender-extract-info"], "整跑只应一次，第二次必须是修补轮"
        assert len(repairs) == 1
        assert repairs[0]["resume_session_id"] == SESSION_ID
        row = _row(pid, tenant)
        assert row["criteria_status"] == "ready"
        assert row["criteria_error"] is None
        assert json.loads(row["criteria"])["total_max"] == 100

    def test_repair_turn_does_not_resend_the_draft(self, monkeypatch):
        tenant = "t-extract-nodraft"
        pid = _make_project_doc(tenant)
        repairs: list[dict] = []
        draft = "招标文件正文" * 5_000

        async def failing_run_command_json(command_name, *args, **kwargs):
            raise JSONContractError("坏 JSON", session_id=SESSION_ID)

        async def fake_repair(prompt, **opts):
            repairs.append({"prompt": prompt, **opts})
            return {"criteria": _SAMPLE_CRITERIA}, _meta()

        monkeypatch.setattr(tender_module, "run_command_json", failing_run_command_json)
        monkeypatch.setattr(tender_module, "run_agent_json", fake_repair)

        asyncio.run(tender_module.extract_project_doc_info(pid, "/fake/case", draft, tenant))

        assert "招标文件正文招标文件正文" not in repairs[0]["prompt"]
        assert repairs[0]["structured"] is False
        assert repairs[0]["schema_name"] is None
        assert repairs[0]["archive_to_results"] is False
        assert repairs[0]["tenant"] == tenant

    def test_no_session_id_falls_back_to_the_full_rerun(self, monkeypatch):
        """失败发生在会话建立之前 → 没有会话可 resume，回落整跑，不静默少跑一轮。"""
        tenant = "t-extract-nosession"
        pid = _make_project_doc(tenant)
        calls: list[str] = []

        async def failing_run_command_json(command_name, *args, **kwargs):
            calls.append("full")
            raise JSONContractError("坏 JSON")

        def explode(*_a, **_kw):
            raise AssertionError("没有会话 id 时不得走修补轮")

        monkeypatch.setattr(tender_module, "run_command_json", failing_run_command_json)
        monkeypatch.setattr(tender_module, "run_agent_json", explode)

        asyncio.run(tender_module.extract_project_doc_info(pid, "/fake/case", "OCR 底稿", tenant))

        assert calls == ["full"] * (tender_module.EXTRACT_CONTRACT_MAX_RETRY + 1)
        assert _row(pid, tenant)["criteria_status"] == "failed"

    def test_non_retryable_failure_never_reaches_the_repair_turn(self, monkeypatch):
        """爆窗是一次性硬失败：resume 同一会话只会再爆一次窗（对齐评标侧既有纪律）。"""
        tenant = "t-extract-toolong"
        pid = _make_project_doc(tenant)
        calls: list[str] = []

        async def failing_run_command_json(command_name, *args, **kwargs):
            calls.append("full")
            raise JSONContractError("Prompt is too long: 780000 tokens", session_id=SESSION_ID)

        def explode(*_a, **_kw):
            raise AssertionError("不可重试错误不得走修补轮")

        monkeypatch.setattr(tender_module, "run_command_json", failing_run_command_json)
        monkeypatch.setattr(tender_module, "run_agent_json", explode)

        asyncio.run(tender_module.extract_project_doc_info(pid, "/fake/case", "OCR 底稿", tenant))

        assert calls == ["full"]
        assert _row(pid, tenant)["criteria_status"] == "failed"

    def test_repeated_failures_land_on_an_honest_failed_state(self, monkeypatch):
        """修补仍失败 → failed + 可读原因（由 (a) 的诚实状态接住），ocr_status 不受牵连。"""
        tenant = "t-extract-exhausted"
        pid = _make_project_doc(tenant)
        calls: list[str] = []

        async def failing_run_command_json(command_name, *args, **kwargs):
            calls.append("full")
            raise JSONContractError("坏 JSON", session_id=SESSION_ID)

        async def failing_repair(prompt, **opts):
            calls.append("repair")
            raise JSONContractError("还是坏 JSON", session_id=SESSION_ID)

        monkeypatch.setattr(tender_module, "run_command_json", failing_run_command_json)
        monkeypatch.setattr(tender_module, "run_agent_json", failing_repair)

        asyncio.run(tender_module.extract_project_doc_info(pid, "/fake/case", "OCR 底稿", tenant))

        assert len(calls) == tender_module.EXTRACT_CONTRACT_MAX_RETRY + 1
        assert calls[0] == "full" and calls[1:] == ["repair"] * tender_module.EXTRACT_CONTRACT_MAX_RETRY
        row = _row(pid, tenant)
        assert row["criteria_status"] == "failed"
        assert "extraction_failed" in row["criteria_error"]
        assert row["ocr_status"] == "ready"
        assert row["criteria_source"] is None

    def test_structural_criteria_problem_does_not_trigger_a_repair_turn(self, monkeypatch):
        """抽出来的 JSON 合法但没有评分项 → 那不是格式问题，修补轮救不了，
        且它连 ``session_id`` 都没有，走下去只会白白整跑一遍。"""
        tenant = "t-extract-structural"
        pid = _make_project_doc(tenant)
        calls: list[str] = []

        async def fake_run_command_json(command_name, *args, **kwargs):
            calls.append("full")
            return {"criteria": {"method": "综合评估法", "items": []}}, _meta()

        def explode(*_a, **_kw):
            raise AssertionError("结构问题不得走修补轮")

        monkeypatch.setattr(tender_module, "run_command_json", fake_run_command_json)
        monkeypatch.setattr(tender_module, "run_agent_json", explode)

        asyncio.run(tender_module.extract_project_doc_info(pid, "/fake/case", "OCR 底稿", tenant))

        assert calls == ["full"]
        row = _row(pid, tenant)
        assert row["criteria_status"] == "failed"
        assert "items_empty" in row["criteria_error"]

    def test_happy_path_makes_no_repair_call(self, monkeypatch):
        tenant = "t-extract-happy-norepair"
        pid = _make_project_doc(tenant)

        async def fake_run_command_json(command_name, *args, **kwargs):
            return {"criteria": _SAMPLE_CRITERIA}, _meta()

        def explode(*_a, **_kw):
            raise AssertionError("成功路径不得触发修补轮")

        monkeypatch.setattr(tender_module, "run_command_json", fake_run_command_json)
        monkeypatch.setattr(tender_module, "run_agent_json", explode)

        asyncio.run(tender_module.extract_project_doc_info(pid, "/fake/case", "OCR 底稿", tenant))

        assert _row(pid, tenant)["criteria_status"] == "ready"


@pytest.mark.parametrize("retry_ceiling", [0, 1])
def test_retry_ceiling_is_honoured(monkeypatch, retry_ceiling):
    """上限可调且真的封顶——重试环跑飞会把上传时的抽取变成无界模型消耗。"""
    tenant = "t-extract-ceiling"
    pid = _make_project_doc(tenant)
    calls: list[str] = []

    monkeypatch.setattr(tender_module, "EXTRACT_CONTRACT_MAX_RETRY", retry_ceiling)

    async def failing_run_command_json(command_name, *args, **kwargs):
        calls.append("full")
        raise JSONContractError("坏 JSON", session_id=SESSION_ID)

    async def failing_repair(prompt, **opts):
        calls.append("repair")
        raise JSONContractError("还是坏 JSON", session_id=SESSION_ID)

    monkeypatch.setattr(tender_module, "run_command_json", failing_run_command_json)
    monkeypatch.setattr(tender_module, "run_agent_json", failing_repair)

    asyncio.run(tender_module.extract_project_doc_info(pid, "/fake/case", "OCR 底稿", tenant))

    assert len(calls) == retry_ceiling + 1
    assert _row(pid, tenant)["criteria_status"] == "failed"
