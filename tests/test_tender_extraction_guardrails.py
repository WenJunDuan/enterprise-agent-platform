"""P0.3 · criteria 抽取补齐评标路径早已有的两道保护：硬超时 + 底稿在场时锁工具面。

抽取与评标是同一种调用（同一个 CLI、同一份大底稿、同一个模型），但保护只做在评标那一侧：

- **无超时**：评标侧 ``worker`` 有 ``asyncio.wait_for``，抽取侧一次调用可以永远挂着。线上
  实测单次抽取跑到 16 分钟仍未结束，而评标入口要等 criteria 到终态才放行——一次挂死把
  整条链路一起拖住。
- **未锁工具面**：抽取回落 ``build_options`` 的 6 工具白名单（实测进程实参
  ``--tools Read,Glob,Grep,Write,Skill,Task --max-turns 50``），底稿明明已由 ``context``
  注入。评标侧 2026-08-17 已为此锁成 ``DRAFT_INJECTED_TOOLS``（理由：模型无视"无需再
  Read"的提示，每轮重新预填充底稿），抽取侧漏了。

两道保护都**复用评标侧既有常量与形态**，不新建机制——本文件同时钉住这条纪律，否则下一次
改评标侧的工具面时抽取侧又会漂开。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from server.common.agent_bridge import AgentRunMeta, build_options
from server.tender import doc_pipeline
from server.tender.runner import DRAFT_INJECTED_TOOLS

_DRAFT = "招标文件 OCR 底稿正文"
_CASE_PATH = "/fake/tender-case"
_SAMPLE_CRITERIA = {
    "method": "综合评估法",
    "items": [{"item": "技术方案", "max": 40, "tag": "scored", "score_mode": "banded"}],
}


def _meta() -> AgentRunMeta:
    return AgentRunMeta(
        request_id="rid-extract",
        conversation_id="conv-extract",
        claude_session_id="sess-extract",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name=None,
        log_file="logs/test.log",
        result_file=None,
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def _project(tenant: str) -> str:
    from server.stores.tender_doc_store import upsert_project_doc

    pid = f"tp-{uuid.uuid4().hex[:16]}"
    upsert_project_doc(project_id=pid, tenant=tenant, tender_files="[]", ocr_status="ready")
    return pid


def _row(pid: str, tenant: str) -> dict:
    from server.stores.tender_doc_store import get_project_doc

    row = get_project_doc(pid, tenant)
    assert row is not None
    return row


@pytest.fixture
def captured(monkeypatch) -> list[dict]:
    """记录整跑与修补轮各自收到的调用参数。"""
    calls: list[dict] = []

    async def fake_run_command_json(command_name, *args, **kwargs):
        calls.append({"kind": "full", "command": command_name, "args": args, **kwargs})
        return {"criteria": _SAMPLE_CRITERIA}, _meta()

    monkeypatch.setattr(doc_pipeline, "run_command_json", fake_run_command_json)
    return calls


# ── 硬超时 ───────────────────────────────────────────────────────────────────


def test_extraction_is_bounded_by_a_hard_timeout(monkeypatch):
    """一次挂死的抽取必须自己结束，而不是永远占着 criteria 的非终态。"""
    tenant = "t-extract-timeout"
    pid = _project(tenant)
    monkeypatch.setattr(doc_pipeline, "EXTRACT_TIMEOUT_SEC", 0.05)

    async def never_returns(*_a, **_kw):
        await asyncio.sleep(30)

    monkeypatch.setattr(doc_pipeline, "run_command_json", never_returns)

    asyncio.run(doc_pipeline.extract_project_doc_info(pid, _CASE_PATH, _DRAFT, tenant))

    assert _row(pid, tenant)["criteria_status"] == "failed"


def test_timeout_error_carries_an_executable_unlock_action(monkeypatch):
    """AC：``criteria_error`` 要告诉用户下一步做什么，不是又一句"识别失败"。"""
    tenant = "t-extract-timeout-msg"
    pid = _project(tenant)
    monkeypatch.setattr(doc_pipeline, "EXTRACT_TIMEOUT_SEC", 0.05)

    async def never_returns(*_a, **_kw):
        await asyncio.sleep(30)

    monkeypatch.setattr(doc_pipeline, "run_command_json", never_returns)

    asyncio.run(doc_pipeline.extract_project_doc_info(pid, _CASE_PATH, _DRAFT, tenant))

    error = _row(pid, tenant)["criteria_error"]
    assert "extraction_timeout" in error, "机器码要留，运维按码 grep"
    assert "重新上传" in error, "用户侧的可执行动作"
    assert "TENDER_EXTRACT_TIMEOUT_SEC" in error, "运维侧的可执行动作（放宽上限的那个旋钮）"
    assert "超时" in error


def test_timeout_does_not_taint_the_ocr_ready_signal(monkeypatch):
    """抽取超时是非致命的：底稿已经识别好了，ocr_status 不得被牵连改写。"""
    tenant = "t-extract-timeout-ocr"
    pid = _project(tenant)
    monkeypatch.setattr(doc_pipeline, "EXTRACT_TIMEOUT_SEC", 0.05)

    async def never_returns(*_a, **_kw):
        await asyncio.sleep(30)

    monkeypatch.setattr(doc_pipeline, "run_command_json", never_returns)

    asyncio.run(doc_pipeline.extract_project_doc_info(pid, _CASE_PATH, _DRAFT, tenant))

    assert _row(pid, tenant)["ocr_status"] == "ready"


def test_timeout_default_is_configurable_and_positive():
    """默认与评标同量级、可配——写死一个数字等于把"这台机器慢"变成代码问题。"""
    assert doc_pipeline.EXTRACT_TIMEOUT_SEC > 0


def test_a_normal_extraction_is_not_cut_short(captured):
    """反向守卫：超时闸不得把正常抽取误杀（默认上限远大于一次正常往返）。"""
    tenant = "t-extract-normal"
    pid = _project(tenant)

    asyncio.run(doc_pipeline.extract_project_doc_info(pid, _CASE_PATH, _DRAFT, tenant))

    assert _row(pid, tenant)["criteria_status"] == "ready"


# ── 底稿在场时锁工具面 ───────────────────────────────────────────────────────


def test_draft_present_locks_the_tool_surface(captured):
    """底稿已由 context 注入 → 子进程不该还留着 Read/Glob 让它每轮重新预填充。"""
    tenant = "t-extract-lock"
    pid = _project(tenant)

    asyncio.run(doc_pipeline.extract_project_doc_info(pid, _CASE_PATH, _DRAFT, tenant))

    call = captured[0]
    assert call["tools"] == DRAFT_INJECTED_TOOLS
    assert call["allowed_tools"] == DRAFT_INJECTED_TOOLS


def test_the_lock_reuses_the_evaluation_side_constant(captured):
    """不新建机制：抽取侧用的必须**就是**评标侧那个常量，不是它的一份副本。"""
    tenant = "t-extract-same-const"
    pid = _project(tenant)

    asyncio.run(doc_pipeline.extract_project_doc_info(pid, _CASE_PATH, _DRAFT, tenant))

    assert captured[0]["tools"] is DRAFT_INJECTED_TOOLS


def test_locked_bash_stays_behind_the_ocr_page_hook(captured):
    """安全硬约束：锁面里唯一的 Bash 必须绑着 case_root，才受 ocr-page PreToolUse 闸约束。

    只锁 ``tools=["Bash"]`` 而不传 ``case_root``，等于给一个处理**攻击者可控 PDF** 的
    子进程配了裸 Bash + ``permission_mode=bypassPermissions``——比不锁还危险。
    """
    tenant = "t-extract-hook"
    pid = _project(tenant)

    asyncio.run(doc_pipeline.extract_project_doc_info(pid, _CASE_PATH, _DRAFT, tenant))

    call = captured[0]
    assert str(call["case_root"]) == _CASE_PATH
    options = build_options(
        case_root=call["case_root"], tools=call["tools"], allowed_tools=call["allowed_tools"]
    )
    assert list(options.tools) == ["Bash"], "锁面必须仍是 1 个工具，不得被回填成全量"
    assert "PreToolUse" in (options.hooks or {}), "Bash 必须挂着 ocr-page 白名单闸"


def test_no_draft_leaves_the_tool_surface_open(captured):
    """底稿缺失（OCR 空）时**不锁**：那条降级路径下模型必须还能自己读文件。"""
    tenant = "t-extract-nolock"
    pid = _project(tenant)

    asyncio.run(doc_pipeline.extract_project_doc_info(pid, _CASE_PATH, "", tenant))

    call = captured[0]
    assert "tools" not in call
    assert "allowed_tools" not in call
    assert "case_root" not in call


def test_repair_turn_inherits_the_same_locked_surface(monkeypatch):
    """整跑与修补轮共用一套调用参数——分两份写必然漂移（``runner._call_kwargs`` 先例）。"""
    from server.common.contract import JSONContractError

    tenant = "t-extract-repair-lock"
    pid = _project(tenant)
    repairs: list[dict] = []

    async def failing_full(command_name, *args, **kwargs):
        raise JSONContractError("坏 JSON", session_id="sess-extract")

    async def fake_repair(prompt, **opts):
        repairs.append(opts)
        return {"criteria": _SAMPLE_CRITERIA}, _meta()

    monkeypatch.setattr(doc_pipeline, "run_command_json", failing_full)
    monkeypatch.setattr(doc_pipeline, "run_agent_json", fake_repair)

    asyncio.run(doc_pipeline.extract_project_doc_info(pid, _CASE_PATH, _DRAFT, tenant))

    assert repairs[0]["tools"] == DRAFT_INJECTED_TOOLS
    assert repairs[0]["allowed_tools"] == DRAFT_INJECTED_TOOLS


def test_existing_call_parameters_are_untouched(captured):
    """回归守卫：加保护不得顺手改掉文本模式 / 不归档 / 无 schema 这三条既有约定。"""
    tenant = "t-extract-kwargs"
    pid = _project(tenant)

    asyncio.run(doc_pipeline.extract_project_doc_info(pid, _CASE_PATH, _DRAFT, tenant))

    call = captured[0]
    assert call["schema_name"] is None
    assert call["structured"] is False
    assert call["archive_to_results"] is False
    assert call["tenant"] == tenant
