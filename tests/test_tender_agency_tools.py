"""Phase A.2 受控补证工具面：``TENDER_AGENCY=1`` 才加 Grep/Read，且被钉死在本案 corpus/。

纠偏令 v2 纠偏令一的两条硬约束，本文件逐条机械化：

- **默认零变更**：不设 ``TENDER_AGENCY`` 时，评标注入与工具面必须与开关引入前逐字一致
  （对照组 = 当前 5ccbb361 形态，实验组才是 1；两组要可比，对照组就不能被顺手改动）。
- **钉死在 corpus/**：评标子进程处理的是**攻击者可控**的投标 PDF。给它 Read/Grep 等于开了
  一个任意文件读面，因此路径闸是 fail-closed 的 PreToolUse hook（仿 ocr-page 先例），
  不是提示词里的一句"请只读 corpus"。单次 Read 有行数上限——补证是"按行区间取原文"，
  不是把整份底稿再拉一遍（那正是 B 项延时治理要消灭的重复预填充）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from server.common.agent_bridge import CORPUS_READ_MAX_LINES, AgentRunMeta, build_options
from server.tender import corpus_materialize as cm
from server.tender import doc_layer, doc_pipeline, runner

DRAFT = "### 文件: 招标文件.pdf (kind=pdf_text, route=native)\n【第 1 页】\n评标办法"


def _fake_meta() -> AgentRunMeta:
    return AgentRunMeta(
        request_id="rid-agency",
        conversation_id="conv-test",
        claude_session_id="sess-test",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="common/audit-result.schema.json",
        log_file="logs/test.log",
        result_file=None,
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def _run(monkeypatch: pytest.MonkeyPatch, *, draft: str | None, directory: str) -> dict[str, Any]:
    """跑一次评标，回传服务端实际发给 SDK 的那套 kwargs。"""
    calls: dict[str, Any] = {}

    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        calls.update(opts)
        return {"verdict": "manual_review"}, _fake_meta()

    monkeypatch.setattr(runner, "run_command_json", fake_run_command_json)
    monkeypatch.setattr(doc_layer, "get_project_doc", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *_a, **_kw: draft)
    monkeypatch.setattr(runner, "resolve_project_criteria", lambda *_a, **_kw: (None, None))
    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-agency",
            tenant="acme",
            directory_path=directory,
            project_id="tp-test",
        )
    )
    return calls


class TestAgencySwitchDefaultsOff:
    def test_tool_surface_is_unchanged_without_the_flag(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("TENDER_AGENCY", raising=False)

        opts = _run(monkeypatch, draft=DRAFT, directory=str(tmp_path))

        assert opts["tools"] == ["Bash"]
        assert opts["allowed_tools"] == ["Bash"]
        assert "corpus_root" not in opts

    def test_injection_is_unchanged_without_the_flag(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """初始注入不变（检索一次做完的证据块照旧）——补证指引不得漏进对照组。"""
        monkeypatch.delenv("TENDER_AGENCY", raising=False)

        opts = _run(monkeypatch, draft=DRAFT, directory=str(tmp_path))

        assert "corpus" not in opts["context"]
        assert "Grep" not in opts["context"]

    def test_extraction_path_never_gets_the_agency_surface(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """开关只作用于**评标**会话：criteria 抽取那条路径的锁面照旧只有 Bash。"""
        monkeypatch.setenv("TENDER_AGENCY", "1")

        kwargs = doc_pipeline._extraction_call_kwargs("acme", case_path="/x", draft_present=True)

        assert kwargs["tools"] == ["Bash"]
        assert kwargs["allowed_tools"] == ["Bash"]


class TestAgencySwitchOn:
    def test_flag_widens_the_surface_to_bash_grep_read(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("TENDER_AGENCY", "1")

        opts = _run(monkeypatch, draft=DRAFT, directory=str(tmp_path))

        assert opts["tools"] == ["Bash", "Grep", "Read"]
        assert opts["allowed_tools"] == ["Bash", "Grep", "Read"]

    def test_flag_binds_the_corpus_root_of_this_case(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """工具面一放开，路径闸就必须同时绑上——两者分开上线等于裸奔一版。"""
        monkeypatch.setenv("TENDER_AGENCY", "1")

        opts = _run(monkeypatch, draft=DRAFT, directory=str(tmp_path))

        assert opts["corpus_root"] == cm.corpus_dir(tmp_path)

    def test_flag_appends_the_follow_up_guidance(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("TENDER_AGENCY", "1")

        context = _run(monkeypatch, draft=DRAFT, directory=str(tmp_path))["context"]

        assert context.startswith("=== OCR/直读底稿"), "补证指引必须**追加在末尾**，不改初始注入"
        assert "不等于" in context and "未提供" in context  # 未注入≠未提供
        assert str(cm.corpus_dir(tmp_path)) in context
        assert "Grep" in context and "Read" in context
        assert str(CORPUS_READ_MAX_LINES) in context
        assert "页锚" in context

    def test_missing_draft_still_falls_back_to_free_reads(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """底稿缺失是既有降级路径：模型必须还能自己读原件，不锁面也不绑 corpus。"""
        monkeypatch.setenv("TENDER_AGENCY", "1")

        opts = _run(monkeypatch, draft="", directory=str(tmp_path))

        assert "tools" not in opts and "corpus_root" not in opts


# ── PreToolUse 路径闸 ─────────────────────────────────────────────────────────


@pytest.fixture
def corpus_case(tmp_path: Path) -> dict[str, Path]:
    case_root = tmp_path / "case-a"
    corpus = cm.corpus_dir(case_root)
    corpus.mkdir(parents=True)
    (corpus / "投标文件.pdf.txt").write_text("【第 1 页】\n正文", encoding="utf-8")
    secret = case_root / "audit-request.json"
    secret.write_text("{}", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("case 外的文件", encoding="utf-8")
    (corpus / "escape.txt").symlink_to(outside)
    return {
        "case_root": case_root,
        "corpus": corpus,
        "inside": corpus / "投标文件.pdf.txt",
        "sibling": secret,
        "outside": outside,
        "escaped": corpus / "escape.txt",
    }


def _hooks_for(tool: str, options) -> list:
    assert options.hooks is not None
    return [m for m in options.hooks["PreToolUse"] if m.matcher == tool]


async def _decide(options, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    matchers = _hooks_for(tool_name, options)
    assert len(matchers) == 1, f"{tool_name} 没有唯一的 PreToolUse 闸"
    result = await matchers[0].hooks[0]({"tool_name": tool_name, "tool_input": tool_input}, None, None)
    return result["hookSpecificOutput"]


def _allows(options, tool_name: str, tool_input: dict[str, Any]) -> bool:
    return asyncio.run(_decide(options, tool_name, tool_input))["permissionDecision"] == "allow"


class TestCorpusHookIsOptIn:
    def test_no_corpus_hook_without_the_parameter(self, corpus_case) -> None:
        """不传 corpus_root → PreToolUse 仍只有 ocr-page 那一个 Bash 闸（零变更）。"""
        options = build_options(case_root=corpus_case["case_root"])

        assert [m.matcher for m in options.hooks["PreToolUse"]] == ["Bash"]

    def test_corpus_hook_joins_the_existing_bash_hook(self, corpus_case) -> None:
        options = build_options(
            case_root=corpus_case["case_root"], corpus_root=corpus_case["corpus"]
        )

        assert [m.matcher for m in options.hooks["PreToolUse"]] == ["Bash", "Read", "Grep"]


class TestCorpusHookBoundary:
    @pytest.fixture
    def options(self, corpus_case):
        return build_options(
            case_root=corpus_case["case_root"], corpus_root=corpus_case["corpus"]
        )

    def test_read_inside_corpus_with_a_bounded_window_is_allowed(self, options, corpus_case):
        assert _allows(
            options, "Read", {"file_path": str(corpus_case["inside"]), "offset": 1, "limit": 200}
        )

    def test_read_outside_the_corpus_is_denied(self, options, corpus_case):
        for target in ("sibling", "outside"):
            assert not _allows(
                options, "Read", {"file_path": str(corpus_case[target]), "limit": 10}
            ), target

    def test_read_through_a_symlink_escape_is_denied(self, options, corpus_case):
        assert not _allows(
            options, "Read", {"file_path": str(corpus_case["escaped"]), "limit": 10}
        )

    def test_relative_and_traversal_paths_are_denied(self, options, corpus_case):
        traversal = f"{corpus_case['corpus']}/../audit-request.json"
        assert not _allows(options, "Read", {"file_path": traversal, "limit": 10})
        assert not _allows(options, "Read", {"file_path": "corpus/投标文件.pdf.txt", "limit": 10})

    def test_read_without_a_line_limit_is_denied(self, options, corpus_case):
        """缺 limit 时 Read 默认拉两千行——补证不是把整份底稿重新灌一遍。"""
        assert not _allows(options, "Read", {"file_path": str(corpus_case["inside"])})

    def test_read_beyond_the_line_cap_is_denied(self, options, corpus_case):
        assert not _allows(
            options,
            "Read",
            {"file_path": str(corpus_case["inside"]), "limit": CORPUS_READ_MAX_LINES + 1},
        )

    def test_grep_inside_the_corpus_is_allowed(self, options, corpus_case):
        assert _allows(options, "Grep", {"pattern": "投标报价", "path": str(corpus_case["corpus"])})

    def test_grep_without_a_path_is_denied(self, options):
        """不给 path 的 Grep 落到进程 cwd（= 整个项目根），是最容易被忽略的越界形态。"""
        assert not _allows(options, "Grep", {"pattern": "投标报价"})

    def test_grep_outside_the_corpus_is_denied(self, options, corpus_case):
        assert not _allows(
            options, "Grep", {"pattern": "密钥", "path": str(corpus_case["case_root"])}
        )

    def test_unexpected_tool_names_are_denied(self, options, corpus_case):
        """fail-closed：同一个 hook 被挂到别的工具上时拒绝，而不是默默放行。"""
        matcher = _hooks_for("Read", options)[0]
        decision = asyncio.run(
            matcher.hooks[0](
                {"tool_name": "Write", "tool_input": {"file_path": str(corpus_case["inside"])}},
                None,
                None,
            )
        )

        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_denial_reason_is_explicit(self, options, corpus_case):
        decision = asyncio.run(
            _decide(options, "Read", {"file_path": str(corpus_case["outside"]), "limit": 10})
        )

        assert decision["permissionDecision"] == "deny"
        assert decision["permissionDecisionReason"]


def test_max_turns_is_left_at_its_current_value(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """v2 明写 ``max_turns`` 维持现值：补证轮次不靠放宽总轮数换来。"""
    monkeypatch.setenv("TENDER_AGENCY", "1")
    monkeypatch.delenv("AUDIT_MAX_TURNS", raising=False)

    options = build_options(case_root=tmp_path, corpus_root=cm.corpus_dir(tmp_path))

    assert options.max_turns == 30
