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
    DEFAULT_OUTPUT_SCHEMA_NAME,
    JSONContractError,
    apply_schema_semantics,
    load_output_schema,
)
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


# ── criteria 随结论进出口闸 + 真伪闸对齐（design §4 方案 A）────────────────


def test_audit_with_criteria_passes_with_statute_policy_ref(monkeypatch):
    # 承重 approved：policy_refs 引通则层真实 rule_id → 过真伪闸；criteria 随 extracted_data 保留。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    out = apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, _audit_approved())
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
            DEFAULT_OUTPUT_SCHEMA_NAME,
            _audit_approved(policy_refs=["tender_r2024007_004"]),
        )


def test_unjudgeable_item_null_score_passes(monkeypatch):
    # 不可判定项（现场答辩）score:null + 整体 manual_review → 出口闸放行（"绝不判 0"）。
    monkeypatch.setenv("RULE_REF_CHECK", "1")
    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: _TENDER_KNOWN)
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
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
                        "basis": "现场答辩环节，投标文件不可判定，需现场记录",
                    },
                ],
            },
        ),
    )
    assert out["verdict"] == "manual_review"
