"""Tests for the tender evaluation read layer in server.tender.runner.run_tender_evaluation.

TDD: tests written before implementation.

D1 T2: the evaluation core (incl. the read layer) moved from
``server.routes.tender_worker._run_evaluation`` to
``server.tender.runner.run_tender_evaluation`` (design round1 F1 + round2 F5 方案 i).
Assertions/coverage unchanged from the pre-move version — only the import target and the
public function name follow the code to its new home.

The read layer: if TENDER_READ_DOC_LAYER=1 (default), run_tender_evaluation should
try to pull ocr_text from tender_doc_store before calling ocr_preprocess_block.

Cases:
1. tender_project_doc ready + all bid docs ready → use doc layer text, skip ocr_preprocess_block.
2. tender_project_doc missing/not-ready → fall back to ocr_preprocess_block.
3. TENDER_READ_DOC_LAYER=0 → always fall back to ocr_preprocess_block.
"""

from __future__ import annotations

import asyncio

from server.common.agent_bridge import AgentRunMeta
from server.tender import doc_layer  # noqa: E402  (H3: 读层拆出后测试改打这里)


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


def _make_fake_run_command(calls: dict):
    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        calls["context"] = opts.get("context")
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    return fake_run_command_json


def test_read_layer_uses_doc_store_when_ready(monkeypatch):
    """When doc layer is enabled and docs are ready, ocr_preprocess_block is NOT called."""
    from server.tender import runner

    calls: dict = {}

    monkeypatch.setattr(runner, "run_command_json", _make_fake_run_command(calls))

    # Provide ready doc store data
    monkeypatch.setattr(
        doc_layer,
        "load_doc_layer_context",
        lambda *_a, **_kw: "=== DOC LAYER TEXT ===",
    )
    # ocr_preprocess_block should NOT be called
    preprocess_called = []
    monkeypatch.setattr(
        runner,
        "ocr_preprocess_block",
        lambda *a, **kw: preprocess_called.append(True) or "fallback",
    )
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "1")

    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-layer-ready",
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-test",
        )
    )

    assert not preprocess_called, "ocr_preprocess_block must not be called when doc layer is ready"
    assert calls["context"] is not None
    assert "DOC LAYER TEXT" in calls["context"]


def test_read_layer_fallback_when_doc_missing(monkeypatch):
    """When doc layer returns None (missing/not-ready), ocr_preprocess_block is called."""
    from server.tender import runner

    calls: dict = {}
    monkeypatch.setattr(runner, "run_command_json", _make_fake_run_command(calls))

    # Doc layer returns None (no data available)
    monkeypatch.setattr(
        doc_layer,
        "load_doc_layer_context",
        lambda *_a, **_kw: None,
    )

    preprocess_called = []

    def fake_preprocess(directory_path, *, purpose=None):
        preprocess_called.append(directory_path)
        return "fallback OCR text"

    monkeypatch.setattr(runner, "ocr_preprocess_block", fake_preprocess)
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "1")

    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-layer-missing",
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-missing",
        )
    )

    assert preprocess_called, "ocr_preprocess_block must be called when doc layer has no data"


def test_read_layer_disabled_always_falls_back(monkeypatch):
    """When TENDER_READ_DOC_LAYER=0, ocr_preprocess_block is always called."""
    from server.tender import runner

    calls: dict = {}
    monkeypatch.setattr(runner, "run_command_json", _make_fake_run_command(calls))

    load_called = []
    monkeypatch.setattr(
        doc_layer,
        "load_doc_layer_context",
        lambda *_a, **_kw: load_called.append(True) or "doc layer",
    )

    preprocess_called = []

    def fake_preprocess(directory_path, *, purpose=None):
        preprocess_called.append(directory_path)
        return "fallback OCR text"

    monkeypatch.setattr(runner, "ocr_preprocess_block", fake_preprocess)
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "0")

    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-layer-disabled",
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-disabled",
        )
    )

    # When disabled, doc layer load must NOT be called, fallback must be called
    assert not load_called, (
        "doc_layer.load_doc_layer_context must not be called when layer disabled"
    )
    assert preprocess_called, "ocr_preprocess_block must be called when layer disabled"


def test_read_layer_no_project_id_falls_back(monkeypatch):
    """When project_id is None, doc layer is skipped, ocr_preprocess_block is called."""
    from server.tender import runner

    calls: dict = {}
    monkeypatch.setattr(runner, "run_command_json", _make_fake_run_command(calls))

    load_called = []
    monkeypatch.setattr(
        doc_layer,
        "load_doc_layer_context",
        lambda *_a, **_kw: load_called.append(True) or "doc layer",
    )

    preprocess_called = []

    def fake_preprocess(directory_path, *, purpose=None):
        preprocess_called.append(directory_path)
        return "fallback OCR text"

    monkeypatch.setattr(runner, "ocr_preprocess_block", fake_preprocess)
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "1")

    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-no-project",
            tenant="acme",
            directory_path="/fake/dir",
            project_id=None,  # no project_id → skip doc layer
        )
    )

    assert not load_called, (
        "doc_layer.load_doc_layer_context must not be called when project_id is None"
    )
    assert preprocess_called


# ── D1 T2 接缝：TENDER_OCR_PURPOSE 挪家 ────────────────────────────────────────


def test_tender_ocr_purpose_relocated_and_reexported():
    """TENDER_OCR_PURPOSE 的权威定义现在是 server.tender.runner（方案 i 接缝①）；
    server.tender.doc_pipeline 只是 re-export 同一个对象，不再自己定义，
    routes/tender.py 既有的 import 引用点因此不用改。"""
    import server.tender.doc_pipeline as pipeline
    from server.tender import runner

    assert pipeline.TENDER_OCR_PURPOSE is runner.TENDER_OCR_PURPOSE
    assert "评分标准" in runner.TENDER_OCR_PURPOSE


# ── D1 T3：TENDER_EVAL_MODEL env 覆盖（per-call model 优先，env 兜底） ─────────────


def test_model_kwarg_omitted_when_unset(monkeypatch):
    """model 参数未传且 TENDER_EVAL_MODEL 未设 → 不传 model kwargs（零行为变更，生产路径）。"""
    from server.tender import runner

    monkeypatch.delenv("TENDER_EVAL_MODEL", raising=False)
    calls: dict = {}
    monkeypatch.setattr(runner, "run_command_json", _make_fake_run_command(calls))
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: "fallback")

    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-no-override", tenant="acme", directory_path="/fake/dir"
        )
    )

    assert "model" not in calls


def test_explicit_model_kwarg_takes_priority_over_env(monkeypatch):
    """显式 model 参数优先于 TENDER_EVAL_MODEL env（CLI --model 场景）。"""
    from server.tender import runner

    monkeypatch.setenv("TENDER_EVAL_MODEL", "env-model")
    calls: dict = {}

    async def fake_run(command_name, *arguments, schema_name, **opts):
        calls["model"] = opts.get("model")
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(runner, "run_command_json", fake_run)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: "fallback")

    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-explicit",
            tenant="acme",
            directory_path="/fake/dir",
            model="cli-model",
        )
    )

    assert calls["model"] == "cli-model"


def test_env_model_used_when_no_explicit_override(monkeypatch):
    """无显式 model 参数、TENDER_EVAL_MODEL 已设 → 落到 env 值（生产 tender_worker 从不设此
    env，故此路径只在部署机 eval 场景生效，零行为变更承诺仍成立）。"""
    from server.tender import runner

    monkeypatch.setenv("TENDER_EVAL_MODEL", "deepseek-v4-pro")
    calls: dict = {}

    async def fake_run(command_name, *arguments, schema_name, **opts):
        calls["model"] = opts.get("model")
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(runner, "run_command_json", fake_run)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: "fallback")

    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-env-fallback", tenant="acme", directory_path="/fake/dir"
        )
    )

    assert calls["model"] == "deepseek-v4-pro"


# ── D1 M1（返工）：契约重试次数是真实字段，不是 getattr 兜底 ──────────────────────
#
# AgentRunMeta 是 @dataclass(slots=True)——slots 类不能被外部动态挂属性，之前
# eval.py 用 getattr(meta, "retry_count", None) 读永远只会读到 None（外部 setattr
# 也会直接 AttributeError）。修法：AgentRunMeta 追加带默认值的尾部字段
# retry_count: int = 0；run_tender_evaluation 的契约重试循环在成功 attempt 后
# 写 meta.retry_count = attempt（该 attempt 就是这次调用实际重试了几次），
# 供 eval 回归闸捕捉「D8 底稿瘦身导致 JSON 更易写坏→重试变多」这类回归信号
# （design 评分维度表「运维指标」，S7 配套问题②）。


def test_run_tender_evaluation_retry_count_zero_on_first_try_success(monkeypatch):
    """一次成功（attempt=0，未重试）→ meta.retry_count == 0。"""
    from server.tender import runner

    async def fake_run(command_name, *arguments, schema_name, **opts):
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(runner, "run_command_json", fake_run)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: "fallback")

    _payload, meta = asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-retry-zero", tenant="acme", directory_path="/fake/dir"
        )
    )

    assert meta.retry_count == 0


def test_run_tender_evaluation_retry_count_after_two_failures(monkeypatch):
    """前 2 次抛契约异常，第 3 次（attempt=2）成功 → meta.retry_count == 2。"""
    from server.tender import runner

    monkeypatch.setattr(runner, "TENDER_CONTRACT_MAX_RETRY", 2)
    attempts = {"n": 0}

    async def flaky_run(command_name, *arguments, schema_name, **opts):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise RuntimeError("契约校验失败：半截 JSON")
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(runner, "run_command_json", flaky_run)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: "fallback")

    _payload, meta = asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-retry-two", tenant="acme", directory_path="/fake/dir"
        )
    )

    assert meta.retry_count == 2
    assert attempts["n"] == 3
