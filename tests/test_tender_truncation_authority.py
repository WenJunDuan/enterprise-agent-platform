"""(d) 整份注入路径一旦截断就**没有评分权威性**——归宿是 manual_review，不是照常出分。

``evidence_context`` 模块 docstring 立的论点是「错评分比失败危险得多」，并为此把三种证据层
内部失败（索引建不出 / 检索全空 / 预算不可达）导向 ``build_manual_review_result``。但**最危险
的那条路径没被覆盖**：证据层未启用 → 整份底稿注入 → 超预算截断 → 照常出分。2026-08-18 那份
9/11 项 ``evidence_unresolved`` 的错误结论正是它的产物（784,903 字节截到 178,641，砍掉 77%）。

**判据刻意不含任何百分比阈值**：任何百分比都是对某一份文档的标定，换一份标书就失准（用户
明令禁止按其标书拟合）。这里用的是物理级判据——整份注入模式下 ``bound_draft`` 一旦触发
（``original_bytes > limit``），被截内容对评分的影响即不可知，自动评分随即失去权威性。

**不得误伤证据层路径**：那条路的注入量由 ``injection_budget`` 的闭式账目构造保证，
``scaffold + criteria + Σ(per_item) + margin ≤ 有效上限`` 恒成立，天然不会撞字节闸；
把闸做成"任何截断都转人工"会连它一起判死。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from server.common.agent_bridge import AgentRunMeta
from server.tender import doc_layer, runner

_TENDER = "# 第三章 技术参数\n技术参数偏差表：额定功率不小于 50kW。"
_BID = (
    "# 商务标\n投标报价：壹佰贰拾万元整。报价一览表见附表。\n"
    "# 资格证明\n营业执照副本附后。"
)
_CRITERIA = {
    "eligibility_rules": [{"check": "营业执照", "requirement": "有效期内"}],
    "items": [{"item": "报价", "max": 40}],
}


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


@pytest.fixture
def probes(monkeypatch):
    """记录模型 / inline OCR 是否被调用的探针（"不出分"要靠"没发 prompt"来证）。"""
    calls: dict[str, object] = {"model": 0, "inline": 0}

    monkeypatch.setenv("TENDER_SLIM_CONTEXT", "1")
    monkeypatch.setenv("TENDER_READ_DOC_LAYER", "1")

    async def fake_wait(*_a, **_kw):
        return "terminal"

    monkeypatch.setattr(doc_layer, "wait_doc_layer_ready", fake_wait)

    async def fake_run_command(_cmd, *_a, **opts):
        calls["model"] = int(calls["model"]) + 1
        return {
            "verdict": "approved",
            "extracted_data": {"scoring": [{"item": "报价", "score": 40}]},
        }, _fake_meta(opts["request_id"])

    monkeypatch.setattr(runner, "run_command_json", fake_run_command)
    return calls


def _patch_docs(monkeypatch, *, criteria: str | None, bid_text: str = _BID) -> None:
    """两层预热 ready 的读层（criteria 为 None 时证据层不适用 → 整份注入）。"""
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


def _use_inline_ocr(monkeypatch, probes, text: str) -> None:
    """强制走 inline_ocr 回落（2026-08-14/15 事故的原路径）：doc 层不出底稿。"""
    monkeypatch.setattr(doc_layer, "load_doc_layer_context", lambda *_a, **_kw: None)
    monkeypatch.setattr(doc_layer, "load_doc_layer_context_slim", lambda *_a, **_kw: None)
    monkeypatch.setattr(doc_layer, "get_project_doc", lambda *_a, **_kw: None)
    monkeypatch.setattr(doc_layer, "get_bid_doc", lambda *_a, **_kw: None)

    def fake_inline(*_a, **_kw):
        probes["inline"] = int(probes["inline"]) + 1
        return text

    monkeypatch.setattr(runner, "ocr_preprocess_block", fake_inline)


def _run(request_id: str, *, bid_id: str | None = "bid-1"):
    return asyncio.run(
        runner.run_tender_evaluation(
            request_id=request_id,
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-1",
            bid_id=bid_id,
        )
    )


def _warnings(payload) -> list[dict]:
    return payload["extracted_data"]["ocr_warnings"]


def _oversized_bid() -> str:
    return _BID + "\n" + "投标材料明细，本段与评分项无关的附件正文。" * 200


# ── 整份注入 + 截断 ⇒ 不出分 ────────────────────────────────────────────────


def test_整份注入被截断时不出分而是转人工(probes, monkeypatch):
    """核心：这条路径产出的分数没有权威性，只能停在人工复核。"""
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "600")
    _patch_docs(monkeypatch, criteria=None, bid_text=_oversized_bid())

    payload, _meta = _run("rid-trunc-manual")

    assert probes["model"] == 0, "被截断的底稿注定证据残缺，不得把这样的 prompt 发出去"
    assert payload["verdict"] == "manual_review"
    assert payload["manual_review_reason"] == "rule_gap"
    assert payload["extracted_data"]["scoring"] == [], "不得带着分数出结论"


def test_转人工的结论带截断账目与解法指引(probes, monkeypatch):
    """人工复核的人要能一眼看出为什么停、以及怎么让它不再停。"""
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "600")
    _patch_docs(monkeypatch, criteria=None, bid_text=_oversized_bid())

    payload, _meta = _run("rid-trunc-account")

    account = next(w for w in _warnings(payload) if w["status"] == "draft_truncated")
    assert account["limit_bytes"] == 600
    assert int(account["original_bytes"]) > 600
    message = str(account["message"])
    assert "人工复核" in message, f"要说清本次的归宿：{message}"
    assert "criteria" in message, f"要给出解法（criteria 就绪后走按项检索）：{message}"
    # 证据层未启用那条痕迹（(c) 已补）必须同时在场，否则读者不知道为何会走整份注入。
    assert "evidence_layer_skipped" in [str(w["status"]) for w in _warnings(payload)]


def test_转人工的结论仍然归档可回查(probes, monkeypatch):
    """短路不能变成"任务 completed 却没有结论可看"——那是又一条静默路径。

    前端取结论走的是 ``get_result_payload_by_request_id``（``routes/tender/tasks.py``），
    故判据必须是"按 request_id 真能取回来"，而不是"返回值里有个 result_file 字段"。
    """
    from server.stores.result_store import get_result_payload_by_request_id

    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "600")
    _patch_docs(monkeypatch, criteria=None, bid_text=_oversized_bid())

    _payload, meta = _run("rid-trunc-archived")

    assert meta.result_file, "结论必须落文件，前端与运维都按它回查"
    archived = get_result_payload_by_request_id("rid-trunc-archived", "acme")
    assert archived is not None, "转人工的结论没归档 = 任务显示完成却没有结论可看"
    assert archived["response"]["verdict"] == "manual_review"


def test_inline_ocr回落路径同样受管(probes, monkeypatch):
    """2026-08-14/15 事故的原路径：预热底稿用不上 → inline 重跑整目录 → 超预算截断。"""
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "600")
    _use_inline_ocr(monkeypatch, probes, "招" * 400)

    payload, _meta = _run("rid-trunc-inline")

    assert probes["inline"] == 1, "前置条件：本用例必须真的走 inline 回落"
    assert probes["model"] == 0
    assert payload["verdict"] == "manual_review"


def test_判据是物理触发而不是百分比阈值(probes, monkeypatch):
    """防拟合硬要求：超 1 个字节与超 77% 同样使被截内容不可知，判据里不得有百分比。

    任何百分比阈值都是对某一份文档的标定；用户会换文档，标定即失效。
    """
    draft = "招" * 400  # 1,200 字节
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", str(len(draft.encode("utf-8")) - 1))
    _use_inline_ocr(monkeypatch, probes, draft)

    payload, _meta = _run("rid-trunc-one-byte")

    assert payload["verdict"] == "manual_review", "只超 1 字节也必须停——判据是物理触发"
    account = next(w for w in _warnings(payload) if w["status"] == "draft_truncated")
    assert int(account["original_bytes"]) - int(account["limit_bytes"]) == 1


def test_未超预算的整份注入照常出分(probes, monkeypatch):
    """对照组：闸没触发就不许改变结论——本次治理不是"整份注入一律不许评"。"""
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "100000")
    _patch_docs(monkeypatch, criteria=None)

    payload, _meta = _run("rid-trunc-fits")

    assert probes["model"] == 1
    assert payload["verdict"] == "approved"
    assert payload["extracted_data"]["scoring"], "正常路径必须照常出分"


# ── 不得误伤证据层路径 ──────────────────────────────────────────────────────


def test_证据层路径不被截断闸误伤(probes, monkeypatch):
    """证据层注入量由闭式账目保证，不该因字节闸触发而失去评分权威性。

    把字节上限压到远小于证据块的体量，模拟"闸误触发"这一最坏情形：即便如此，
    走按评分项检索的这条路仍必须照常出分——它的证据是**选出来的**，不是被腰斩的整份底稿。
    """
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "300")
    _patch_docs(monkeypatch, criteria=json.dumps(_CRITERIA), bid_text=_oversized_bid())

    payload, _meta = _run("rid-trunc-evidence-path")

    assert probes["model"] == 1, "证据层路径不得被截断闸判死"
    assert payload["verdict"] == "approved"
    assert payload["extracted_data"]["scoring"], "证据层路径必须照常出分"


def test_证据层路径的截断留痕不谎称已停止评分(probes, monkeypatch):
    """痕迹仍要有（(c) 的要求），但文案不得说"已转人工"——那与实际发生的事不符。"""
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "300")
    _patch_docs(monkeypatch, criteria=json.dumps(_CRITERIA), bid_text=_oversized_bid())

    payload, _meta = _run("rid-trunc-evidence-message")

    account = next(w for w in _warnings(payload) if w["status"] == "draft_truncated")
    assert "不出分" not in str(account["message"])
    assert "证据缺失" in str(account["message"])
