"""Unit tests for server/core.py pure functions.

锁定现有行为，不改实现——全部用 monkeypatch 或 tmp_path 隔离 I/O，
不发起任何网络请求，不调用 claude_agent_sdk.query。
"""

from __future__ import annotations

import json
from typing import Any

import pytest

# ── 防止 server.core 模块级 offline_guard_error 在 build_options 时炸测试 ─────
# configure_claude_runtime_env() 只写 env vars，ensure_local_layout() 只建目录，均安全。
# offline_guard_error 在 build_options() 内调用，纯函数测试不会触达，无需 mock。

from server.core import (
    DEFAULT_OUTPUT_SCHEMA_NAME,
    INIT_RULES_REPORT_SCHEMA_NAME,
    JSONContractError,
    _coerce_reason_to_str,
    _coerce_risk_dimensions,
    _extract_json_object,
    _scale_risk_dimension_score,
    enrich_audit_decision,
    resolve_output_schema_path,
    validate_structured_output_semantics,
)
import server.common.output_contracts as _oc


@pytest.fixture(autouse=True)
def _neutralize_ambient_rules(monkeypatch):
    """真伪闸默认开后（hardening H1），用合成 policy_refs 的用例把 ``_load_known_rule_ids``
    置空集 → 优雅跳过，不依赖 gitignored ``knowledge/``（CI/本地一致）。"""
    monkeypatch.setattr(_oc, "_load_known_rule_ids", lambda: set())


# ═════════════════════════════════════════════════════════════════════════════
# _extract_json_object
# ═════════════════════════════════════════════════════════════════════════════


class TestExtractJsonObject:
    def test_plain_json(self):
        assert _extract_json_object('{"verdict": "approved"}') == {"verdict": "approved"}

    def test_think_tag_strips_draft_json(self):
        """推理草稿在 <think> 内的临时 JSON 不应被采用；最终答案在 </think> 之后。"""
        text = '<think>{"verdict":"draft"}</think>{"verdict":"approved"}'
        assert _extract_json_object(text) == {"verdict": "approved"}

    def test_think_tag_last_occurrence(self):
        """多个 </think> 时以最后一个为准。"""
        text = '<think>bad1</think><think>bad2</think>{"verdict":"final"}'
        assert _extract_json_object(text) == {"verdict": "final"}

    def test_json_fence_stripped(self):
        assert _extract_json_object('```json\n{"k": 1}\n```') == {"k": 1}

    def test_multiple_balanced_objects_last_wins(self):
        """多个平衡 {} 时返回最后一个可解析的 dict（最终答案在末尾）。"""
        text = '{"draft": 1} some text {"final": 2}'
        assert _extract_json_object(text) == {"final": 2}

    def test_string_with_embedded_braces(self):
        """字符串内嵌花括号不应打乱平衡计数。"""
        text = '{"msg": "use {} and {{}}"}'
        result = _extract_json_object(text)
        assert result == {"msg": "use {} and {{}}"}

    def test_escaped_quote_inside_string(self):
        """转义引号不应提前结束字符串，从而误判 JSON 边界。"""
        text = '{"key": "he said \\"hello\\""}'
        result = _extract_json_object(text)
        assert result is not None
        assert result["key"] == 'he said "hello"'

    def test_empty_text_returns_none(self):
        assert _extract_json_object("") is None

    def test_no_json_returns_none(self):
        assert _extract_json_object("no json here") is None

    def test_half_open_json_returns_none(self):
        assert _extract_json_object('{"incomplete": ') is None

    def test_array_not_returned_as_dict(self):
        """顶层数组不满足 dict 要求，应返回 None。"""
        assert _extract_json_object("[1, 2, 3]") is None

    def test_think_json_only_in_think_returns_none(self):
        """如果唯一 JSON 在 </think> 里，截断后应返回 None。"""
        text = '<think>{"draft": 1}</think>no json after'
        assert _extract_json_object(text) is None

    def test_nested_json(self):
        """嵌套 {} 正确计数，完整对象被识别。"""
        text = '{"outer": {"inner": 42}}'
        assert _extract_json_object(text) == {"outer": {"inner": 42}}

    def test_only_invalid_json_returns_none(self):
        """存在 {} 但无法 parse 成 dict，返回 None。"""
        assert _extract_json_object("{not valid}") is None

    def test_trailing_think_after_answer(self):
        """R1 修复：答案 JSON 后跟一个游离的 </think>（glm/deepseek 偶发）——旧 rsplit 截到
        末尾 </think> 之后=空 → 误返 None；应剥离成对 think 块后仍找到答案。"""
        text = '{"verdict": "approved"}</think>'
        assert _extract_json_object(text) == {"verdict": "approved"}

    def test_reasoning_then_answer_then_stray_close(self):
        """成对 <think>…</think> 草稿 + 答案 + 游离尾随 </think>：剥离草稿块后答案仍可取。"""
        text = '<think>reasoning here</think>{"verdict": "final"}</think>'
        assert _extract_json_object(text) == {"verdict": "final"}

    def test_draft_in_think_then_answer_with_stray_close(self):
        """草稿 JSON 在成对 think 内 + 答案在外 + 尾随游离 </think>：取答案而非草稿。"""
        text = '<think>{"verdict": "draft"}</think>{"verdict": "final"}</think>'
        assert _extract_json_object(text) == {"verdict": "final"}


# ═════════════════════════════════════════════════════════════════════════════
# _coerce_reason_to_str
# ═════════════════════════════════════════════════════════════════════════════


class TestCoerceReasonToStr:
    def test_string_passthrough(self):
        assert _coerce_reason_to_str("合规") == "合规"

    def test_dict_with_description(self):
        r = _coerce_reason_to_str({"description": "金额超标"})
        assert r == "金额超标"

    def test_dict_with_message(self):
        r = _coerce_reason_to_str({"message": "发票缺失"})
        assert r == "发票缺失"

    def test_dict_with_reason(self):
        r = _coerce_reason_to_str({"reason": "未审批"})
        assert r == "未审批"

    def test_dict_with_severity_prefix(self):
        r = _coerce_reason_to_str({"severity": "high", "description": "异常金额"})
        assert r == "[high] 异常金额"

    def test_dict_severity_without_description_no_prefix(self):
        """severity 存在但 description/message/reason 全缺时，不加 [] 前缀。"""
        r = _coerce_reason_to_str({"severity": "low"})
        # desc 为空，severity 独立无意义，回退到 json.dumps
        assert "low" in r

    def test_dict_fallback_to_json_dumps(self):
        """dict 里没有 description/message/reason，回退 json.dumps。"""
        d = {"code": "E001", "detail": "something"}
        r = _coerce_reason_to_str(d)
        parsed = json.loads(r)
        assert parsed == d

    def test_non_str_non_dict_int(self):
        assert _coerce_reason_to_str(42) == "42"

    def test_non_str_non_dict_none(self):
        assert _coerce_reason_to_str(None) == "None"

    def test_empty_string(self):
        assert _coerce_reason_to_str("") == ""


# ═════════════════════════════════════════════════════════════════════════════
# _scale_risk_dimension_score
# ═════════════════════════════════════════════════════════════════════════════


class TestScaleRiskDimensionScore:
    def test_zero_to_ten_passthrough(self):
        for v in (0, 5, 10):
            assert _scale_risk_dimension_score(v) == v

    def test_value_over_ten_divided_by_ten(self):
        assert _scale_risk_dimension_score(80) == 8
        assert _scale_risk_dimension_score(100) == 10

    def test_clamp_min(self):
        assert _scale_risk_dimension_score(-5) == 0

    def test_clamp_max(self):
        # 110 → 11.0 → clamp to 10
        assert _scale_risk_dimension_score(110) == 10

    def test_non_numeric_string_returns_zero(self):
        assert _scale_risk_dimension_score("abc") == 0

    def test_none_returns_zero(self):
        assert _scale_risk_dimension_score(None) == 0

    def test_bool_true_treated_as_one(self):
        # bool is subclass of int: True == 1
        assert _scale_risk_dimension_score(True) == 1

    def test_bool_false_treated_as_zero(self):
        assert _scale_risk_dimension_score(False) == 0

    def test_float_value(self):
        assert _scale_risk_dimension_score(7.6) == 8  # round

    def test_string_numeric(self):
        assert _scale_risk_dimension_score("5") == 5


# ═════════════════════════════════════════════════════════════════════════════
# _coerce_risk_dimensions
# ═════════════════════════════════════════════════════════════════════════════


class TestCoerceRiskDimensions:
    def test_dict_mapping_form(self):
        result = _coerce_risk_dimensions({"anomaly": 85, "invoice": 5})
        assert result is not None
        names = {d["name"] for d in result}
        assert names == {"anomaly", "invoice"}
        # anomaly: 85 → div by 10 → 8 (or 9 depending on rounding)
        anomaly = next(d for d in result if d["name"] == "anomaly")
        assert (
            anomaly["score"] == 8
        )  # round(8.5) = 8 in Python banker's rounding, but 85/10=8.5 → round=8 or 9
        # Actually Python rounds 8.5 → 8 (banker's rounding). Let's be precise:

        assert anomaly["score"] == round(8.5)  # banker's rounding == 8

    def test_list_of_dicts_form(self):
        result = _coerce_risk_dimensions(
            [{"name": "amount", "score": 6}, {"name": "approval", "score": 9}]
        )
        assert result is not None
        assert len(result) == 2

    def test_list_with_non_dict_items_skipped(self):
        result = _coerce_risk_dimensions([{"name": "amount", "score": 3}, "invalid", 42])
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "amount"

    def test_empty_dict_returns_none(self):
        assert _coerce_risk_dimensions({}) is None

    def test_empty_list_returns_none(self):
        assert _coerce_risk_dimensions([]) is None

    def test_non_dict_non_list_returns_none(self):
        assert _coerce_risk_dimensions("invalid") is None
        assert _coerce_risk_dimensions(42) is None
        assert _coerce_risk_dimensions(None) is None

    def test_list_with_missing_name_skipped(self):
        result = _coerce_risk_dimensions([{"score": 5}])
        # name is None → skipped
        assert result is None

    def test_dict_with_empty_name_skipped(self):
        result = _coerce_risk_dimensions({"": 5})
        assert result is None

    def test_score_normalized_for_dict_form(self):
        result = _coerce_risk_dimensions({"budget": 100})
        assert result is not None
        assert result[0]["score"] == 10  # clamp


# ═════════════════════════════════════════════════════════════════════════════
# enrich_audit_decision
# ═════════════════════════════════════════════════════════════════════════════


class TestEnrichAuditDecision:
    def test_approved_verdict_derives_result_and_conclusion(self):
        d: dict[str, Any] = {"verdict": "approved", "explanation": "ok"}
        enrich_audit_decision(d)
        assert d["result"] is True
        assert d["conclusion"] == "合规"

    def test_rejected_verdict(self):
        d: dict[str, Any] = {"verdict": "rejected", "explanation": "no"}
        enrich_audit_decision(d)
        assert d["result"] is False
        assert d["conclusion"] == "不合规"

    def test_manual_review_verdict(self):
        d: dict[str, Any] = {"verdict": "manual_review", "explanation": "need review"}
        enrich_audit_decision(d)
        assert d["result"] is False
        assert d["conclusion"] == "待人工复核"

    def test_unknown_verdict_not_injected(self):
        d: dict[str, Any] = {"verdict": "unknown_thing"}
        enrich_audit_decision(d)
        assert "result" not in d
        assert "conclusion" not in d

    def test_reasons_flattened_from_objects(self):
        d: dict[str, Any] = {
            "verdict": "rejected",
            "reasons": [{"description": "金额超限"}, "发票缺失"],
        }
        enrich_audit_decision(d)
        assert d["reasons"] == ["金额超限", "发票缺失"]

    def test_policy_refs_flattened(self):
        d: dict[str, Any] = {
            "verdict": "approved",
            "policy_refs": [{"code": "R001"}, "R002"],
        }
        enrich_audit_decision(d)
        # dict with no description/message/reason falls back to json.dumps
        assert isinstance(d["policy_refs"][0], str)
        assert d["policy_refs"][1] == "R002"

    def test_risk_dimensions_normalized(self):
        d: dict[str, Any] = {
            "verdict": "approved",
            "risk_dimensions": {"anomaly": 50},
        }
        enrich_audit_decision(d)
        assert isinstance(d["risk_dimensions"], list)
        assert d["risk_dimensions"][0]["name"] == "anomaly"
        assert d["risk_dimensions"][0]["score"] == 5

    def test_non_dict_input_returned_unchanged(self):
        lst: list[Any] = [1, 2, 3]
        result = enrich_audit_decision(lst)
        assert result == [1, 2, 3]

    def test_reasons_non_list_not_touched(self):
        d: dict[str, Any] = {"verdict": "approved", "reasons": "single string"}
        enrich_audit_decision(d)
        assert d["reasons"] == "single string"


# ═════════════════════════════════════════════════════════════════════════════
# normalize_audit_result — server metadata stamping (G1 pre-validate)
# ═════════════════════════════════════════════════════════════════════════════


class TestNormalizeAuditResult:
    def test_stamps_missing_server_metadata(self):
        out = _oc.normalize_audit_result({"verdict": "manual_review"}, request_id="req-123")
        assert out["claim_id"] == "req-123"  # claim_id 缺 → 回落 request_id
        assert out["reviewed_by"]  # 服务端盖章
        assert out["timestamp"]
        assert out["extracted_data"] == {}  # 漏给 → 空对象

    def test_keeps_model_supplied_claim_id(self):
        out = _oc.normalize_audit_result(
            {"claim_id": "EXP-9", "verdict": "approved"}, request_id="req-1"
        )
        assert out["claim_id"] == "EXP-9"  # 模型给了就不覆盖

    def test_no_request_id_falls_back_to_placeholder(self):
        out = _oc.normalize_audit_result({"verdict": "approved"})
        assert out["claim_id"] == "UNKNOWN"

    def test_risk_dimensions_object_coerced_and_invalid_dropped(self):
        # live eval 实测形状：对象映射 + 0-100 量纲 + 非枚举名 'compliance'
        out = _oc.normalize_audit_result(
            {"verdict": "manual_review", "risk_dimensions": {"anomaly": 60, "compliance": 45}},
            request_id="r",
        )
        assert isinstance(out["risk_dimensions"], list)
        names = [d["name"] for d in out["risk_dimensions"]]
        assert names == ["anomaly"]  # 'compliance' 非枚举被清
        assert out["risk_dimensions"][0]["score"] == 6  # 0-100 → 0-10

    def test_manual_review_reason_stripped_when_not_manual_review(self):
        # 模型在 approved/rejected 时偶带 manual_review_reason → 应剥离，避免脏枚举残留。
        out = _oc.normalize_audit_result(
            {"verdict": "rejected", "manual_review_reason": "data_conflict"}, request_id="r"
        )
        assert "manual_review_reason" not in out

    def test_manual_review_reason_kept_when_manual_review(self):
        out = _oc.normalize_audit_result(
            {"verdict": "manual_review", "manual_review_reason": "data_conflict"}, request_id="r"
        )
        assert out["manual_review_reason"] == "data_conflict"

    def test_full_pipeline_validates_live_failure_shape(self):
        """复现 live eval 的失败输出（缺 claim_id/metadata + 对象 risk_dimensions）→ 经
        apply_schema_semantics 应通过硬校验并补全/派生，不再抛 'claim_id is required'。"""
        from server.common.contract import (
            DEFAULT_OUTPUT_SCHEMA_NAME,
            apply_schema_semantics,
        )

        raw: dict[str, Any] = {
            "verdict": "manual_review",
            "manual_review_reason": "data_conflict",
            "explanation": "字段冲突需人工核实",
            "reasons": ["出差同日却住宿2晚"],
            "policy_refs": [],
            "risk_score": 62,
            "risk_dimensions": {"anomaly": 60, "compliance": 45},
            "evidence_chain": [{"source": "a", "finding": "b", "conclusion": "c"}],
        }
        out = apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, raw, request_id="req-xyz")
        assert out["claim_id"] == "req-xyz"
        assert out["verdict"] == "manual_review"
        assert out["result"] is False  # enrich 派生
        assert out["conclusion"] == "待人工复核"


# ═════════════════════════════════════════════════════════════════════════════
# validate_structured_output_semantics — audit schema
# ═════════════════════════════════════════════════════════════════════════════


class TestValidateAuditSchema:
    def _ok(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        base: dict[str, Any] = {
            "verdict": "approved",
            "explanation": "合规",
            "reasons": [],
            "policy_refs": ["EXPENSE-TRAVEL-001"],  # G1b：approved 须引 ≥1 规则
        }
        if extra:
            base.update(extra)
        return base

    def test_valid_approved(self):
        validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, self._ok())

    def test_invalid_verdict_raises(self):
        with pytest.raises(JSONContractError, match="unknown verdict"):
            validate_structured_output_semantics(
                DEFAULT_OUTPUT_SCHEMA_NAME, self._ok({"verdict": "maybe"})
            )

    def test_empty_explanation_raises(self):
        with pytest.raises(JSONContractError, match="explanation"):
            validate_structured_output_semantics(
                DEFAULT_OUTPUT_SCHEMA_NAME, self._ok({"explanation": ""})
            )

    def test_none_explanation_raises(self):
        with pytest.raises(JSONContractError, match="explanation"):
            validate_structured_output_semantics(
                DEFAULT_OUTPUT_SCHEMA_NAME, self._ok({"explanation": None})
            )

    def test_manual_review_requires_valid_reason(self):
        with pytest.raises(JSONContractError, match="manual_review_reason"):
            validate_structured_output_semantics(
                DEFAULT_OUTPUT_SCHEMA_NAME,
                self._ok({"verdict": "manual_review", "explanation": "unclear"}),
            )

    def test_manual_review_with_valid_reason_passes(self):
        validate_structured_output_semantics(
            DEFAULT_OUTPUT_SCHEMA_NAME,
            self._ok(
                {
                    "verdict": "manual_review",
                    "explanation": "unclear",
                    "manual_review_reason": "rule_gap",
                }
            ),
        )

    def test_invalid_manual_review_reason_raises(self):
        with pytest.raises(JSONContractError, match="manual_review_reason"):
            validate_structured_output_semantics(
                DEFAULT_OUTPUT_SCHEMA_NAME,
                self._ok(
                    {
                        "verdict": "manual_review",
                        "explanation": "unclear",
                        "manual_review_reason": "bad_reason",
                    }
                ),
            )

    def test_risk_dimensions_invalid_items_filtered(self):
        """共享契约继续清除非法 risk_dimensions 条目，不影响其他业务域。"""
        d = self._ok(
            {
                "risk_dimensions": [
                    {"name": "invoice", "score": 5},  # valid
                    {"name": "unknown_dim", "score": 3},  # invalid name
                    {"name": "amount", "score": 200},  # score out of range
                    {"name": "approval", "score": True},  # bool score rejected
                ]
            }
        )
        validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, d)
        kept = [item["name"] for item in d["risk_dimensions"]]
        assert kept == ["invoice"]

    def test_risk_dimensions_non_list_popped(self):
        """共享契约收到非 list 维度时清除，不让可选元数据拖垮其他域。"""
        d = self._ok({"risk_dimensions": {"anomaly": 5}})
        validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, d)
        assert "risk_dimensions" not in d

    def test_non_dict_input_raises(self):
        with pytest.raises(JSONContractError, match="JSON object"):
            validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, [1, 2])

    def test_all_valid_manual_review_reasons(self):
        valid_reasons = {
            "missing_approval",
            "rule_gap",
            "data_conflict",
            "insufficient_evidence",
            "budget_exceeded",
            "invoice_invalid",
            "pre_approval_mismatch",
        }
        for reason in valid_reasons:
            d = self._ok(
                {"verdict": "manual_review", "explanation": "x", "manual_review_reason": reason}
            )
            validate_structured_output_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, d)


# ═════════════════════════════════════════════════════════════════════════════
# validate_structured_output_semantics — init-rules schema
# ═════════════════════════════════════════════════════════════════════════════


class TestValidateInitRulesSchema:
    def _ok_initialized(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        base: dict[str, Any] = {
            "status": "initialized",
            "source_path": "/some/path",
            "written_files": ["rules.json"],
            "categories": ["expense"],
            "extracted_rule_count": 5,
        }
        if extra:
            base.update(extra)
        return base

    def test_valid_initialized(self):
        validate_structured_output_semantics(INIT_RULES_REPORT_SCHEMA_NAME, self._ok_initialized())

    def test_non_initialized_status_skips_hard_checks(self):
        """status != 'initialized' 时跳过三项硬校验，不抛异常。"""
        d: dict[str, Any] = {"status": "partial", "source_path": "/x"}
        validate_structured_output_semantics(INIT_RULES_REPORT_SCHEMA_NAME, d)

    def test_missing_source_path_raises(self):
        d = self._ok_initialized({"source_path": ""})
        with pytest.raises(JSONContractError, match="source_path"):
            validate_structured_output_semantics(INIT_RULES_REPORT_SCHEMA_NAME, d)

    def test_empty_written_files_raises(self):
        d = self._ok_initialized({"written_files": []})
        with pytest.raises(JSONContractError, match="written_files"):
            validate_structured_output_semantics(INIT_RULES_REPORT_SCHEMA_NAME, d)

    def test_none_written_files_raises(self):
        d = self._ok_initialized({"written_files": None})
        with pytest.raises(JSONContractError, match="written_files"):
            validate_structured_output_semantics(INIT_RULES_REPORT_SCHEMA_NAME, d)

    def test_empty_categories_raises(self):
        d = self._ok_initialized({"categories": []})
        with pytest.raises(JSONContractError, match="categories"):
            validate_structured_output_semantics(INIT_RULES_REPORT_SCHEMA_NAME, d)

    def test_zero_extracted_rule_count_raises(self):
        d = self._ok_initialized({"extracted_rule_count": 0})
        with pytest.raises(JSONContractError, match="extracted_rule_count"):
            validate_structured_output_semantics(INIT_RULES_REPORT_SCHEMA_NAME, d)

    def test_negative_extracted_rule_count_raises(self):
        d = self._ok_initialized({"extracted_rule_count": -1})
        with pytest.raises(JSONContractError, match="extracted_rule_count"):
            validate_structured_output_semantics(INIT_RULES_REPORT_SCHEMA_NAME, d)

    def test_non_int_extracted_rule_count_raises(self):
        d = self._ok_initialized({"extracted_rule_count": "five"})
        with pytest.raises(JSONContractError, match="extracted_rule_count"):
            validate_structured_output_semantics(INIT_RULES_REPORT_SCHEMA_NAME, d)

    def test_non_dict_raises(self):
        with pytest.raises(JSONContractError, match="JSON object"):
            validate_structured_output_semantics(INIT_RULES_REPORT_SCHEMA_NAME, [])

    def test_unrelated_schema_name_skips_all(self):
        """schema 名称不认识时，语义校验直接返回，不抛异常。"""
        validate_structured_output_semantics("other/schema.json", {"anything": 1})


# ═════════════════════════════════════════════════════════════════════════════
# resolve_output_schema_path
# ═════════════════════════════════════════════════════════════════════════════


class TestResolveOutputSchemaPath:
    def test_valid_schema_returns_path(self):
        path = resolve_output_schema_path(DEFAULT_OUTPUT_SCHEMA_NAME)
        assert path.is_file()

    def test_path_traversal_raises(self):
        with pytest.raises(JSONContractError, match="escapes"):
            resolve_output_schema_path("../../../etc/passwd")

    def test_nonexistent_schema_raises(self):
        with pytest.raises(JSONContractError, match="not found"):
            resolve_output_schema_path("common/does-not-exist.schema.json")

    def test_absolute_traversal_rejected(self):
        """绝对路径也必须拒绝（resolve 后不在 contracts 子目录）。"""
        with pytest.raises(JSONContractError):
            resolve_output_schema_path("/etc/passwd")
