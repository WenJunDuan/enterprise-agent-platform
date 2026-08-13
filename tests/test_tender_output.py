"""F6: server.tender.output 直接单测（从 output_contracts 抽离的 tender 专属逻辑，T2 搬家）。

锁定：① tender-only 后处理不误伤 expense；② 废标/资格 gate 的 confirmed/eligibility 语义；
③ 得分小结重算；④ 评分一致性闸（硬拒超量纲 / 软告警 score_mode 不一致 / 可选 plan 丢弃）。
"""

from __future__ import annotations

import subprocess
import sys
from copy import deepcopy

import pytest

from server.common.contract import JSONContractError
from server.tender import output as to


def test_tender_output_independently_importable():
    """S4 review P2: 全新解释器里**首个** import server.tender.output 必须成功。

    防 contract → output_contracts → tender.output → contract 的模块加载期环回归（本测试文件本身
    先 import 了 contract，会 preload 安全顺序而掩盖该 bug，故用独立子进程在干净 sys.modules 下验证）。
    """
    result = subprocess.run(
        [sys.executable, "-c", "import server.tender.output"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# ── tender-only guard：不误伤 expense ──────────────────────────────────────────────
def test_is_tender_output_true_for_scoring_or_eligibility():
    assert to._is_tender_explanation_output({"extracted_data": {"scoring": []}}) is True
    assert to._is_tender_explanation_output({"extracted_data": {"eligibility_checks": []}}) is True


def test_finalize_explanation_leaves_expense_untouched():
    # expense 结论无 scoring/eligibility → explanation 原样不动（D0 跨域污染防回归）。
    out = {
        "verdict": "approved",
        "explanation": "发票与审批单一致。综上，本次报销合计 1200 元，予以通过。",
        "extracted_data": {"invoice_no": "fp_2026_0420"},
    }
    to._finalize_user_explanation(out)
    assert out["explanation"] == "发票与审批单一致。综上，本次报销合计 1200 元，予以通过。"


def test_finalize_explanation_appends_server_score_summary():
    out = {
        "verdict": "approved",
        "explanation": "各项均按评标办法判定。综上，合计 86 分。",
        "extracted_data": {"scoring": [
            {"item": "业绩", "max": 30, "score": 27},
            {"item": "技术", "max": 40, "score": 35},
            {"item": "价格", "max": 30, "score": None},
        ]},
    }
    to._finalize_user_explanation(out)
    assert "得分小结：" in out["explanation"]
    assert "合计 62 分" in out["explanation"]  # 27+35，服务端重算覆盖模型写错的 86
    assert "30 分需要补充信息后确认" in out["explanation"]


def test_score_summary_preserves_unknown_max_count_without_claiming_complete_total():
    out = {
        "verdict": "manual_review",
        "explanation": "已有七项完成评分。",
        "extracted_data": {
            "scoring": [
                *[
                    {"item": f"数值项{i}", "max": 10, "score": 8, "status": "scored"}
                    for i in range(1, 8)
                ],
                {
                    "item": "现场答辩",
                    "max": None,
                    "score": None,
                    "status": "manual_review",
                },
                {
                    "item": "外部信用",
                    "max": None,
                    "score": None,
                    "status": "manual_review",
                },
            ]
        },
    }

    to._finalize_user_explanation(out)

    assert "评分表共 9 项" in out["explanation"]
    assert "已知满分 70 分" in out["explanation"]
    assert "2 项未设满分" in out["explanation"]
    assert "满分 70 分" not in out["explanation"].replace("已知满分 70 分", "")


def test_finalize_explanation_rejected_eligibility_prefix():
    out = {
        "verdict": "rejected",
        "explanation": "投标无有效资质。",
        "extracted_data": {
            "eligibility_checks": [{"check": "资质", "status": "fail", "basis": "缺二级资质"}],
            "scoring": [{"item": "技术", "max": 40, "score": 20}],
        },
    }
    to._finalize_user_explanation(out)
    assert out["explanation"].startswith("资格审查不通过，按废标处理。")
    assert "得分小结：" not in out["explanation"]  # 废标 → 不附得分小结


# ── 废标/资格 gate 语义 ────────────────────────────────────────────────────────────
def test_has_hard_disqualification_confirmed_vs_unconfirmed():
    assert to._has_hard_disqualification({"disqualification_hits": [{"finding": "逾期", "confirmed": True}]}) is True
    # confirmed:false（疑似/读不清）不触发废标（R2b 纪律）
    assert to._has_hard_disqualification({"disqualification_hits": [{"finding": "疑似", "confirmed": False}]}) is False
    assert to._has_hard_disqualification({"eligibility_checks": [{"status": "fail"}]}) is True
    assert to._has_hard_disqualification({"invoice_no": "x"}) is False  # expense 无此结构


def test_hit_unconfirmed_backward_compat():
    assert to._hit_unconfirmed({"finding": "x"}) is False  # 无 confirmed → 视为已确认
    assert to._hit_unconfirmed({"confirmed": False}) is True
    assert to._hit_unconfirmed({"confirmed": "疑似"}) is True


# ── 评分一致性闸 ───────────────────────────────────────────────────────────────────
def test_verify_scoring_consistency_rejects_out_of_range():
    with pytest.raises(JSONContractError):
        to._verify_scoring_consistency({"extracted_data": {"scoring": [{"item": "x", "max": 10, "score": 15}]}})


def test_verify_score_mode_consistency_warns_not_raises():
    out = {"extracted_data": {
        "criteria": {"items": [{"item": "技术", "score_mode": "deduction", "deductions": []}]},
        "scoring": [{"item": "技术", "max": 10, "score": 4, "status": "scored", "deduction_hits": []}],
    }}
    to._verify_score_mode_consistency(out)  # 不抛
    warnings = out["extracted_data"].get("validation_warnings")
    assert isinstance(warnings, list) and any(w["code"] == "deduction_scored_no_hits" for w in warnings)


def test_normalize_optional_plan_drops_invalid():
    out = {"extracted_data": {"plan": {"not": "valid-plan-shape"}}}
    to._normalize_optional_plan(out)
    assert "plan" not in out["extracted_data"]  # 形不对的可选 plan 丢弃，不抛


def test_normalize_tender_result_stamps_tender_reviewer():
    out = to.normalize_tender_result({"verdict": "manual_review"})
    assert out["reviewed_by"] == "tender-evaluator"


def _scoring_hit(*, awarded: int, source: str, quote: str) -> dict:
    return {
        "award_id": "性能参数",
        "awarded": awarded,
        "evidence": {"source": source, "quote": quote},
    }


@pytest.mark.parametrize("chain", [None, [], [{"source": "", "finding": "", "conclusion": ""}]])
def test_enrich_derives_evidence_chain_for_empty_chain(chain):
    out = {
        "verdict": "approved",
        "evidence_chain": chain,
        "extracted_data": {
            "scoring": [
                {
                    "item": "技术参数",
                    "basis": "性能参数满足要求，得 3 分",
                    "award_hits": [_scoring_hit(awarded=3, source="投标文件第6页", quote="塔吊两台")],
                }
            ]
        },
    }
    to.enrich_tender_result(out)
    assert out["evidence_chain"] == [
        {
            "source": "投标文件第6页",
            "finding": "塔吊两台",
            "conclusion": "性能参数满足要求，得 3 分",
        }
    ]


def test_enrich_derives_when_chain_is_missing():
    out = {
        "verdict": "approved",
        "extracted_data": {
            "scoring": [
                {
                    "item": "业绩",
                    "basis": "符合业绩要求，得 2 分",
                    "award_hits": [_scoring_hit(awarded=2, source="投标文件第12页", quote="合同金额")],
                }
            ]
        },
    }
    to.enrich_tender_result(out)
    assert out["evidence_chain"][0]["source"] == "投标文件第12页"


def test_enrich_does_not_overwrite_nonempty_evidence_chain():
    existing = [{"source": "招标文件第3页", "finding": "评分办法", "conclusion": "按该办法评分"}]
    out = {
        "verdict": "approved",
        "evidence_chain": deepcopy(existing),
        "extracted_data": {
            "scoring": [
                {
                    "basis": "不应覆盖",
                    "award_hits": [_scoring_hit(awarded=2, source="投标文件第12页", quote="合同金额")],
                }
            ]
        },
    }
    to.enrich_tender_result(out)
    assert out["evidence_chain"] == existing


def test_enrich_skips_missing_scoring():
    out = {"verdict": "approved", "evidence_chain": []}
    to.enrich_tender_result(out)
    assert out["evidence_chain"] == []


def test_enrich_prioritizes_nonzero_hit_and_preserves_page_anchor():
    out = {
        "verdict": "approved",
        "evidence_chain": [],
        "extracted_data": {
            "scoring": [
                {
                    "basis": "基础分与加分均已核对",
                    "award_hits": [
                        _scoring_hit(awarded=0, source="投标文件第4页", quote="常规参数"),
                        _scoring_hit(awarded=3, source="投标文件第18页【第18页】", quote="检测报告") ,
                    ],
                }
            ]
        },
    }
    to.enrich_tender_result(out)
    assert out["evidence_chain"][0]["source"] == "投标文件第18页【第18页】"
    assert out["evidence_chain"][1]["source"] == "投标文件第4页"


def test_unresolved_derived_evidence_does_not_change_verdict_or_scoring(monkeypatch):
    from server.common.contract import apply_schema_semantics
    from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME

    monkeypatch.setattr("server.common.output_contracts._load_known_rule_ids", lambda: set())
    before = {
        "status": "scored",
        "score": 3,
        "award_hits": [
            {
                "awarded": 3,
                "source": "投标文件第99页",
                "finding": "底稿不存在的原文",
                "conclusion": "该项得 3 分",
            }
        ],
    }
    out = {
        "claim_id": "T-1",
        "verdict": "approved",
        "explanation": "评分完成",
        "reasons": [],
        "policy_refs": ["tender_evalmethod_001"],
        "risk_score": 20,
        "extracted_data": {"scoring": [deepcopy(before)]},
        "evidence_chain": [],
        "reviewed_by": "tender-evaluator",
        "timestamp": "2026-06-22T00:00:00Z",
    }

    result = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        out,
        evidence_source="### 文件: 投标文件.pdf\n【第 1 页】\n其他内容",
    )

    assert result["evidence_chain"][0]["resolution"]["status"] == "unresolved"
    assert result["verdict"] == "approved"
    assert result["extracted_data"]["scoring"][0] == before


def test_second_enrich_after_downgrade_does_not_duplicate_derived_evidence(monkeypatch):
    """F4 回归守卫：unresolved 承重 award_hit → downgrade → verdict 翻 manual_review →
    ``evidence.py`` 在 verdict 翻转时二次调 ``enrich_tender_result``；空链派生须幂等——只派生
    一次、无重复条目（防 lazy-import seam 静默失真复发，见
    compound/2026-07-18-learning-lazy-import-behavioral-seam）。"""
    from server.common.contract import apply_schema_semantics
    from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME

    monkeypatch.setenv("EVIDENCE_RESOLUTION_DOWNGRADE", "1")
    monkeypatch.setattr("server.common.output_contracts._load_known_rule_ids", lambda: set())
    out = {
        "claim_id": "T-F4",
        "verdict": "approved",
        "explanation": "评分完成，得 21 分",
        "reasons": [],
        "policy_refs": ["tender_evalmethod_001"],
        "risk_score": 20,
        "extracted_data": {
            "scoring": [
                {
                    "item": "技术参数指标",
                    "max": 25,
                    "score": 21,
                    "status": "scored",
                    "score_mode": "additive",
                    "award_hits": [
                        _scoring_hit(awarded=21, source="投标文件第6页【第6页】", quote="不可核验的承重原文"),
                    ],
                }
            ]
        },
        "evidence_chain": [],
        "reviewed_by": "tender-evaluator",
        "timestamp": "2026-06-22T00:00:00Z",
    }

    result = apply_schema_semantics(
        TENDER_OUTPUT_SCHEMA_NAME,
        out,
        evidence_source="### 文件: 投标文件.pdf\n【第 1 页】\n完全不含承重引文的其他内容",
    )

    # 承重 award_hit 核不实 → 降级 → verdict 翻 manual_review → 触发 evidence.py 二次 enrich
    assert result["verdict"] == "manual_review"
    assert result["extracted_data"]["scoring"][0]["score"] is None
    # F4 核心：二次 enrich 幂等，空链只派生一次、无重复条目
    assert len(result["evidence_chain"]) == 1
    assert result["evidence_chain"][0]["finding"] == "不可核验的承重原文"


# ── T5 (G2/F3): 自注册回归 —— 隔离子进程，不被同进程内其它测试的 import 顺序掩盖 ──────


def test_package_import_registers_tender_schema():
    """G2/F3: importing the server.tender package (any submodule) must self-register
    TENDER_OUTPUT_SCHEMA_NAME -- proven in a fresh interpreter so no other test's import
    order can accidentally pre-warm the registry."""
    code = (
        "import server.tender\n"
        "from server.common.contract import _SCHEMA_PROCESSORS\n"
        "from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME\n"
        "assert TENDER_OUTPUT_SCHEMA_NAME in _SCHEMA_PROCESSORS, "
        "'server.tender import did not self-register the tender schema processor'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_cli_import_registers_tender_schema():
    """G2: the CLI entrypoint specifically must trigger self-registration -- this is the
    exact gap Round-2 critic flagged (cli.py->command_adapter->json_bridge->contract had zero
    server.tender import). Importing server.cli in a fresh interpreter must be enough."""
    code = (
        "import server.cli\n"
        "from server.common.contract import _SCHEMA_PROCESSORS\n"
        "from server.tender.output import TENDER_OUTPUT_SCHEMA_NAME\n"
        "assert TENDER_OUTPUT_SCHEMA_NAME in _SCHEMA_PROCESSORS, "
        "'importing server.cli did not self-register the tender schema processor'\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
