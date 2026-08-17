"""A. 通则层法规 + 业务记忆改服务端注入（原为模型自取的 Read 指令）。

耗时账：每个 agent turn 都要重新预填充整份底稿（~83K token），让模型自己 Read 两个内容固定的
法规 JSON（合计 15,883 B）与记忆目录，等于每单白烧 3-5 轮。内容一字不变地搬到服务端拼 context
的位置后，模型开局即持有，省的是往返而不是信息。
"""

from __future__ import annotations

import asyncio
import json

from server.common.agent_bridge import AgentRunMeta
from server.platform.paths import PROJECT_ROOT
from server.tender import doc_layer, rules_context


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


def _write_rules(tmp_path):
    rules_dir = tmp_path / "tender"
    rules_dir.mkdir(parents=True)
    (rules_dir / "evalmethod.rules.json").write_text(
        json.dumps({"source_path": "评标方法暂行规定", "rules": [{"rule_id": "tender_evalmethod_001"}]}),
        encoding="utf-8",
    )
    (rules_dir / "regulation.rules.json").write_text(
        json.dumps({"source_path": "招标投标法实施条例", "rules": [{"rule_id": "tender_regulation_003"}]}),
        encoding="utf-8",
    )
    return rules_dir


class TestRulesBlock:
    def test_block_carries_both_statute_files_verbatim(self, tmp_path, monkeypatch):
        rules_dir = _write_rules(tmp_path)
        monkeypatch.setattr(rules_context, "TENDER_RULES_DIR", rules_dir)
        monkeypatch.setattr(rules_context, "TENDER_MEMORY_DIR", tmp_path / "memory-absent")

        block = rules_context.tender_rules_block()

        assert "tender_evalmethod_001" in block
        assert "tender_regulation_003" in block
        assert "evalmethod.rules.json" in block
        assert "regulation.rules.json" in block

    def test_block_tells_the_model_not_to_read_the_files_again(self, tmp_path, monkeypatch):
        rules_dir = _write_rules(tmp_path)
        monkeypatch.setattr(rules_context, "TENDER_RULES_DIR", rules_dir)
        monkeypatch.setattr(rules_context, "TENDER_MEMORY_DIR", tmp_path / "memory-absent")

        block = rules_context.tender_rules_block()

        assert "勿再 Read" in block

    def test_missing_statutes_degrade_to_rule_gap_notice_not_silence(self, tmp_path, monkeypatch):
        """通则层缺失是既有的 manual_review(rule_gap) 降级路径，注入化不得让它静默消失。"""
        monkeypatch.setattr(rules_context, "TENDER_RULES_DIR", tmp_path / "absent")
        monkeypatch.setattr(rules_context, "TENDER_MEMORY_DIR", tmp_path / "memory-absent")

        block = rules_context.tender_rules_block()

        assert "rule_gap" in block

    def test_memory_assets_are_injected_as_auxiliary_evidence(self, tmp_path, monkeypatch):
        rules_dir = _write_rules(tmp_path)
        memory_dir = tmp_path / "memory" / "tender"
        memory_dir.mkdir(parents=True)
        (memory_dir / "case-2026-001.json").write_text(
            json.dumps({"case_id": "case-2026-001", "lesson": "业绩项目经理需与拟派负责人一致"}),
            encoding="utf-8",
        )
        monkeypatch.setattr(rules_context, "TENDER_RULES_DIR", rules_dir)
        monkeypatch.setattr(rules_context, "TENDER_MEMORY_DIR", memory_dir)

        block = rules_context.tender_rules_block()

        assert "case-2026-001" in block

    def test_empty_memory_dir_adds_no_memory_section(self, tmp_path, monkeypatch):
        rules_dir = _write_rules(tmp_path)
        monkeypatch.setattr(rules_context, "TENDER_RULES_DIR", rules_dir)
        monkeypatch.setattr(rules_context, "TENDER_MEMORY_DIR", tmp_path / "memory-absent")

        block = rules_context.tender_rules_block()

        assert "相似案例记忆" not in block


class TestRunnerWiring:
    def _captured_context(self, monkeypatch, runner) -> str:
        calls: dict = {}

        async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
            calls["context"] = opts.get("context")
            return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

        monkeypatch.setattr(runner, "run_command_json", fake_run_command_json)
        monkeypatch.setattr(doc_layer, "get_project_doc", lambda *_a, **_kw: None)
        monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: "底稿正文")
        monkeypatch.setattr(runner, "resolve_project_criteria", lambda *_a, **_kw: (None, None))
        asyncio.run(
            runner.run_tender_evaluation(
                request_id="rid-rules-injection",
                tenant="acme",
                directory_path="/fake/dir",
                project_id="tp-test",
            )
        )
        return calls["context"]

    def test_statutes_land_in_the_injected_context(self, monkeypatch, tmp_path):
        from server.tender import runner

        rules_dir = _write_rules(tmp_path)
        monkeypatch.setattr(rules_context, "TENDER_RULES_DIR", rules_dir)
        monkeypatch.setattr(rules_context, "TENDER_MEMORY_DIR", tmp_path / "memory-absent")

        context = self._captured_context(monkeypatch, runner)

        assert "tender_evalmethod_001" in context
        assert "tender_regulation_003" in context

    def test_statute_block_survives_the_real_context_budget_gate(self, monkeypatch, tmp_path):
        """法规是承重法定依据，预算闸削证据时不得把它削掉（故必须拼在 criteria 之后的尾段）。"""
        from server.tender import context_slim

        rules_dir = _write_rules(tmp_path)
        monkeypatch.setattr(rules_context, "TENDER_RULES_DIR", rules_dir)
        monkeypatch.setattr(rules_context, "TENDER_MEMORY_DIR", tmp_path / "memory-absent")
        monkeypatch.setattr(context_slim, "_preextract_char_budget", lambda *_a, **_kw: 4_000)

        context = (
            "=== OCR/直读底稿（确定性预处理，优先用此文本，无需再 Read 文件）===\n"
            "=== 招标文件底稿 ===\n" + "招标正文" * 3_000 + "\n"
            "\n=== 投标文件（Acme）底稿 ===\n" + "投标正文" * 3_000 + "\n"
            "\n\n=== 已解析评分标准 criteria（版本 v1，S1 直接采用，勿重新解析）===\n{}\n"
            + rules_context.tender_rules_block()
        )

        bounded = context_slim.bound_tender_context(context, model=None)

        assert bounded is not None
        assert len(bounded) < len(context), "预算闸本轮必须真的削过证据段，否则本测试无意义"
        assert "tender_evalmethod_001" in bounded
        assert "tender_regulation_003" in bounded


class TestPromptsNoLongerSelfServe:
    """提示词里对应的 Read 指令必须删除——否则模型仍会白跑那几轮。"""

    def test_command_and_skill_do_not_ask_the_model_to_read_statutes(self):
        for rel in (".claude/commands/tender-evaluate.md", ".claude/skills/tender-eval/SKILL.md"):
            text = (PROJECT_ROOT / rel).read_text(encoding="utf-8")
            assert "knowledge/tender/evalmethod.rules.json" not in text, rel
            assert "knowledge/tender/regulation.rules.json" not in text, rel

    def test_skill_does_not_ask_the_model_to_read_the_memory_dir(self):
        text = (PROJECT_ROOT / ".claude/skills/tender-eval/SKILL.md").read_text(encoding="utf-8")

        assert "knowledge/memory/tender/" not in text
