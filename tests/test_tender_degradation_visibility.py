"""(c) 降级不许静默：两条零信号分支必须产出**用户看得见**的痕迹（KD4/AC2 守卫）。

2026-08-18 生产事故根因链的中间两环：criteria 抽取失败 → 证据层跳过（``build_evidence_context``
在无可检索项时 ``return EvidenceContext()``，零 warning 零日志）→ 静默退回整份注入 → 底稿
784,903 字节截到 178,641（砍 77%，只写运维日志 ``tender_context_truncated`` 与模型上下文里的
``TRUNCATION_NOTICE``）。用户拿到 9/11 项 ``evidence_unresolved`` 的结论，却完全看不到"底稿被
砍了 77%"这件事，反查根因花掉一整天。

design KD4 立的原则是「**降级可以发生，但必须留下用户看得见的痕迹**」，这两条是漏网的。

守卫口径与 ``test_tender_evidence_wiring.py`` 同款：**只从 ``run_tender_evaluation`` 这一端
断言**——降级信号能否被用户看见，取决于它有没有落进 ``extracted_data.ocr_warnings``（结论
落盘字段，前端据此渲染）；测私有函数不算可见性证据。
"""

from __future__ import annotations

import asyncio

import pytest

from server.common.agent_bridge import AgentRunMeta
from server.tender import doc_layer, runner

_TENDER = "# 第三章 技术参数\n技术参数偏差表：额定功率不小于 50kW。"
_BID = (
    "# 商务标\n投标报价：壹佰贰拾万元整。报价一览表见附表。\n"
    "# 资格证明\n营业执照副本附后。"
)
_CRITERIA_JSON = (
    '{"eligibility_rules": [{"check": "营业执照", "requirement": "有效期内"}],'
    ' "items": [{"item": "报价", "max": 40}]}'
)


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
def evaluated(monkeypatch):
    """两层预热 ready 的读层 + 记录模型是否被调用、收到什么上下文的探针。"""
    calls: dict[str, object] = {"model": 0, "context": None}

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

    def fail_if_called(*_a, **_kw):
        raise AssertionError("预热底稿在场时不应回落 inline OCR")

    monkeypatch.setattr(runner, "ocr_preprocess_block", fail_if_called)
    return calls


def _patch_docs(monkeypatch, *, criteria: str | None, bid_text: str = _BID) -> None:
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


def _run(request_id: str = "rid-degrade"):
    return asyncio.run(
        runner.run_tender_evaluation(
            request_id=request_id,
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-1",
            bid_id="bid-1",
        )
    )


def _warnings(payload) -> list[dict]:
    return payload["extracted_data"]["ocr_warnings"]


def _statuses(payload) -> list[str]:
    return [str(w["status"]) for w in _warnings(payload)]


# ── (c)-1 证据层未启用 ────────────────────────────────────────────────────────


def test_criteria缺失导致证据层未启用时结论必须留痕(evaluated, monkeypatch):
    """事故第一环：criteria 抽不出来 → 证据层跳过 → 整份注入，全程零信号。

    "本路径不适用"是真的（评标会自行 S1 解析），但它同时意味着**注入形态变了**——
    从按评分项检索的片段变回整份底稿，从而重新暴露在截断风险下。用户有权看见这次换了路。
    """
    _patch_docs(monkeypatch, criteria=None)

    payload, _meta = _run()

    assert evaluated["model"] == 1, "无 criteria 是正常路径，评标必须照常进行"
    assert "evidence_layer_skipped" in _statuses(payload), (
        f"证据层跳过没有留下任何用户可见痕迹：{_statuses(payload)}"
    )


def test_criteria存在但无可检索项同样留痕(evaluated, monkeypatch):
    """另一半形态：criteria 在，但 items 缺项名 / 全空——同样检索不了，同样必须留痕。"""
    _patch_docs(monkeypatch, criteria='{"items": [{"max": 10}]}')

    payload, _meta = _run("rid-degrade-empty-items")

    assert "evidence_layer_skipped" in _statuses(payload), (
        f"criteria 不可用时证据层跳过没有留痕：{_statuses(payload)}"
    )


def test_证据层跳过的留痕要写清改用了什么以及后果(evaluated, monkeypatch):
    """痕迹不能只是一个状态码：用户要能读懂"没走按项检索、改成整份底稿"及其代价。"""
    _patch_docs(monkeypatch, criteria=None)

    payload, _meta = _run("rid-degrade-message")

    skipped = next(w for w in _warnings(payload) if w["status"] == "evidence_layer_skipped")
    message = str(skipped["message"])
    assert "评分项" in message, f"要说清没走的是什么：{message}"
    assert "整份底稿" in message, f"要说清改用了什么：{message}"
    assert "截断" in message, f"要说清后果（整份注入会被截）：{message}"


# ── (c)-2 截断账目 ───────────────────────────────────────────────────────────


def _oversized_bid() -> str:
    """构造一份必然超出小额预算的投标底稿（合成语料，非真实标书）。"""
    return _BID + "\n" + "投标材料明细，本段与评分项无关的附件正文。" * 200


def test_底稿截断的字节账必须落到结论(evaluated, monkeypatch):
    """事故第二环：截断只发运维日志 + 模型上下文标记，结论与前端一个字都没有。

    落盘的三个数（原始 / 实际注入 / 预算上限）是用户判断"这份结论能不能用"的唯一依据——
    生产实测 784,903→178,641 砍掉 77%，而用户在界面上看到的是一份"正常"的评分结论。
    """
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "600")
    _patch_docs(monkeypatch, criteria=None, bid_text=_oversized_bid())

    payload, _meta = _run("rid-degrade-truncated")

    truncated = [w for w in _warnings(payload) if w["status"] == "draft_truncated"]
    assert truncated, f"底稿被截断却没有任何用户可见痕迹：{_statuses(payload)}"
    account = truncated[0]
    assert account["limit_bytes"] == 600
    assert account["original_bytes"] > 600, "原始体量必须如实记账"
    assert 0 < int(account["kept_bytes"]) <= 600, f"实际注入量必须如实记账：{account}"


def test_截断留痕是业务可读表述而不是字段名堆砌(evaluated, monkeypatch):
    """痕迹给的是人，不是日志采集器：三个数要出现在可读句子里，不是甩内部字段名。"""
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "600")
    _patch_docs(monkeypatch, criteria=None, bid_text=_oversized_bid())

    payload, _meta = _run("rid-degrade-truncated-readable")

    account = next(w for w in _warnings(payload) if w["status"] == "draft_truncated")
    message = str(account["message"])
    assert "截断" in message
    assert f"{int(account['original_bytes']):,}" in message, f"原始体量要出现在正文里：{message}"
    assert f"{int(account['kept_bytes']):,}" in message, f"实际注入量要出现在正文里：{message}"
    assert f"{int(account['limit_bytes']):,}" in message, f"预算上限要出现在正文里：{message}"
    assert not any(
        field in message for field in ("original_bytes", "kept_bytes", "limit_bytes")
    ), f"正文不该堆内部字段名：{message}"


def test_未超预算时不产生截断留痕(evaluated, monkeypatch):
    """对照组：没截断就不该多出一条 warning（可见性不等于噪音）。"""
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "100000")
    _patch_docs(monkeypatch, criteria=_CRITERIA_JSON)

    payload, _meta = _run("rid-degrade-fits")

    assert "draft_truncated" not in _statuses(payload)
