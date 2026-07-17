"""F6: server.tender.output 直接单测（从 output_contracts 抽离的 tender 专属逻辑，T2 搬家）。

锁定：① tender-only 后处理不误伤 expense；② 废标/资格 gate 的 confirmed/eligibility 语义；
③ 得分小结重算；④ 评分一致性闸（硬拒超量纲 / 软告警 score_mode 不一致 / 可选 plan 丢弃）。
"""

from __future__ import annotations

import subprocess
import sys

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
