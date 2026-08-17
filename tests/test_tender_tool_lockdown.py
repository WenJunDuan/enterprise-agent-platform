"""B. 底稿已注入时禁止自由 Glob/Read（唯一例外：ocr-page 按页重识别）。

`error_max_turns` 的根因是自相矛盾的指令：注入头写"无需再 Read 文件"，S0 却让模型 `Glob`
列目录、后续步骤再逐个 `Read`——每一次都是一整轮重新预填充 ~83K token 底稿。提示词说服不了
模型的部分由**工具面**兜底：底稿在场时子进程根本不存在 Read/Glob/Task，只留受 PreToolUse
hook 约束的 Bash 供 ocr-page 重识别。

底稿缺失（context 为 None）时不锁——那条路径模型必须自己去读文件。
"""

from __future__ import annotations

import asyncio

from server.common.agent_bridge import AgentRunMeta, build_options
from server.platform.paths import PROJECT_ROOT
from server.tender import doc_layer, runner

COMMAND_PATH = PROJECT_ROOT / ".claude/commands/tender-evaluate.md"


def _fake_meta(request_id: str) -> AgentRunMeta:
    return AgentRunMeta(
        request_id=request_id,
        conversation_id="conv-test",
        claude_session_id="sess-test",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="common/audit-result.schema.json",
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def _run(monkeypatch, *, draft: str | None) -> dict:
    calls: dict = {}

    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        calls.update(opts)
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(runner, "run_command_json", fake_run_command_json)
    monkeypatch.setattr(doc_layer, "get_project_doc", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: draft)
    monkeypatch.setattr(runner, "resolve_project_criteria", lambda *_a, **_kw: (None, None))
    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-lockdown",
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-test",
        )
    )
    return calls


class TestServerSideLockdown:
    def test_injected_draft_leaves_only_bash_for_ocr_page(self, monkeypatch):
        opts = _run(monkeypatch, draft="### 文件: 招标文件.pdf\n【第 1 页】正文")

        assert opts["tools"] == runner.DRAFT_INJECTED_TOOLS
        assert opts["allowed_tools"] == runner.DRAFT_INJECTED_TOOLS

    def test_lockdown_keeps_bash_so_ocr_page_reread_stays_reachable(self, monkeypatch):
        opts = _run(monkeypatch, draft="### 文件: 招标文件.pdf\n【第 1 页】正文")

        assert "Bash" in opts["tools"]

    def test_lockdown_removes_read_glob_and_task(self, monkeypatch):
        opts = _run(monkeypatch, draft="### 文件: 招标文件.pdf\n【第 1 页】正文")

        for banned in ("Read", "Glob", "Grep", "Task"):
            assert banned not in opts["tools"], banned
            assert banned not in opts["allowed_tools"], banned

    def test_no_draft_keeps_the_default_tool_inventory(self, monkeypatch):
        """底稿缺失是既有的降级路径：模型必须还能自己 Read/Glob，不锁。"""
        opts = _run(monkeypatch, draft="")

        assert "tools" not in opts
        assert "allowed_tools" not in opts


class TestLockdownActuallyLandsInSdkOptions:
    """闸必须穿透 build_options——空/假的工具清单会被 `or _AGENT_TOOLS` 悄悄还原成全量。"""

    def test_build_options_honours_the_lockdown_inventory(self, tmp_path):
        options = build_options(
            case_root=tmp_path,
            tools=list(runner.DRAFT_INJECTED_TOOLS),
            allowed_tools=list(runner.DRAFT_INJECTED_TOOLS),
        )

        assert "Read" not in options.tools
        assert "Glob" not in options.tools
        assert "Bash" in options.tools
        assert "Bash" in options.allowed_tools

    def test_lockdown_inventory_is_not_falsy(self):
        """空列表会被 build_options 的 ``or _AGENT_TOOLS`` 还原成全量工具——必须非空。"""
        assert runner.DRAFT_INJECTED_TOOLS


class TestPromptDropsTheContradictoryGlob:
    def test_s0_no_longer_orders_a_glob_sweep(self):
        text = COMMAND_PATH.read_text(encoding="utf-8")

        assert "`Glob` 列目录" not in text

    def test_prompt_states_the_ban_and_its_single_exception(self):
        text = COMMAND_PATH.read_text(encoding="utf-8")

        assert "禁止 `Glob` / `Read`" in text
        assert "ocr-page" in text

    def test_truncation_fallback_survives(self):
        """注入不全的兜底（截断标记 → 证据缺失 → manual_review）不得被本项删掉。

        锁工具面后模型无法自行补读，这条降级路径是唯一出口，因此服务端标记与提示词侧的
        处置口径必须同时在场。
        """
        assert "已省略" in runner._TRUNCATION_NOTICE
        assert "证据缺失" in runner._TRUNCATION_NOTICE
        assert "证据缺失" in COMMAND_PATH.read_text(encoding="utf-8")
