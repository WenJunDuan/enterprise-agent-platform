"""返工 F1 · 证据层信号必须**穿透 runner 落到结论**（AC2 接线层）。

pass1 REWORK 的主因：``load_evidence_context`` 零调用方、``enforce_manual_review`` 只被自己的
单测调用——``_build_doc_context`` 只取 ``evidence.context``，``warnings`` 与
``force_manual_review`` 落地即丢。四类信号（evidence_unresolved / evidence_all_unresolved /
evidence_index_unavailable / evidence_budget_exhausted）都到不了结论与前端，而死函数上的绿
测试制造了"已接线"的假象。

**本文件只从 ``run_tender_evaluation`` 这一端断言**——测函数本身不算接线证据。
"""

from __future__ import annotations

import asyncio

import pytest

from server.tender import doc_layer, runner

_TENDER = "# 第三章 技术参数\n技术参数偏差表：额定功率不小于 50kW。"
_BID = (
    "# 商务标\n投标报价：壹佰贰拾万元整。报价一览表见附表。\n"
    "# 资格证明\n营业执照副本附后。"
)
_CRITERIA_JSON = (
    '{"eligibility_rules": [{"check": "营业执照", "requirement": "有效期内"}],'
    ' "items": [{"item": "报价", "max": 40}, {"item": "现场答辩表现", "max": 10}]}'
)


def _fake_meta(request_id: str):
    from server.common.agent_bridge import AgentRunMeta

    return AgentRunMeta(
        request_id=request_id,
        conversation_id="c",
        claude_session_id="s",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="common/audit-result.schema.json",
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


@pytest.fixture
def wired(monkeypatch):
    """两层 ready 的读层 + 记录模型/inline OCR 是否被调用的探针。"""
    calls: dict[str, object] = {"model": 0, "inline": 0, "context": None}

    monkeypatch.setenv("TENDER_SLIM_CONTEXT", "1")
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "1")

    async def fake_wait(*_a, **_kw):
        return "terminal"

    monkeypatch.setattr(doc_layer, "wait_doc_layer_ready", fake_wait)

    async def fake_run_command(_cmd, *_a, **opts):
        calls["model"] = int(calls["model"]) + 1
        calls["context"] = opts.get("context")
        return {"verdict": "approved", "extracted_data": {"scoring": [{"item": "报价"}]}}, (
            _fake_meta(opts["request_id"])
        )

    monkeypatch.setattr(runner, "run_command_json", fake_run_command)

    def fake_inline(*_a, **_kw):
        calls["inline"] = int(calls["inline"]) + 1
        return "inline 重跑产出的整目录底稿"

    monkeypatch.setattr(runner, "ocr_preprocess_block", fake_inline)
    return calls


def _patch_docs(monkeypatch, *, bid_text: str, criteria: str | None = _CRITERIA_JSON):
    monkeypatch.setattr(
        doc_layer,
        "get_project_doc",
        lambda pid, tenant: {
            "ocr_status": "ready",
            "ocr_text": _TENDER,
            "criteria": criteria,
        },
    )
    monkeypatch.setattr(
        doc_layer,
        "get_bid_doc",
        lambda pid, bid, tenant: {
            "bid_id": bid,
            "ocr_status": "ready",
            "ocr_text": bid_text,
            "bidder_name": "甲公司",
        },
    )


def _run():
    return asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-wire",
            tenant="t1",
            directory_path="/fake/dir",
            project_id="tp-1",
            bid_id="bid-1",
        )
    )


def _warnings(payload) -> list[dict]:
    return payload["extracted_data"]["ocr_warnings"]


def test_evidence_unresolved_warning_reaches_final_payload(wired, monkeypatch):
    """F1 核心：某项检索不到证据时，该信号必须出现在**最终结论**里，不能只活在日志。"""
    _patch_docs(monkeypatch, bid_text=_BID)

    payload, _meta = _run()

    statuses = [w["status"] for w in _warnings(payload)]
    assert "evidence_unresolved" in statuses, f"证据信号没穿透到结论：{statuses}"
    unresolved = next(w for w in _warnings(payload) if w["status"] == "evidence_unresolved")
    assert "现场答辩表现" in str(unresolved["message"])
    assert unresolved["queries"], "必须带出实际用过的查询串"


def test_逐项注入量留痕穿透到最终结论(wired, monkeypatch):
    """AC15：证据"变薄"没有专属故障码——它既不是 unresolved 也不是 truncated。

    hit-stop 的边界质量依赖邻项命中的疏密（邻项 unresolved 则边界后移、噪音命中制造伪边界
    提前截断、末项之后无停止点），三种都无痕。唯一能让它们被看见的量纲是**逐项实际注入了
    多少 token**，故它必须和其它证据信号一样穿透到结论，而不是只活在服务端日志里。
    """
    _patch_docs(monkeypatch, bid_text=_BID)

    payload, _meta = _run()

    volume = next(
        (w for w in _warnings(payload) if w["status"] == "evidence_volume"), None
    )
    assert volume is not None, f"逐项注入量没穿透到结论：{[w['status'] for w in _warnings(payload)]}"
    tokens = {row["item"]: row["tokens"] for row in volume["items"]}
    assert tokens["报价"] > 0, f"命中项的注入量必须是实测值：{tokens}"
    assert tokens["现场答辩表现"] == 0, f"零命中项要显式记 0，不能从清单里消失：{tokens}"


def test_evidence_context_actually_injected(wired, monkeypatch):
    """接线的另一半：注入给模型的确实是检索到的证据，不是整份投标底稿。"""
    noise = "与任何评分项都无关的大段附件正文。"
    _patch_docs(monkeypatch, bid_text=_BID + "\n" + noise * 500)

    _run()

    context = str(wired["context"])
    assert "按评分项检索到的证据片段" in context
    assert noise * 50 not in context, "无关正文不该整份注入"


def test_force_manual_review_short_circuits_the_model(wired, monkeypatch):
    """F7/F1：证据层不可用时**不出分也不发 prompt**，更不能回落 inline 重跑整目录。"""
    _patch_docs(monkeypatch, bid_text="   ")

    payload, meta = _run()

    assert wired["model"] == 0, "不得把注定失败/无证据的 prompt 发出去"
    assert wired["inline"] == 0, "不得回落 inline OCR 重跑整目录（F7 明令禁止）"
    assert payload["verdict"] == "manual_review"
    assert payload["manual_review_reason"] == "rule_gap"
    assert payload["extracted_data"]["scoring"] == [], "不得带着分数出结论"
    statuses = [w["status"] for w in _warnings(payload)]
    assert "evidence_index_unavailable" in statuses
    assert meta.request_id == "rid-wire"


def test_all_unresolved_also_stops_at_manual_review(wired, monkeypatch):
    """F4：索引建成而检索全空是结构性异常，归宿是 manual_review，不是回落整份注入。"""
    _patch_docs(
        monkeypatch,
        bid_text="# 附件\n本份材料与任何评分项都不相干。",
        criteria='{"items": [{"item": "现场答辩表现", "max": 10}]}',
    )

    payload, _meta = _run()

    assert wired["model"] == 0
    assert payload["verdict"] == "manual_review"
    statuses = [w["status"] for w in _warnings(payload)]
    assert "evidence_all_unresolved" in statuses


def test_budget_exhausted_reaches_the_conclusion(wired, monkeypatch):
    """预算不可达同样必须落结论（此前该 warning 也被丢弃）。"""
    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", "100")
    _patch_docs(monkeypatch, bid_text=_BID)

    payload, _meta = _run()

    assert payload["verdict"] == "manual_review"
    statuses = [w["status"] for w in _warnings(payload)]
    assert "evidence_budget_exhausted" in statuses


def test_no_criteria_still_evaluates_normally(wired, monkeypatch):
    """反回归：没有 criteria 时证据层不适用，评标照常进行（不得被误判成降级）。"""
    _patch_docs(monkeypatch, bid_text=_BID, criteria=None)

    payload, _meta = _run()

    assert wired["model"] == 1, "无 criteria 是正常路径，必须照常评"
    assert payload["verdict"] == "approved"
