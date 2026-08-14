"""Bug 1（2026-08-14 生产事故）：tender 注入 OCR 底稿必须过字节预算闸。

事故链：云 OCR 写超时 → runner 降级 ``inline_ocr`` → ``ocr_preprocess_block(directory_path)``
把整个 case 目录的 OCR 全文无上限注入 → 内网 DeepSeek Flash ``Prompt is too long``。
闸放在 tender 调用侧（``server/ocr/`` 禁改），两条底稿来源（doc_layer_reuse / inline_ocr）同过。
"""

from __future__ import annotations

import asyncio
import logging

from server.common.agent_bridge import AgentRunMeta
from server.tender import doc_layer

# 用户可见的截断标记前缀（契约：模型能看见"这里被截了"，评分项据此走证据缺失规则）
TRUNCATION_NOTICE_PREFIX = "【底稿超出上下文预算，已截断"


def _fake_meta(request_id: str) -> AgentRunMeta:
    return AgentRunMeta(
        request_id=request_id,
        conversation_id="conv-test",
        claude_session_id="sess-test",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="tender/audit-result.schema.json",
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def _run_evaluation(monkeypatch, runner, *, request_id: str) -> dict:
    """跑一次评标，返回 run_command_json 实际收到的 kwargs（context / evidence_source）。"""
    calls: dict = {}

    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        calls.update(opts)
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(runner, "run_command_json", fake_run_command_json)
    monkeypatch.setattr(runner, "resolve_project_criteria", lambda *_a, **_kw: (None, None))
    asyncio.run(
        runner.run_tender_evaluation(
            request_id=request_id,
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-test",
        )
    )
    return calls


def _kept_material(context: str) -> str:
    """取注入上下文里"截断标记之前的底稿本体"（标记自带前导换行，不算底稿内容）。"""
    body = context.split(TRUNCATION_NOTICE_PREFIX)[0]
    return body.split("===\n", maxsplit=1)[1].removesuffix("\n")


def _use_inline_ocr(monkeypatch, runner, text: str) -> None:
    """强制走 inline_ocr 降级路径（事故路径）：doc 层不出底稿。"""
    monkeypatch.setattr(doc_layer, "load_doc_layer_context", lambda *_a, **_kw: None)
    monkeypatch.setattr(doc_layer, "load_doc_layer_context_slim", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: text)


def test_inline_ocr_block_over_budget_is_truncated_with_visible_marker(monkeypatch):
    from server.tender import runner

    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "300")
    # 每个汉字 3 字节：150 字 = 450 字节 > 300 字节上限
    _use_inline_ocr(monkeypatch, runner, "招" * 150)

    calls = _run_evaluation(monkeypatch, runner, request_id="rid-budget-inline")

    context = calls["context"]
    assert TRUNCATION_NOTICE_PREFIX in context
    kept = _kept_material(context)
    assert len(kept.encode("utf-8")) <= 300
    # 保留的是**前** N 字节，不是随机片段
    assert kept == "招" * 100


def test_truncation_cuts_on_utf8_boundary(monkeypatch):
    """上限落在多字节字符中间时不得截出半个字符（截断产物必须严格 UTF-8 可解码）。"""
    from server.tender import runner

    # 100 不是 3 的整数倍 → 第 34 个汉字被上限劈开
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "100")
    _use_inline_ocr(monkeypatch, runner, "标" * 60)

    calls = _run_evaluation(monkeypatch, runner, request_id="rid-budget-utf8")

    raw = _kept_material(calls["context"]).encode("utf-8")
    # 33 个完整汉字 = 99 字节；第 34 个字被上限劈开，必须整字丢弃而不是留半个
    assert len(raw) == 99
    # 严格解码：出现半个字符会抛 UnicodeDecodeError
    assert raw.decode("utf-8") == "标" * 33


def test_truncation_emits_structured_warning_log(monkeypatch, caplog):
    from server.tender import runner

    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "300")
    _use_inline_ocr(monkeypatch, runner, "招" * 150)

    with caplog.at_level(logging.WARNING, logger="server.tender.runner"):
        _run_evaluation(monkeypatch, runner, request_id="rid-budget-log")

    records = [r for r in caplog.records if r.getMessage() == "tender_context_truncated"]
    assert len(records) == 1
    record = records[0]
    assert record.request_id == "rid-budget-log"
    assert record.original_bytes == 450
    assert record.kept_bytes == 300
    assert record.limit_bytes == 300


def test_doc_layer_reuse_path_is_also_bounded(monkeypatch):
    """预热底稿理论上也可能超大 → 复用路径同样过闸。"""
    from server.tender import runner

    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "300")
    monkeypatch.setattr(doc_layer, "load_doc_layer_context", lambda *_a, **_kw: "标" * 150)
    monkeypatch.setattr(doc_layer, "load_doc_layer_context_slim", lambda *_a, **_kw: "标" * 150)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("doc 层已出底稿时不应回落 inline OCR")

    monkeypatch.setattr(runner, "ocr_preprocess_block", fail_if_called)

    calls = _run_evaluation(monkeypatch, runner, request_id="rid-budget-doc-layer")

    assert TRUNCATION_NOTICE_PREFIX in calls["context"]


def test_evidence_source_matches_the_bounded_block(monkeypatch):
    """evidence_source 与模型看到的底稿必须同源，否则出处回查会指向未注入内容。"""
    from server.tender import runner

    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "300")
    _use_inline_ocr(monkeypatch, runner, "招" * 150)

    calls = _run_evaluation(monkeypatch, runner, request_id="rid-budget-evidence")

    assert calls["evidence_source"] in calls["context"]
    assert TRUNCATION_NOTICE_PREFIX in calls["evidence_source"]


def test_under_budget_block_is_passed_through_unchanged(monkeypatch, caplog):
    """对照：不超限时零改动、零日志。"""
    from server.tender import runner

    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "300")
    _use_inline_ocr(monkeypatch, runner, "招" * 50)

    with caplog.at_level(logging.WARNING, logger="server.tender.runner"):
        calls = _run_evaluation(monkeypatch, runner, request_id="rid-budget-fits")

    assert calls["evidence_source"] == "招" * 50
    assert TRUNCATION_NOTICE_PREFIX not in calls["context"]
    assert not [r for r in caplog.records if r.getMessage() == "tender_context_truncated"]


def test_default_budget_bounds_a_whole_directory_dump(monkeypatch):
    """未配 env 时默认值生效——事故当天正是"没人配上限"。"""
    from server.tender import runner

    monkeypatch.delenv("TENDER_CONTEXT_MAX_BYTES", raising=False)
    _use_inline_ocr(monkeypatch, runner, "招" * 200_000)  # 600 KB 整目录全文

    calls = _run_evaluation(monkeypatch, runner, request_id="rid-budget-default")

    assert TRUNCATION_NOTICE_PREFIX in calls["evidence_source"]
    assert len(calls["evidence_source"].encode("utf-8")) < 100_000
