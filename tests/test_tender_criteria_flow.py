"""Tender 评标改造（招标文件第三章直读出会话评分标准）验收测试。

锁定新流程的关键不变量（design 验收标准逐条）：
- 会话项目规则 ``criteria`` 契约可载 + 形校验（不可判定标签是枚举，杜绝"客观 0 分"范畴错误）；
- ``criteria`` 随 ``extracted_data`` 进结论，不被出口闸吞/拒；
- 承重 ``policy_refs`` 引**通则层**真实 ``rule_id`` 过真伪闸；编造的**项目层** ``rule_id``
  （项目层已删）被真伪闸拒；
- 不可判定项 ``score: null`` 不判 0，仍放行。

真伪闸用 monkeypatch 注入"已知 rule 集"，不依赖 gitignored ``knowledge/``（CI/本地一致）。
"""

from __future__ import annotations

import jsonschema
import pytest

from server.common.contract import (
    JSONContractError,
    apply_schema_semantics,
    load_output_schema,
)
from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME
import server.common.output_contracts as oc

CRITERIA_SCHEMA = "tender/criteria.schema.json"

# 模拟本地 knowledge/tender 通则层真实 rule_id（与 evalmethod/regulation.rules.json 对齐）。
_TENDER_KNOWN = {
    "tender_evalmethod_001",
    "tender_evalmethod_003",
    "tender_evalmethod_005",
    "tender_regulation_001",
}


def _mixed_criteria(**overrides) -> dict:
    """含可判定 + 三类不可判定项的完整会话评分标准（schema 形校验用）。"""
    base = {
        "source_ref": "烛照-标段一v3.pdf 第三章《评标办法》 p.18",
        "method": "综合评估法",
        "total_max": 100,
        "items": [
            {
                "item": "价格分",
                "max": 40,
                "scoring_rule": "最低有效报价/本投标报价×40",
                "source_ref": "第三章 p.18",
                "tag": "requires_cross_bid_comparison",
            },
            {
                "item": "技术方案",
                "max": 50,
                "scoring_rule": "按对技术规格的响应程度评分",
                "source_ref": "第三章 p.19",
                "tag": "scored",
            },
            {
                "item": "项目负责人答辩",
                "max": 10,
                "scoring_rule": "现场答辩表现评分",
                "source_ref": "第三章 p.20",
                "tag": "requires_live_event",
            },
        ],
    }
    base.update(overrides)
    return base


def _scored_criteria() -> dict:
    """全部可依投标文件判定的评分标准（approved 路径用，语义自洽）。"""
    return {
        "source_ref": "烛照-标段一v3.pdf 第三章《评标办法》 p.18",
        "method": "综合评估法",
        "total_max": 100,
        "items": [
            {
                "item": "技术方案",
                "max": 60,
                "scoring_rule": "按对技术规格的响应程度评分",
                "source_ref": "第三章 p.19",
                "tag": "scored",
            },
            {
                "item": "商务响应",
                "max": 40,
                "scoring_rule": "按商务条款响应程度评分",
                "source_ref": "第三章 p.20",
                "tag": "scored",
            },
        ],
    }


def _audit_approved(**overrides) -> dict:
    """一份语义自洽的 approved 评标结论：criteria 全 scored，policy_refs 引通则层。"""
    base = {
        "claim_id": "BID-001",
        "verdict": "approved",
        "explanation": "投标实质性响应招标文件要求，按第三章评标办法逐项评分，无废标/否决情形。",
        "reasons": [],
        "policy_refs": ["tender_evalmethod_001", "tender_evalmethod_003"],
        "risk_score": 20,
        "extracted_data": {
            "criteria": _scored_criteria(),
            "scoring": [
                {"item": "技术方案", "max": 60, "score": 52, "status": "scored", "basis": "技术响应齐全"},
                {"item": "商务响应", "max": 40, "score": 36, "status": "scored", "basis": "商务条款全部响应"},
            ],
        },
        "evidence_chain": [
            {
                "source": "烛照-标段一v3.pdf 第三章 p.19",
                "finding": "技术方案评分规则（满分 60）",
                "conclusion": "据投标技术分册给技术分 52",
            }
        ],
        "reviewed_by": "tender-evaluator",
        "timestamp": "2026-06-20T00:00:00Z",
    }
    base.update(overrides)
    return base


# ── criteria 会话评分标准契约 ──────────────────────────────────────────────


def test_criteria_schema_loads():
    schema = load_output_schema(CRITERIA_SCHEMA)
    assert isinstance(schema, dict) and schema, "criteria 契约应为非空 JSON 对象"


def test_criteria_sample_validates():
    jsonschema.validate(_mixed_criteria(), load_output_schema(CRITERIA_SCHEMA))


def test_criteria_rejects_unknown_tag():
    # tag 是枚举：杜撰 "objective_zero" 之类 → 拒（防"文档没有=客观 0 分"范畴错误绕过）。
    bad = _mixed_criteria()
    bad["items"][0]["tag"] = "objective_zero"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, load_output_schema(CRITERIA_SCHEMA))


def test_criteria_rejects_item_missing_source_ref():
    # 每个评分项必须有出处（可追溯到招标文件第三章页）。
    bad = _mixed_criteria()
    del bad["items"][0]["source_ref"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, load_output_schema(CRITERIA_SCHEMA))


def test_criteria_with_score_modes_validates():
    # v2 多评分模式：deduction/banded/additive/formula/pass_fail 各容器 + 废标规则通过形校验。
    crit = _scored_criteria()
    crit["items"] = [
        {
            "item": "商务偏差", "max": 10, "scoring_rule": "每处负偏差扣2分,最多扣8分",
            "source_ref": "评标办法 p.18", "tag": "scored", "score_mode": "deduction",
            "evaluator_type": "objective",
            "deductions": [
                {"id": "d1", "condition": "商务条款负偏差", "points": 2,
                 "unit": "per_occurrence", "max_times": None, "max_deduct": 8,
                 "source_quote": "每处负偏差扣2分,最多扣8分", "source_ref": "评标办法 p.18"}
            ],
        },
        {
            "item": "技术方案", "max": 10, "scoring_rule": "优10良7中4",
            "source_ref": "评标办法 p.19", "tag": "scored", "score_mode": "banded",
            "evaluator_type": "subjective",
            "bands": [
                {"level": "优", "points": 10, "criteria": "完全满足且有亮点", "source_quote": "优秀10分"},
                {"level": "良", "points": 7, "criteria": "满足", "source_quote": "良好7分"},
                {"level": "中", "points": 4, "criteria": "基本满足", "source_quote": "一般4分"},
            ],
        },
        {
            "item": "业绩加分", "max": 5, "scoring_rule": "每个类似业绩加1分,最多5分",
            "source_ref": "评标办法 p.20", "tag": "scored", "score_mode": "additive",
            "base": 0,
            "awards": [
                {"id": "a1", "condition": "类似业绩", "points": 1, "cap": 5,
                 "source_quote": "每个类似业绩加1分最多5分", "source_ref": "评标办法 p.20"}
            ],
        },
        {
            "item": "价格分", "max": 40, "scoring_rule": "最低价/本价×40",
            "source_ref": "评标办法 p.21", "tag": "requires_cross_bid_comparison",
            "score_mode": "formula", "formula": "最低有效报价/本投标报价×40",
        },
        {
            "item": "资质门槛", "max": 5, "scoring_rule": "具备一级资质得5分否则0分",
            "source_ref": "评标办法 p.22", "tag": "scored", "score_mode": "pass_fail",
        },
    ]
    crit["rejection_rules"] = [
        {"id": "r1", "condition": "投标文件未实质性响应招标项目",
         "source_quote": "未响应本项目的投标作废标处理", "source_ref": "投标须知 p.5"}
    ]
    jsonschema.validate(crit, load_output_schema(CRITERIA_SCHEMA))


def test_criteria_with_highest_priority_eligibility_rules_validates():
    # 资格审查与评分 items 并列：最高优先级先跑，不计入 total_max。
    crit = _scored_criteria()
    crit["eligibility_rules"] = [
        {
            "id": "q1",
            "check": "企业资质证书",
            "requirement": "具备建筑工程施工总承包一级及以上资质",
            "evidence_required": "企业资质证书",
            "stage": "qualification_review",
            "priority": "highest",
            "external_data": False,
            "source_quote": "资质等级：具备建筑工程施工总承包一级及以上资质",
            "source_ref": "招标文件第三章 资格评审标准 第22页",
        },
        {
            "id": "q2",
            "check": "信用记录",
            "requirement": "未被列入失信被执行人等不得投标情形",
            "evidence_required": "信用中国查询结果",
            "stage": "qualification_review",
            "priority": "highest",
            "external_data": True,
            "source_quote": "将在信用中国网站查询投标人的信用记录",
            "source_ref": "招标文件第五部分 资格性审查 第18页",
        },
    ]
    jsonschema.validate(crit, load_output_schema(CRITERIA_SCHEMA))


def test_criteria_eligibility_rule_requires_highest_priority():
    # 防止模型把资格审查降级成普通评分项或后置检查。
    bad = _scored_criteria()
    bad["eligibility_rules"] = [
        {
            "check": "企业资质证书",
            "source_ref": "招标文件第三章 资格评审标准 第22页",
            "priority": "normal",
        }
    ]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, load_output_schema(CRITERIA_SCHEMA))


def test_criteria_rejects_unknown_score_mode():
    # score_mode 是枚举：乱造 "magic_mode" → 拒。
    bad = _scored_criteria()
    bad["items"][0]["score_mode"] = "magic_mode"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, load_output_schema(CRITERIA_SCHEMA))


def test_criteria_backward_compatible_without_new_fields():
    # 旧 criteria（无 score_mode/deductions/rejection_rules）仍通过形校验（向后兼容）。
    jsonschema.validate(_scored_criteria(), load_output_schema(CRITERIA_SCHEMA))


# ── criteria 随结论进出口闸 + 真伪闸对齐（design §4 方案 A）────────────────


def test_audit_with_criteria_passes_with_statute_policy_ref(monkeypatch):
    # 承重 approved：policy_refs 引通则层真实 rule_id → 过真伪闸；criteria 随 extracted_data 保留。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    out = apply_schema_semantics(TENDER_OUTPUT_SCHEMA_NAME, _audit_approved())
    assert out["result"] is True
    # criteria 不被出口闸吞，原样落 extracted_data（→ archive_result_payload 持久化）。
    assert out["extracted_data"]["criteria"]["method"] == "综合评估法"
    assert out["extracted_data"]["criteria"]["items"][0]["tag"] == "scored"


def test_fabricated_project_layer_ref_rejected(monkeypatch):
    # 项目层已删：把会话 criteria 当 rule_id 编造（tender_r2024007_004）塞 policy_refs
    # → 不在通则层 known 集 → 真伪闸拒。守住 H1 反幻觉价值。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    with pytest.raises(JSONContractError):
        apply_schema_semantics(
            TENDER_OUTPUT_SCHEMA_NAME,
            _audit_approved(policy_refs=["tender_r2024007_004"]),
        )


def test_unjudgeable_item_null_score_passes(monkeypatch):
    # 不可判定项（现场答辩）score:null + 整体 manual_review → 出口闸放行（"绝不判 0"）。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _audit_approved(
            verdict="manual_review",
            manual_review_reason="rule_gap",
            policy_refs=["tender_evalmethod_001"],
            extracted_data={
                "criteria": _mixed_criteria(),
                "scoring": [
                    {"item": "技术方案", "max": 50, "score": 44, "status": "scored", "basis": "技术响应齐全"},
                    {
                        "item": "项目负责人答辩",
                        "max": 10,
                        "score": None,
                        "status": "manual_review",
                        "pending_reason": "live_event",
                        "basis": "现场答辩环节，投标文件不可判定，需现场记录",
                    },
                ],
            },
        ),
    )
    assert out["verdict"] == "manual_review"


# ── 反馈子系统：按 score_mode 软校验（design 第1轮 §5，不一致记 warning 不阻断）──


def _scored_with(extracted: dict, **overrides) -> dict:
    base = _audit_approved(policy_refs=["tender_evalmethod_001"], extracted_data=extracted)
    base.update(overrides)
    return base


def _mismatch_warns(out: dict) -> list:
    """只取算术不一致（score_mode_*_mismatch）告警，剔除 criteria 完整性等其它告警。"""
    warns = out["extracted_data"].get("validation_warnings") or []
    return [w for w in warns if str(w.get("code", "")).endswith("_mismatch")]


def test_expense_explanation_summary_sentence_is_not_stripped():
    """D0: expense 合法结论里的“综上…合计…”不是 tender 得分小结，不应被剥离。"""
    explanation = (
        "发票与审批单一致，金额在预算内。"
        "综上，本次差旅报销合计 1200 元，符合制度规定，予以通过。"
    )
    out = oc.enrich_audit_decision(
        {
            "verdict": "approved",
            "explanation": explanation,
            "extracted_data": {"invoice_no": "fp_2026_0420"},
        }
    )
    assert out["explanation"] == explanation


def test_expense_explanation_keeps_legitimate_underscore_identifier():
    """D0: 非 tender 结论中的发票号/文件名等下划线标识不应被通配替换。"""
    explanation = "发票编号 fp_2026_0420 与审批单一致，予以通过。"
    out = oc.enrich_audit_decision(
        {
            "verdict": "approved",
            "explanation": explanation,
            "extracted_data": {"invoice_no": "fp_2026_0420"},
        }
    )
    assert out["explanation"] == explanation


def test_tender_explanation_score_summary_stays_server_canonical(monkeypatch):
    """D0: tender 结论仍按 scoring[] 重算小结，覆盖模型写错的总分。"""
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with(
            {
                "criteria": _scored_criteria(),
                "scoring": [
                    {
                        "item": "技术方案",
                        "max": 60,
                        "score": 52,
                        "status": "scored",
                        "basis": "技术响应齐全",
                    },
                    {
                        "item": "商务响应",
                        "max": 40,
                        "score": 36,
                        "status": "scored",
                        "basis": "商务条款全部响应",
                    },
                ],
            },
            explanation="投标文件满足要求。综上，评分项总分 999 分。",
        ),
    )
    assert "999" not in out["explanation"]
    assert "得分小结：评分表共 2 项，满分 100 分；已有分数 2 项，合计 88 分。" in out["explanation"]


def test_score_mode_deduction_inconsistent_records_warning(monkeypatch):
    # deduction 项 score≠max−Σ扣 → validation_warnings 记一条，不抛错。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    crit = _scored_criteria()
    crit["items"][0]["score_mode"] = "deduction"
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with(
            {
                "criteria": crit,
                "scoring": [
                    {
                        "item": "技术方案", "max": 60, "score": 55, "status": "scored",
                        "score_mode": "deduction", "basis": "扣10但写成55",
                        "deduction_hits": [
                            {"deduction_id": "d1", "condition": "x", "points_each": 5,
                             "times": 2, "deducted": 10,
                             "evidence": {"source": "投标p1", "quote": "q"}}
                        ],
                    },  # 60−10=50 ≠ 55 → 不一致
                    {"item": "商务响应", "max": 40, "score": 36, "status": "scored", "basis": "ok"},
                ],
            }
        ),
    )
    warns = out["extracted_data"].get("validation_warnings", [])
    assert any(w["item"] == "技术方案" for w in warns), warns


def test_score_mode_deduction_consistent_no_warning(monkeypatch):
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    crit = _scored_criteria()
    crit["items"][0]["score_mode"] = "deduction"
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with(
            {
                "criteria": crit,
                "scoring": [
                    {
                        "item": "技术方案", "max": 60, "score": 50, "status": "scored",
                        "score_mode": "deduction",
                        "deduction_hits": [
                            {"deduction_id": "d1", "condition": "x", "points_each": 5,
                             "times": 2, "deducted": 10,
                             "evidence": {"source": "投标p1", "quote": "q"}}
                        ],
                    },  # 60−10=50 ✓
                    {"item": "商务响应", "max": 40, "score": 36, "status": "scored"},
                ],
            }
        ),
    )
    assert not _mismatch_warns(out)


def test_score_mode_banded_not_treated_as_deduction(monkeypatch):
    # banded 项 score==选档分 → 无 warning；档次分不被当"扣分"误伤（critic F1/F5）。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    crit = _scored_criteria()
    crit["items"][0]["score_mode"] = "banded"
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with(
            {
                "criteria": crit,
                "scoring": [
                    {
                        "item": "技术方案", "max": 60, "score": 42, "status": "scored",
                        "score_mode": "banded",
                        "selected_band": {"level": "良", "points": 42},
                    },
                    {"item": "商务响应", "max": 40, "score": 36, "status": "scored"},
                ],
            }
        ),
    )
    assert not _mismatch_warns(out)


def test_score_mode_skips_null_and_manual(monkeypatch):
    # null/manual_review 项不触发一致性校验（critic F5 skip 路径）。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with(
            {
                "criteria": _mixed_criteria(),
                "scoring": [
                    {"item": "技术方案", "max": 50, "score": 44, "status": "scored", "basis": "无明细不校验"},
                    {"item": "项目负责人答辩", "max": 10, "score": None,
                     "status": "manual_review", "pending_reason": "live_event",
                     "basis": "现场"},
                ],
            },
            verdict="manual_review",
            manual_review_reason="rule_gap",
        ),
    )
    assert not _mismatch_warns(out)


# ── criteria 横比指纹兼容（codex P1.6：v2 加可选字段不得引发 hash 漂移）──────


def test_criteria_hash_ignores_empty_optional_fields():
    # 同标多家：一家输出空容器(deductions:[]/bands:[]/eligibility_rules:[]/rejection_rules:[])一家省略 → 同 hash。
    from server.stores.tender_compare_store import compute_criteria_hash

    a = _scored_criteria()
    a["items"][0]["score_mode"] = "deduction"
    b = _scored_criteria()
    b["items"][0]["score_mode"] = "deduction"
    b["items"][0]["deductions"] = []
    b["items"][0]["bands"] = []
    b["eligibility_rules"] = []
    b["rejection_rules"] = []
    assert compute_criteria_hash(a) == compute_criteria_hash(b)


def test_criteria_hash_differs_on_core_change():
    # 核心评分标准变了（满分）→ 指纹必须不同（防误判一致）。
    from server.stores.tender_compare_store import compute_criteria_hash

    a = _scored_criteria()
    b = _scored_criteria()
    b["items"][0]["max"] = 999
    assert compute_criteria_hash(a) != compute_criteria_hash(b)


def test_criteria_hash_ignores_default_field_values():
    # codex P2-6：显式默认值（evaluator_type:objective / score_mode:deduction）与省略 → 同 hash。
    from server.stores.tender_compare_store import compute_criteria_hash

    a = _scored_criteria()
    b = _scored_criteria()
    b["items"][0]["evaluator_type"] = "objective"
    b["items"][1]["score_mode"] = "deduction"
    assert compute_criteria_hash(a) == compute_criteria_hash(b)


# ── 反馈：criteria 完整性 + score_mode 缺失兜底告警（codex P1-4/P1-5）──────────


def test_criteria_missing_score_mode_warns(monkeypatch):
    # criteria 项未声明 score_mode → validation_warnings 提示按 deduction 兜底。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with(
            {
                "criteria": _scored_criteria(),  # 无 score_mode
                "scoring": [
                    {"item": "技术方案", "max": 60, "score": 52, "status": "scored", "basis": "x"},
                    {"item": "商务响应", "max": 40, "score": 36, "status": "scored", "basis": "y"},
                ],
            }
        ),
    )
    warns = out["extracted_data"].get("validation_warnings", [])
    assert any(w["code"] == "criteria_missing_score_mode" for w in warns), warns


def test_criteria_mode_container_mismatch_warns(monkeypatch):
    # score_mode=deduction 缺 deductions、banded 缺 bands → 各记一条 warning。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    crit = _scored_criteria()
    crit["items"][0]["score_mode"] = "deduction"  # 但不给 deductions
    crit["items"][1]["score_mode"] = "banded"  # 但不给 bands
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with(
            {
                "criteria": crit,
                "scoring": [
                    {"item": "技术方案", "max": 60, "score": 52, "status": "scored", "basis": "x"},
                    {"item": "商务响应", "max": 40, "score": 36, "status": "scored", "basis": "y"},
                ],
            }
        ),
    )
    codes = [w["code"] for w in out["extracted_data"].get("validation_warnings", [])]
    assert "criteria_deduction_missing_deductions" in codes
    assert "criteria_banded_missing_bands" in codes


def test_tender_explanation_is_user_facing_and_score_summary_is_canonical(monkeypatch):
    """出结果时按 scoring[] 重算小结，并清理模型泄漏的内部字段名。"""
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with(
            {
                "criteria": _scored_criteria(),
                "scoring": [
                    {
                        "item": "施工组织设计",
                        "max": 6,
                        "score": 5.0,
                        "status": "scored",
                        "basis": "已有初步分数",
                    },
                    {
                        "item": "业绩",
                        "max": 2,
                        "score": 0,
                        "status": "scored",
                        "score_mode": "pass_fail",
                        "basis": "未提供合格业绩",
                    },
                    {
                        "item": "投标报价",
                        "max": 92,
                        "score": None,
                        "status": "manual_review",
                        "pending_reason": "cross_bid",
                        "basis": "需全部投标报价",
                    },
                ],
            },
            verdict="manual_review",
            manual_review_reason="insufficient_evidence",
            explanation=(
                "价格分公式含cross_bid变量，单家无法闭合。"
                "综上，已判定项合计约5.00分（施工组织设计初评5.05/6 + 业绩0/2）。"
            ),
        ),
    )
    explanation = out["explanation"]
    assert "cross_bid" not in explanation
    assert "manual_review" not in explanation
    assert "5.05/6" not in explanation
    assert "得分小结：评分表共 3 项，满分 100 分；已有分数 2 项，合计 5 分" in explanation
    assert "还有 1 项、共 92 分需要补充信息后确认" in explanation


def test_failed_eligibility_rejected_explanation_skips_score_summary(monkeypatch):
    """资格审查失败时综合意见只说废标，分数保留在明细里。"""
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with(
            {
                "criteria": _scored_criteria(),
                "eligibility_checks": [
                    {
                        "rule_id": "q1",
                        "check": "企业资质证书",
                        "status": "fail",
                        "basis": "未提供招标文件要求的企业资质证书。",
                    }
                ],
                "scoring": [
                    {
                        "item": "施工组织设计",
                        "max": 60,
                        "score": 48,
                        "status": "scored",
                        "basis": "技术方案章节完整。",
                    },
                    {
                        "item": "商务响应",
                        "max": 40,
                        "score": 0,
                        "status": "scored",
                        "basis": "未响应商务条款。",
                    },
                ],
            },
            verdict="manual_review",
            manual_review_reason="insufficient_evidence",
            explanation="未提供招标文件要求的企业资质证书。综上，已有分数项合计 48 分。",
        ),
    )
    assert out["verdict"] == "rejected"
    assert "资格审查不通过，按废标处理" in out["explanation"]
    assert "得分小结" not in out["explanation"]
    assert out["extracted_data"]["scoring"][0]["score"] == 48


# ── C 根因:模型多输出未知顶层字段不再整单被拒(normalize 剥离)──────────────


def test_unknown_top_field_stripped_not_rejected(monkeypatch):
    """模型多带 missing_fields/technical_subtotal → normalize 剥离 → 不被 additionalProperties:false 拒。"""
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _audit_approved(
            missing_fields=["entertainment_target"],
            technical_subtotal=50,
        ),
    )
    assert out["verdict"] == "approved"  # 多字段不再让整单结论被拒
    assert "missing_fields" not in out  # 未知顶层字段已剥离
    assert "technical_subtotal" not in out


def test_scored_zero_demoted_when_disqualified(monkeypatch):
    """A 兜底:整单实质性不响应(disqualification)时,additive 实得0无依据 → 降级 manual_review。"""
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    crit = _scored_criteria()
    crit["items"][0]["score_mode"] = "additive"
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with(
            {
                "criteria": crit,
                "disqualification_hits": [{"rule_id": "x", "finding": "投标未响应本招标"}],
                "scoring": [
                    {"item": "技术方案", "max": 60, "score": 0, "status": "scored",
                     "score_mode": "additive", "basis": "无对应内容"},
                    {"item": "商务响应", "max": 40, "score": 36, "status": "scored"},
                ],
            }
        ),
    )
    tech = next(s for s in out["extracted_data"]["scoring"] if s["item"] == "技术方案")
    assert tech["status"] == "manual_review" and tech["score"] is None  # 投错标→降级
    codes = [w["code"] for w in out["extracted_data"].get("validation_warnings", [])]
    assert "scored_zero_demoted" in codes


def test_scored_zero_no_disq_only_warns(monkeypatch):
    """正常案例(无 disqualification):additive 实得0(可能规则性确认缺失) → 仅 warning 不降级(codex P1-1 防误伤)。"""
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    crit = _scored_criteria()
    crit["items"][0]["score_mode"] = "additive"
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with(
            {
                "criteria": crit,
                "scoring": [
                    {"item": "技术方案", "max": 60, "score": 0, "status": "scored",
                     "score_mode": "additive", "basis": "已核投标无加分材料"},
                    {"item": "商务响应", "max": 40, "score": 36, "status": "scored"},
                ],
            }
        ),
    )
    tech = next(s for s in out["extracted_data"]["scoring"] if s["item"] == "技术方案")
    assert tech["status"] == "scored" and tech["score"] == 0  # 正常案例不降级
    codes = [w["code"] for w in out["extracted_data"].get("validation_warnings", [])]
    assert "scored_zero_suspect" in codes and "scored_zero_demoted" not in codes


def test_passfail_zero_not_demoted(monkeypatch):
    """pass_fail 实得0(客观未满足,有依据) → 不降级,保留 scored。"""
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    crit = _scored_criteria()
    crit["items"][0]["score_mode"] = "pass_fail"
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with(
            {
                "criteria": crit,
                "scoring": [
                    {"item": "技术方案", "max": 60, "score": 0, "status": "scored",
                     "score_mode": "pass_fail", "basis": "未满足一级资质硬性条件"},
                    {"item": "商务响应", "max": 40, "score": 36, "status": "scored"},
                ],
            }
        ),
    )
    tech = next(s for s in out["extracted_data"]["scoring"] if s["item"] == "技术方案")
    assert tech["status"] == "scored" and tech["score"] == 0  # pass_fail 0 是有依据的,不降级


def test_deduction_zero_with_hits_no_suspect(monkeypatch):
    """deduction 真扣减到 0(有明细) → 不报 scored_zero_suspect(合理的扣满)。"""
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    crit = _scored_criteria()
    crit["items"][0]["score_mode"] = "deduction"
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with(
            {
                "criteria": crit,
                "scoring": [
                    {
                        "item": "技术方案", "max": 60, "score": 0, "status": "scored",
                        "score_mode": "deduction",
                        "deduction_hits": [
                            {"deduction_id": "d1", "condition": "全不符", "points_each": 60,
                             "times": 1, "deducted": 60,
                             "evidence": {"source": "投标p1", "quote": "q"}}
                        ],
                    },
                    {"item": "商务响应", "max": 40, "score": 36, "status": "scored"},
                ],
            }
        ),
    )
    tech = next(s for s in out["extracted_data"]["scoring"] if s["item"] == "技术方案")
    assert tech["status"] == "scored" and tech["score"] == 0  # 扣满到0是合理的,不降级
    codes = [w["code"] for w in out["extracted_data"].get("validation_warnings", [])]
    assert "scored_zero_demoted" not in codes


def test_audit_schema_whitelist_no_drift():
    """漂移守卫:_AUDIT_SCHEMA_TOP_FIELDS 必须 == schema 顶层 properties(改 schema 要同步白名单)。"""
    import json as _json

    from server.platform.paths import PROJECT_ROOT

    schema = _json.loads(
        (PROJECT_ROOT / ".claude" / "contracts" / "common" / "audit-result.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert oc._AUDIT_SCHEMA_TOP_FIELDS == set(schema["properties"].keys())


# ── G5 第3轮:formula 公式变量结构化(formula_spec,限价类单家可算)──────────────

# 限价类:变量全 tender_constant + bid_component → 可单家闭合代入算分。
_CLOSED_FORMULA_SPEC = {
    "expression": "score = min(cap, floor((limit - bid) / limit * 100))",
    "variables": [
        {"name": "limit", "source": "tender_constant", "value": 300,
         "unit": "元/用户·月", "ref": "招标文件第21页限价表"},
        {"name": "bid", "source": "bid_component", "value": 270,
         "unit": "元/用户·月", "ref": "投标文件第6页报价表"},
    ],
    "rounding": "floor",
    "cap": 10,
}
# 横比类:含 cross_bid 群体变量 → 单家算不了,应 manual_review。
_CROSS_FORMULA_SPEC = {
    "expression": "score = lowest / bid * 40",
    "variables": [
        {"name": "lowest", "source": "cross_bid", "value": None, "ref": None},
        {"name": "bid", "source": "bid_component", "value": 270, "ref": "投标文件第6页"},
    ],
}


def _formula_criteria(formula_spec) -> dict:
    """单 formula 价格项(可选 formula_spec) + 一个普通 scored 项的会话评分标准。"""
    item = {
        "item": "价格分", "max": 10,
        "scoring_rule": "每低于最高限价1%得1分，最多10分",
        "source_ref": "评标办法 p.21", "tag": "scored", "score_mode": "formula",
        "formula": "每低于最高限价1%得1分，最多10分",
    }
    if formula_spec is not None:
        item["formula_spec"] = formula_spec
    return {
        "source_ref": "招标文件 评标办法 p.18", "method": "综合评估法", "total_max": 50,
        "items": [
            item,
            {"item": "商务响应", "max": 40, "scoring_rule": "按商务条款响应评分",
             "source_ref": "p.20", "tag": "scored", "score_mode": "deduction", "deductions": []},
        ],
    }


def _formula_scoring(status: str = "scored", score=10) -> list:
    price_item = {"item": "价格分", "max": 10, "score": score, "status": status,
                  "score_mode": "formula",
                  "basis": "限价300、本家270、(300−270)/300=10%、floor得10分"}
    if score is None:
        price_item["pending_reason"] = "cross_bid"  # KD5：score=null 必带待定原因
    return [
        price_item,
        {"item": "商务响应", "max": 40, "score": 36, "status": "scored",
         "score_mode": "deduction", "basis": "全响应"},
    ]


def _formula_warns(out: dict) -> list:
    warns = out["extracted_data"].get("validation_warnings") or []
    return [w["code"] for w in warns if str(w.get("code", "")).startswith("formula_")]


def test_criteria_formula_spec_validates():
    # formula_spec(expression+variables[source/value/unit/ref]+rounding+cap)通过 criteria 形校验。
    jsonschema.validate(_formula_criteria(_CLOSED_FORMULA_SPEC), load_output_schema(CRITERIA_SCHEMA))


def test_criteria_formula_spec_rejects_bad_source():
    # variables[].source 是枚举:乱造 → 拒(让验证闸能拦 tag 派生漂移,codex F4)。
    crit = _formula_criteria(_CLOSED_FORMULA_SPEC)
    crit["items"][0]["formula_spec"] = {
        "expression": "x", "variables": [{"name": "v", "source": "magic_source"}],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(crit, load_output_schema(CRITERIA_SCHEMA))


def test_criteria_formula_spec_rejects_missing_required():
    # formula_spec 缺 required(variables) → 拒。
    crit = _formula_criteria(_CLOSED_FORMULA_SPEC)
    crit["items"][0]["formula_spec"] = {"expression": "x"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(crit, load_output_schema(CRITERIA_SCHEMA))


def test_formula_scored_closed_spec_no_warning(monkeypatch):
    # 限价类 formula 全变量闭合(tender_constant+bid_component)判 scored → 无 formula warning(正确单家算分)。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with({"criteria": _formula_criteria(_CLOSED_FORMULA_SPEC),
                      "scoring": _formula_scoring()}),
    )
    assert not _formula_warns(out)


def test_formula_scored_no_spec_warns(monkeypatch):
    # formula 判 scored 但缺 formula_spec → formula_scored_no_spec(治"回退临场心算",codex P1-3)。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with({"criteria": _formula_criteria(None),
                      "scoring": _formula_scoring()}),
    )
    assert "formula_scored_no_spec" in _formula_warns(out)


def test_formula_scored_not_closeable_warns(monkeypatch):
    # formula 判 scored 但 spec 含 cross_bid 群体变量 → formula_scored_not_closeable(本应 manual_review)。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with({"criteria": _formula_criteria(_CROSS_FORMULA_SPEC),
                      "scoring": _formula_scoring()}),
    )
    assert "formula_scored_not_closeable" in _formula_warns(out)


def test_formula_manual_review_no_warning(monkeypatch):
    # formula 正确判 manual_review(横比降级,不判 scored)→ 不进 scored 校验,无 formula warning。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with(
            {"criteria": _formula_criteria(_CROSS_FORMULA_SPEC),
             "scoring": _formula_scoring(status="manual_review", score=None)},
            verdict="manual_review", manual_review_reason="insufficient_evidence",
        ),
    )
    assert not _formula_warns(out)


def test_formula_scored_missing_value_warns(monkeypatch):
    # codex P1-1:formula scored,变量 source 全可闭合但有 value 未填(缺限价/本家报价)→ missing_value warning。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    import copy

    spec = copy.deepcopy(_CLOSED_FORMULA_SPEC)
    spec["variables"][1]["value"] = None  # 本家报价没抽到
    out = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        _scored_with({"criteria": _formula_criteria(spec), "scoring": _formula_scoring()}),
    )
    assert "formula_scored_missing_value" in _formula_warns(out)


def test_criteria_hash_ignores_bid_value_in_formula_spec():
    # codex P1-2:同招标两家,formula_spec 标准(expression/变量结构)相同,只 S2 回填的本家报价 value/ref
    # 不同 → 必须同 hash(本家数据不属核心标准,不能让报价差异引发横比 stale 误判)。
    import copy

    from server.stores.tender_compare_store import compute_criteria_hash

    a = _formula_criteria(copy.deepcopy(_CLOSED_FORMULA_SPEC))
    b = _formula_criteria(copy.deepcopy(_CLOSED_FORMULA_SPEC))
    b["items"][0]["formula_spec"]["variables"][1]["value"] = 250  # 本家报价不同
    b["items"][0]["formula_spec"]["variables"][1]["ref"] = "投标文件第8页"
    assert compute_criteria_hash(a) == compute_criteria_hash(b)


def test_criteria_hash_differs_on_formula_standard():
    # codex P1-2:但 formula 标准本身变(cap/expression)→ hash 必须不同(标准侧保留,不能排整个 spec 漏判 stale)。
    import copy

    from server.stores.tender_compare_store import compute_criteria_hash

    a = _formula_criteria(copy.deepcopy(_CLOSED_FORMULA_SPEC))
    b = _formula_criteria(copy.deepcopy(_CLOSED_FORMULA_SPEC))
    b["items"][0]["formula_spec"]["cap"] = 20  # 评分标准变了
    assert compute_criteria_hash(a) != compute_criteria_hash(b)
