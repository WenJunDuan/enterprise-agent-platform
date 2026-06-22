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
import server.common.output_contracts as _oc


@pytest.fixture(autouse=True)
def _neutralize_ambient_rules(monkeypatch):
    """真伪闸默认开后（hardening H1），本模块多数用例用合成 policy_refs（非真实 rule_id）。
    置 ``_load_known_rule_ids`` 为空集 → 真伪闸优雅跳过（不依赖 gitignored ``knowledge/``，
    CI/本地一致）；专测真伪闸的用例在体内 monkeypatch 覆盖为非空集。"""
    monkeypatch.setattr(_oc, "_load_known_rule_ids", lambda: set())


def test_unregistered_schema_is_passthrough():
    payload = {"anything": 1}
    assert apply_schema_semantics("other/unknown.schema.json", payload) is payload


@pytest.mark.parametrize("schema_name", [None, ""])
def test_empty_schema_name_is_passthrough(schema_name):
    """R1: schema_name 为 None/"" = 无命名 schema → 原样返回，不得崩（CONTRACTS_DIR / None）。

    用于 enrichment 调用（tender-extract-info 输出 {criteria, tender_info} 不对应单一契约）。
    """
    payload = {"criteria": {"items": []}, "tender_info": {"tender_no": "X"}}
    assert apply_schema_semantics(schema_name, payload) is payload


@pytest.mark.parametrize("schema_name", [None, ""])
def test_empty_schema_name_requires_text_mode(schema_name):
    """codex R1 P2: schema_name 空 + structured=True 必须显式报错（否则 build_output_format(None) 崩）。"""
    import asyncio

    from server.common.json_bridge import run_agent_json

    with pytest.raises(ValueError, match="requires structured=False"):
        asyncio.run(run_agent_json("prompt", schema_name=schema_name, structured=True))


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


def test_disqualification_hits_coerce_verdict_to_rejected():
    """R2 verdict 一致性：disqualification_hits 非空（硬废标）→ verdict 强制 rejected，即使模型
    判 manual_review（治"投错标判成 manual_review"，与其自标 disqualification_hits 自相矛盾）。"""
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        _valid_audit_result(
            verdict="manual_review",
            manual_review_reason="insufficient_evidence",
            policy_refs=["tender_evalmethod_005"],
            extracted_data={"disqualification_hits": [{"rule_id": "RR2", "finding": "投错标"}]},
        ),
    )
    assert out["verdict"] == "rejected"
    assert out["result"] is False  # enrich 据 rejected 派生
    assert "manual_review_reason" not in out  # 非 manual_review 剥离


def test_eligibility_fail_coerces_verdict_to_rejected():
    """R2：任一 eligibility_checks.status=fail（资格否决）→ verdict 强制 rejected。"""
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        _valid_audit_result(
            verdict="approved",
            policy_refs=["tender_evalmethod_006"],
            extracted_data={"eligibility_checks": [{"check": "资质", "status": "fail"}]},
        ),
    )
    assert out["verdict"] == "rejected"


def test_no_disqualification_leaves_verdict_untouched():
    """无废标/资格否决 → verdict 不被纠偏（expense 域 extracted_data 无此结构，恒不触发）。"""
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        _valid_audit_result(verdict="approved", extracted_data={"scoring": []}),
    )
    assert out["verdict"] == "approved"


@pytest.mark.parametrize(
    "disq",
    ["无", "", {"count": 0}, [], [{}], [None], "none", 0],
)
def test_falsy_disqualification_does_not_coerce(disq):
    """codex R2 P1 回归：disqualification_hits 为假值（"无"/[]/[{}]/{} 等）绝不误判 rejected。

    extracted_data 无内部 schema：模型可能写中文"无"(truthy 字符串)、空 list、空 dict 列表等——
    朴素 bool() 会把"无"当命中→误判废标。必须是"非空 list + 含有内容的 dict"才算硬废标。
    """
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        _valid_audit_result(verdict="approved", extracted_data={"disqualification_hits": disq}),
    )
    assert out["verdict"] == "approved"


def test_missing_envelope_fields_defaulted_not_rejected():
    """R3：模型漏给信封类必填字段(reasons/risk_score/policy_refs/evidence_chain)→兜底默认而非整单
    契约失败（实测 deepseek 全量评标漏 reasons 反复重试至失败）。manual_review 不需 policy_refs。"""
    base = _valid_audit_result(verdict="manual_review", manual_review_reason="insufficient_evidence")
    for missing in ("reasons", "risk_score", "policy_refs", "evidence_chain"):
        base.pop(missing, None)
    out = apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, base)
    assert out["verdict"] == "manual_review"
    assert out["reasons"] == []
    assert out["policy_refs"] == []
    assert out["evidence_chain"] == []
    assert out["risk_score"] == 50  # 中性兜底,不触发高风险复审


def test_evidence_chain_extra_fields_normalized_not_rejected():
    """R3：evidence_chain 项含未知字段(rule_ref/relevance)或漏 conclusion → 归一到
    {source,finding,conclusion} 而非整单契约失败（实测 qwen/deepseek 评标反复挂 `evidence_chain/N`）。"""
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        _valid_audit_result(
            evidence_chain=[
                {"source": "招标文件第14页", "finding": "实质性未响应", "rule_ref": "tender_evalmethod_005"},
                {"source": "p.62", "finding": "评分标准", "relevance": "不适用本项目"},
            ]
        ),
    )
    ec = out["evidence_chain"]
    assert len(ec) == 2
    for item in ec:
        assert set(item.keys()) == {"source", "finding", "conclusion"}  # 未知字段已剥
    assert ec[0]["source"] == "招标文件第14页"
    assert ec[0]["conclusion"] == ""  # 缺失必填补空串


@pytest.mark.parametrize("status", ["FAIL", "fail ", " Fail"])
def test_eligibility_fail_case_insensitive_coerces(status):
    """codex R2 P2：eligibility status 大小写/空白容错（FAIL/fail /Fail 均算 fail→rejected）。"""
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        _valid_audit_result(
            verdict="approved",
            policy_refs=["tender_evalmethod_006"],
            extracted_data={"eligibility_checks": [{"check": "资质", "status": status}]},
        ),
    )
    assert out["verdict"] == "rejected"


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


# ── G1b-full（env-gated 引用存在性闸 RULE_REF_CHECK）─────────────────────────


def test_rule_ref_check_on_by_default_rejects_unknown_ref(monkeypatch):
    # 默认开（hardening H1）：env 未设即生效，编造的 rule_id 被拒（空集仍优雅跳过，见下）。
    import server.common.output_contracts as oc

    monkeypatch.delenv("RULE_REF_CHECK", raising=False)
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: {"expense_travel_001"})
    with pytest.raises(JSONContractError):
        apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, _valid_audit_result(policy_refs=["NOPE-999"]))


def test_rule_ref_check_disabled_allows_unknown_ref(monkeypatch):
    # 显式 RULE_REF_CHECK=0 逃生阀：即便引用不存在的 rule_id 也放行。
    import server.common.output_contracts as oc

    monkeypatch.setenv("RULE_REF_CHECK", "0")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: {"expense_travel_001"})
    apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, _valid_audit_result(policy_refs=["NOPE-999"]))


def test_rule_ref_check_on_rejects_fabricated_ref(monkeypatch):
    import server.common.output_contracts as oc

    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: {"expense_travel_001"})
    with pytest.raises(JSONContractError):
        apply_schema_semantics(
            DEFAULT_OUTPUT_SCHEMA_NAME, _valid_audit_result(policy_refs=["TRAVEL-RULE-999"])
        )


def test_rule_ref_check_on_allows_real_ref(monkeypatch):
    import server.common.output_contracts as oc

    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: {"expense_travel_001"})
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME, _valid_audit_result(policy_refs=["expense_travel_001"])
    )
    assert out["result"] is True


def test_mixed_policy_refs_strips_fabricated_keeps_real(monkeypatch):
    """R4-D 降重试：真+假混合的 policy_refs → 剥假留真直接过，而非整单拒重跑 290s（实测 deepseek
    把废标描述当 ref）。承重 rejected 有真实依据(留下)即合法。"""
    import server.common.output_contracts as oc

    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: {"tender_evalmethod_005"})
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        _valid_audit_result(
            verdict="rejected",
            policy_refs=["tender_evalmethod_005", "未实质响应招标文件作废标"],
        ),
    )
    assert out["verdict"] == "rejected"
    assert out["policy_refs"] == ["tender_evalmethod_005"]  # 编造描述被剥


def test_malformed_optional_plan_dropped_not_rejected():
    """R4-D 降重试：可选 extracted_data.plan 形不符 plan 契约 → 丢弃而非整单拒（实测 glm）。"""
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        _valid_audit_result(
            verdict="manual_review",
            manual_review_reason="insufficient_evidence",
            extracted_data={"plan": [{"bogus": "shape", "no": "step/intent"}]},
        ),
    )
    assert out["verdict"] == "manual_review"
    assert "plan" not in out["extracted_data"]  # 形不对的 plan 已丢


def test_rule_ref_check_on_but_no_rules_loaded_skips(monkeypatch):
    import server.common.output_contracts as oc

    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: set())  # 无 knowledge → 跳过
    apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, _valid_audit_result(policy_refs=["ANYTHING"]))


# ── G1c 评分项内部一致性（score ≤ max，验证非判断）──────────────────────────


def test_scoring_consistency_rejects_score_over_max():
    bad = _valid_audit_result(
        extracted_data={"scoring": [{"item": "技术", "max": 10, "score": 15, "status": "scored"}]}
    )
    with pytest.raises(JSONContractError):
        apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, bad)


def test_scoring_consistency_allows_null_score():
    # 不可判定项 score=null（manual_review）→ 跳过，不报错（呼应"绝不判 0"）。
    ok = _valid_audit_result(
        extracted_data={"scoring": [{"item": "答辩", "max": 10, "score": None, "status": "manual_review"}]}
    )
    out = apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, ok)
    assert out["result"] is True


def test_scoring_consistency_allows_valid_score():
    ok = _valid_audit_result(
        extracted_data={"scoring": [{"item": "技术", "max": 10, "score": 8, "status": "scored"}]}
    )
    out = apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, ok)
    assert out["result"] is True


# ── G2 类型化任务计划（extracted_data.plan 可选，产出则校验形）──────────────


def test_plan_present_valid_passes():
    ok = _valid_audit_result(
        extracted_data={"plan": {"nodes": [{"step": 0, "intent": "清点文件", "tag": "sequential"}]}}
    )
    out = apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, ok)
    assert out["result"] is True


def test_plan_present_malformed_dropped_not_rejected():
    # R4-D 行为变更：plan 是【可选】非承重字段，形不对 → 丢弃而非整单拒（旧行为整单拒会重跑 290s）。
    bad = _valid_audit_result(extracted_data={"plan": {"nodes": [{"step": 0}]}})
    out = apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, bad)
    assert "plan" not in out["extracted_data"]


def test_no_plan_skips_plan_check():
    # 未产出 plan（内联散文计划）→ 跳过，不报错。
    out = apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, _valid_audit_result())
    assert out["result"] is True


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


# ── R4: scoring 明细完整性（笼统扣分/加分无明细 → warning）────────────────────


def _warning_codes(out: dict) -> set[str]:
    return {w.get("code") for w in (out.get("extracted_data") or {}).get("validation_warnings", [])}


def test_r4_deduction_scored_partial_without_hits_warns():
    # 部分扣分(0<score<max)却无 deduction_hits 明细 → 笼统扣分告警
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        _valid_audit_result(
            extracted_data={
                "scoring": [
                    {"item": "技术", "max": 6, "score": 4, "status": "scored", "score_mode": "deduction"}
                ]
            }
        ),
    )
    assert "deduction_scored_no_hits" in _warning_codes(out)


def test_r4_deduction_full_score_without_hits_no_warn():
    # 满分不扣，无 hits 合法 → 不告警
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        _valid_audit_result(
            extracted_data={
                "scoring": [
                    {"item": "技术", "max": 6, "score": 6, "status": "scored", "score_mode": "deduction"}
                ]
            }
        ),
    )
    assert "deduction_scored_no_hits" not in _warning_codes(out)


def test_r4_deduction_with_hits_no_completeness_warn():
    # 有逐条明细且算术自洽 → 无完整性告警
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        _valid_audit_result(
            extracted_data={
                "scoring": [
                    {
                        "item": "技术",
                        "max": 6,
                        "score": 4,
                        "status": "scored",
                        "score_mode": "deduction",
                        "deduction_hits": [{"deduction_id": "d1", "deducted": 2}],
                    }
                ]
            }
        ),
    )
    assert "deduction_scored_no_hits" not in _warning_codes(out)


def test_r4_additive_scored_above_base_without_awards_warns():
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        _valid_audit_result(
            extracted_data={
                "criteria": {"items": [{"item": "加分项", "score_mode": "additive", "base": 0}]},
                "scoring": [
                    {"item": "加分项", "max": 5, "score": 3, "status": "scored", "score_mode": "additive"}
                ],
            }
        ),
    )
    assert "additive_scored_no_awards" in _warning_codes(out)


def test_r4_manual_review_item_no_completeness_warn():
    # manual_review 项不触发明细完整性告警
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        _valid_audit_result(
            extracted_data={
                "scoring": [
                    {"item": "答辩", "max": 6, "score": None, "status": "manual_review", "score_mode": "deduction"}
                ]
            }
        ),
    )
    assert "deduction_scored_no_hits" not in _warning_codes(out)
