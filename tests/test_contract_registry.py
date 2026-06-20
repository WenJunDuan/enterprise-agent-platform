"""契约后处理注册表：apply_schema_semantics 的 validate+enrich 分发 (OCP)。

锁定：内置 audit schema 仍校验+派生；未注册 schema 原样返回不报错；
新 schema 注册即生效，无需改分发器。
"""

from __future__ import annotations

import pytest

from server.common.contract import (
    DEFAULT_OUTPUT_SCHEMA_NAME,
    JSONContractError,
    SchemaProcessor,
    _SCHEMA_PROCESSORS,
    apply_schema_semantics,
    register_schema_processor,
)


def test_unregistered_schema_is_passthrough():
    payload = {"anything": 1}
    assert apply_schema_semantics("other/unknown.schema.json", payload) is payload


def _valid_audit_result(**overrides) -> dict:
    """一份满足 audit-result schema required + additionalProperties:false 的完整结论。"""
    base = {
        "claim_id": "C-1",
        "verdict": "approved",
        "explanation": "符合差旅政策",
        "reasons": [],
        "policy_refs": ["EXPENSE-TRAVEL-001"],
        "risk_score": 10,
        "extracted_data": {},
        "evidence_chain": [],
        "reviewed_by": "expense-auditor",
        "timestamp": "2026-06-20T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_builtin_audit_schema_validates_and_enriches():
    out = apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, _valid_audit_result())
    # enrich 从 verdict 派生 result/conclusion
    assert out["result"] is True
    assert out["conclusion"] == "合规"


def test_builtin_audit_schema_rejects_bad_verdict():
    with pytest.raises(JSONContractError):
        apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, {"verdict": "??", "explanation": "x"})


# ── G1 验证闸（round4 F1）：schema 形校验先于一切语义处理 ──────────────────────


def test_gate_rejects_missing_required_field():
    # 缺 policy_refs（schema required）→ 验证闸拒，不再像旧文本路径那样静默通过+归档。
    payload = _valid_audit_result()
    del payload["policy_refs"]
    with pytest.raises(JSONContractError):
        apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, payload)


def test_gate_rejects_additional_property():
    # additionalProperties:false → 模型自报 result/多余字段被拒。
    with pytest.raises(JSONContractError):
        apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, _valid_audit_result(result=True))


def test_gate_rejects_wrong_type():
    # risk_score 须 integer 0-100；给字符串 → 拒。
    with pytest.raises(JSONContractError):
        apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, _valid_audit_result(risk_score="high"))


def test_gate_rejects_bad_enum_value():
    # manual_review_reason 不在 7 枚举内 → schema enum 校验拒。
    with pytest.raises(JSONContractError):
        apply_schema_semantics(
            DEFAULT_OUTPUT_SCHEMA_NAME,
            _valid_audit_result(verdict="manual_review", manual_review_reason="not_a_reason"),
        )


def test_gate_rejects_approved_without_policy_refs():
    # G1b 幻觉闸：approved 但 policy_refs 为空 → 无依据判决，拒（schema 只能要求字段存在）。
    with pytest.raises(JSONContractError):
        apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, _valid_audit_result(policy_refs=[]))


def test_gate_rejects_rejected_without_policy_refs():
    # 与 approved 对称：rejected 也是承重结论，空 refs → 拒。
    with pytest.raises(JSONContractError):
        apply_schema_semantics(
            DEFAULT_OUTPUT_SCHEMA_NAME, _valid_audit_result(verdict="rejected", policy_refs=[])
        )


def test_manual_review_allowed_with_empty_policy_refs():
    # manual_review 豁免 G1b：人工复核本就因证据/规则不足，不强求引规则（边界快照）。
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        _valid_audit_result(verdict="manual_review", manual_review_reason="rule_gap", policy_refs=[]),
    )
    assert out["verdict"] == "manual_review"


def test_register_new_schema_takes_effect_without_editing_dispatcher():
    schema = "test/widget.schema.json"
    calls: list[str] = []

    def _validate(out):
        calls.append("validate")
        if "name" not in out:
            raise JSONContractError("widget needs name")

    def _enrich(out):
        out["enriched"] = True
        return out

    register_schema_processor(schema, validate=_validate, enrich=_enrich)
    try:
        result = apply_schema_semantics(schema, {"name": "w"})
        assert calls == ["validate"]
        assert result["enriched"] is True
        with pytest.raises(JSONContractError):
            apply_schema_semantics(schema, {})  # 缺 name → validate 抛错
    finally:
        _SCHEMA_PROCESSORS.pop(schema, None)  # 不污染全局注册表


def test_processor_dataclass_defaults_are_none():
    proc = SchemaProcessor()
    assert proc.validate is None
    assert proc.enrich is None
