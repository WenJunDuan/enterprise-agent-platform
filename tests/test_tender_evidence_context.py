"""S3c · 证据层接入主链路（AC2/AC4/AC7）：组装 + 降级可见 + 索引不可用强制 manual_review。

F7 教训：旧设计把"索引缺失 → 回落招标原文 + 投标截断"当降级归宿，而那条路径**已实证会
产出带 warning 的错误评分**（08-15 的 "largely impossible"）。错评分比失败更危险，所以
本模块的降级归宿是**强制 manual_review 不出分**，不是"凑合评一个"。
"""

from __future__ import annotations

import pytest

from server.tender import evidence_context as ec

_TENDER = "# 第三章 技术参数\n技术参数偏差表：额定功率不小于 50kW。"
_BID = (
    "# 商务标\n投标报价：壹佰贰拾万元整。报价一览表见附表。\n"
    "# 技术标\n施工组织设计详见本章。\n"
    "# 资格证明\n营业执照副本附后。"
)
_CRITERIA = {
    "eligibility_rules": [{"check": "营业执照", "requirement": "有效期内"}],
    "items": [{"item": "报价", "max": 40}, {"item": "施工组织设计", "max": 30}],
}


def test_组装产物含证据与出处而非投标全文():
    """KD1：注入的是检索到的证据片段，不是整份投标底稿。"""
    result = ec.build_evidence_context(
        tender_text=_TENDER, bid_text=_BID, criteria=_CRITERIA, project_id="tp-1"
    )
    assert result.context is not None
    assert "投标报价" in result.context
    assert "【" in result.context, "证据块必须带出处与页锚"
    assert not result.force_manual_review
    # 顺利路径不得出任何降级信号；逐项注入量（AC15）是常在的留痕账，不是降级——它走同一条
    # warnings 通道只因为那是唯一能把信号送进结论的接线，故此处按 status 判而不是判空。
    assert [w["status"] for w in result.warnings] == ["evidence_volume"], result.warnings


def test_注入量远小于投标全文():
    """AC5 的直观判据：证据层的意义就是不再把整份投标塞进去。"""
    big_bid = _BID + "\n" + "\n".join(f"【第{p}页】\n无关附件正文。" * 40 for p in range(2, 300))
    result = ec.build_evidence_context(
        tender_text=_TENDER, bid_text=big_bid, criteria=_CRITERIA, project_id="tp-1"
    )
    assert result.context is not None
    assert len(result.context) < len(big_bid) / 10


def test_零命中项进可见警告且不判分():
    """AC2/AC7：零命中项要显示检索了什么，并明确"不得判 0"。

    刻意用"部分命中"的混合 criteria：全空时走的是另一条路径（见
    :func:`test_全部零命中时不接管`），此处要验的是**接管成功但个别项没证据**这一档。
    """
    result = ec.build_evidence_context(
        tender_text=_TENDER,
        bid_text=_BID,
        criteria={
            "items": [{"item": "报价", "max": 40}, {"item": "现场答辩表现", "max": 10}]
        },
        project_id="tp-1",
    )
    unresolved = [w for w in result.warnings if w["status"] == "evidence_unresolved"]
    assert len(unresolved) == 1
    assert "现场答辩表现" in str(unresolved[0]["message"])
    assert "现场答辩表现" in str(unresolved[0]["queries"]), "必须记录实际用过的查询串"
    assert "不得判 0" in str(unresolved[0]["message"])


def test_全部零命中时停在人工复核():
    """F4：索引建成而检索全空是**结构性异常**，归宿是 manual_review，不是回落整份注入。

    本测试原先断言 ``force_manual_review is False``（回落既有路径）。那条归宿对超预算大标
    书 = 截断错评（复演 08-15），对小标书也只是把"检索全空"这个异常信号变成一次照常出分；
    两种情形下都属于"带着残缺证据出分"。既然索引建成了却一条都检不出，说明底稿与本项目
    criteria 根本对不上——该让人看一眼，而不是让模型硬评。
    """
    result = ec.build_evidence_context(
        tender_text=_TENDER,
        bid_text=_BID,
        criteria={"items": [{"item": "现场答辩表现", "max": 10}]},
        project_id="tp-1",
    )
    assert result.context is None, "全空时不得接管"
    assert result.force_manual_review is True
    assert [w["status"] for w in result.warnings] == ["evidence_all_unresolved"]


def test_投标底稿建不出索引时强制人工复核():
    """F7：降级归宿是不出分，不是"凑合评一个"——错评分比失败更危险。"""
    result = ec.build_evidence_context(
        tender_text=_TENDER, bid_text="   ", criteria=_CRITERIA, project_id="tp-1"
    )
    assert result.force_manual_review is True
    assert result.context is None
    statuses = {w["status"] for w in result.warnings}
    assert "evidence_index_unavailable" in statuses


def test_criteria不可用时不接管_交回旧路径():
    """criteria 缺项名/满分时无从按项检索——交回调用方走既有路径，不静默产出空证据。"""
    for criteria in ({}, {"items": []}, None):
        result = ec.build_evidence_context(
            tender_text=_TENDER, bid_text=_BID, criteria=criteria, project_id="tp-1"
        )
        assert result.context is None
        assert result.force_manual_review is False, "这不是失败，是本路径不适用"


def test_预算不可达时降级而不是静默缩水(monkeypatch):
    """标定值小到装不下规则层 → 强制 manual_review 并说明原因，绝不硬塞。"""
    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", "100")
    result = ec.build_evidence_context(
        tender_text=_TENDER, bid_text=_BID, criteria=_CRITERIA, project_id="tp-1"
    )
    assert result.force_manual_review is True
    assert any(w["status"] == "evidence_budget_exhausted" for w in result.warnings)
    assert any("TENDER_EFFECTIVE_CONTEXT_TOKENS" in str(w["message"]) for w in result.warnings)


def test_强制人工复核会落到结论上():
    """AC2：force_manual_review 必须真的改结论，而不是只写一条 warning。"""
    payload: dict = {"verdict": "approved", "extracted_data": {"scoring": [{"item": "报价"}]}}
    ec.enforce_manual_review(payload, reason="evidence_index_unavailable")

    assert payload["verdict"] == "manual_review"
    assert payload["manual_review_reason"] == "rule_gap"
    assert payload["extracted_data"]["scoring"] == [], "不得带着旧分数出结论"


@pytest.mark.parametrize("payload", [None, "not a dict", 42])
def test_非字典结论不炸(payload):
    """模型偶发返回非对象——防御放在这个信任边界上是必要的，不是过度防御。"""
    ec.enforce_manual_review(payload, reason="evidence_index_unavailable")


# ── 接入主链路（读层） ───────────────────────────────────────────────────────


def _patch_docs(monkeypatch, *, criteria_json: str | None, bid_text: str = _BID):
    from server.tender import doc_layer

    monkeypatch.setenv("TENDER_SLIM_CONTEXT", "1")
    monkeypatch.setattr(
        doc_layer,
        "get_project_doc",
        lambda pid, tenant: {
            "ocr_status": "ready",
            "ocr_text": _TENDER,
            "criteria": criteria_json,
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
    return doc_layer


def test_读层在有criteria时改走证据层(monkeypatch):
    """AC4 接线：证据层入口按项检索，且**把三个信号一起带出**。

    返工 F1：本测试原先断言 ``load_doc_layer_context_slim`` 内联做检索——那条形态只能返回
    ``str | None``，``warnings`` 与 ``force_manual_review`` 落地即丢，正是 pass1 REWORK 的成因。
    证据层现由 ``doc_context.load_evidence_context`` 单独驱动，返回结构化结果。
    """
    import json

    from server.tender import doc_context

    _patch_docs(monkeypatch, criteria_json=json.dumps(_CRITERIA))
    big_bid_marker = "本段是投标底稿里与任何评分项都无关的大量附件正文"
    _patch_docs(
        monkeypatch, criteria_json=json.dumps(_CRITERIA), bid_text=_BID + "\n" + big_bid_marker * 200
    )

    evidence = doc_context.load_evidence_context("tp-1", "bid-1", "acme")
    assert evidence is not None and evidence.context is not None
    assert "投标报价" in evidence.context, "检索到的证据必须在场"
    assert big_bid_marker not in evidence.context, "无关正文不该整份注入"


def test_读层无criteria时保持既有行为(monkeypatch):
    """反回归：没有 criteria 时仍走既有拼接路径，不因证据层改造而丢底稿。"""
    doc_layer = _patch_docs(monkeypatch, criteria_json=None)
    text = doc_layer.load_doc_layer_context_slim("tp-1", "bid-1", "acme")
    assert text is not None
    assert _BID.splitlines()[1] in text


# ── F5：额度饿死的项必须出 warning ──────────────────────────────────────────


def test_额度饿死的项产出evidence_truncated警告(monkeypatch):
    """F5/AC2：有命中却没装下的项要出声——否则用户看到的是"证据齐全"的假象。"""
    from server.tender import injection_budget as budget

    criteria = {
        "items": [
            {"item": "投标报价", "max": 40},
            {"item": "施工组织设计", "max": 30},
            {"item": "营业执照", "max": 10},
        ]
    }
    # 证据额度压到 P0.1 的下界（= criteria 实测额度，再低即 InjectionBudgetExhausted），
    # 并把每段应答做成"一块装得下、两块装不下"的体量——这样饿死的是排序靠后的项，
    # 而不是整批（整批饿死属预算不可达，归 InjectionBudgetExhausted 管，不是本条要测的）。
    floor = budget.criteria_tokens(criteria)
    body = "本项应答正文。" * (floor * 2 // 3 // len("本项应答正文。"))
    bid = (
        f"# 商务标\n投标报价：壹佰贰拾万元整。{body}\n"
        f"# 技术标\n施工组织设计详见本章。{body}\n"
        f"# 资格证明\n营业执照副本附后。{body}"
    )
    total = 200_000
    margin = total // 4
    scaffold = total - margin - floor - floor
    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", str(total))
    monkeypatch.setenv("TENDER_SCAFFOLD_RESERVE_TOKENS", str(scaffold))

    result = ec.build_evidence_context(
        tender_text=_TENDER, bid_text=bid, criteria=criteria, project_id="tp-1"
    )

    statuses = [w["status"] for w in result.warnings]
    assert "evidence_truncated" in statuses, f"额度饿死的项必须出声：{statuses}"
    warning = next(w for w in result.warnings if w["status"] == "evidence_truncated")
    assert warning["items"], "必须点名是哪几项被饿死"
    assert "不得判 0" in str(warning["message"])
