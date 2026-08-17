"""KD5：``score=null`` 的语义显式化 —— ``scoring[].pending_reason`` 枚举全链锁定。

`score:null` 此前承载 ≥6 种语义（等横比 / 需外部数据 / 需现场答辩 / 回查降级 / manual 合法 null /
实质性不响应），消费端各自立法解释。本组测试锁定契约链：schema 声明枚举 → prompt 产出义务 →
服务端语义闸拒绝缺失 → 服务端自身的降级路径也必须打上枚举（否则自造违约数据）。
"""

from __future__ import annotations

from pathlib import Path

import jsonschema
import pytest

from server.common.contract import JSONContractError, load_output_schema
from server.tender import evidence as tender_evidence
from server.tender import output as to

AUDIT_SCHEMA = "common/audit-result.schema.json"
PENDING_REASONS = {
    "cross_bid",
    "external_data",
    "live_event",
    "evidence_unresolved",
    "manual_mode",
    "non_responsive",
}


def _tender_result(scoring: list[dict]) -> dict:
    return {
        "claim_id": "B1",
        "verdict": "manual_review",
        "manual_review_reason": "insufficient_evidence",
        "explanation": "价格项待全部投标报价一起计算。",
        "reasons": ["价格项需横比"],
        "policy_refs": ["tender_evalmethod_001"],
        "risk_score": 20,
        "extracted_data": {"scoring": scoring},
        "evidence_chain": [],
        "reviewed_by": "tender-evaluator",
        "timestamp": "2026-08-11T00:00:00+00:00",
    }


# ── 契约声明 ────────────────────────────────────────────────────────────────────


def test_audit_schema_declares_pending_reason_enum():
    schema = load_output_schema(AUDIT_SCHEMA)
    item_schema = schema["properties"]["extracted_data"]["properties"]["scoring"]["items"]
    assert set(item_schema["properties"]["pending_reason"]["enum"]) == PENDING_REASONS


def test_audit_schema_rejects_unknown_pending_reason():
    schema = load_output_schema(AUDIT_SCHEMA)
    payload = _tender_result(
        [{"item": "价格分", "max": 40, "score": None, "status": "manual_review",
          "pending_reason": "whatever"}]
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


def test_audit_schema_accepts_known_pending_reason():
    schema = load_output_schema(AUDIT_SCHEMA)
    payload = _tender_result(
        [{"item": "价格分", "max": 40, "score": None, "status": "manual_review",
          "pending_reason": "cross_bid", "basis": "待汇总"}]
    )
    jsonschema.validate(payload, schema)


def test_tender_evaluate_prompt_declares_every_pending_reason():
    """契约链：prompt 必须写明产出义务与全部枚举值，否则模型永远不产出该字段。"""
    # 2026-08-14 回滚后命令为单文件自洽形态（骨架+Read references 因会话上下文反增爆窗
    # 而废弃，见 tests/test_prompt_budget.py 头注），枚举全部内联在命令本体。
    prompt = Path(".claude/commands/tender-evaluate.md").read_text(encoding="utf-8")
    assert "pending_reason" in prompt
    for reason in PENDING_REASONS:
        assert reason in prompt, reason


# ── 服务端语义闸 ────────────────────────────────────────────────────────────────


def test_validate_rejects_null_score_without_pending_reason():
    payload = _tender_result(
        [{"item": "价格分", "max": 40, "score": None, "status": "manual_review"}]
    )
    with pytest.raises(JSONContractError, match="pending_reason"):
        to.validate_tender_result(payload)


def test_validate_rejects_unknown_pending_reason_value():
    payload = _tender_result(
        [{"item": "价格分", "max": 40, "score": None, "status": "manual_review",
          "pending_reason": "because"}]
    )
    with pytest.raises(JSONContractError, match="pending_reason"):
        to.validate_tender_result(payload)


def test_validate_accepts_null_score_with_pending_reason():
    payload = _tender_result(
        [{"item": "价格分", "max": 40, "score": None, "status": "manual_review",
          "pending_reason": "cross_bid"}]
    )
    to.validate_tender_result(payload)


def test_validate_ignores_scored_items_without_pending_reason():
    payload = _tender_result(
        [{"item": "业绩", "max": 30, "score": 30, "status": "scored"}]
    )
    to.validate_tender_result(payload)


def test_validate_leaves_expense_result_untouched(monkeypatch):
    """expense 结论无 scoring → 本闸恒不触发（跨域污染防回归）。

    规则引用真伪闸与本测试无关且依赖 gitignored 的 knowledge/（有无规则库行为不同，
    worktree 无 knowledge 时假绿），置空使测试密闭。
    """
    from server.common import output_contracts as oc

    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: set())
    payload = {
        "claim_id": "E1",
        "verdict": "approved",
        "explanation": "发票与审批单一致。",
        "reasons": ["合规"],
        "policy_refs": ["expense_001"],
        "risk_score": 5,
        "extracted_data": {"invoice_no": "fp-1"},
        "evidence_chain": [],
        "reviewed_by": "expense-auditor",
        "timestamp": "2026-08-11T00:00:00+00:00",
    }
    to.validate_tender_result(payload)


# ── 服务端自身的降级路径必须打枚举 ──────────────────────────────────────────────


def test_scored_zero_demotion_stamps_pending_reason():
    """无依据 0 分被降级 null → 打 evidence_unresolved。

    F4：该分支同时写 ``manual_review_reason="insufficient_evidence"``，语义是"没有可核的
    评分依据"，与 evidence.py 回查降级同源，故枚举必须一致取 ``evidence_unresolved``；
    ``non_responsive`` 是"投标压根没响应该项"，两者不是一回事，贴错标签会误导人工。
    """
    payload = _tender_result(
        [{"item": "技术方案", "max": 20, "score": 0, "status": "scored", "score_mode": "banded"}]
    )
    payload["extracted_data"]["disqualification_hits"] = [
        {"finding": "投错项目", "confirmed": True}
    ]
    to.validate_tender_result(payload)
    item = payload["extracted_data"]["scoring"][0]
    assert item["score"] is None
    assert item["pending_reason"] == "evidence_unresolved"
    assert item["manual_review_reason"] == "insufficient_evidence"


def test_evidence_downgrade_stamps_pending_reason():
    """回查闸把 scored 降 manual_review 且 score=null → 必须打 evidence_unresolved。"""
    sitem = {"item": "业绩", "max": 10, "score": 8, "status": "scored", "basis": "已核"}
    tender_evidence._downgrade_scoring_item(
        sitem,
        note="（出处未核实）",
        resolution_status="downgraded_unresolved",
        summary={"downgraded_items": []},
    )
    assert sitem["score"] is None
    assert sitem["pending_reason"] == "evidence_unresolved"
