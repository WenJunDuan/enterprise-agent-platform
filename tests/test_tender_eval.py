"""Offline coverage for the tender golden-case eval harness (D1 T1/T2).

Mirrors ``tests/test_audit_eval.py``: the pure scoring/parsing/consistency/reporting
surface is fully covered offline; the live-gateway runner (``run_eval``/CLI ``main``)
needs a real model gateway and is only smoke-checked via monkeypatching
``run_tender_evaluation``. The committed manifest fixture check lands in D1 T4.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from server.tender.eval import (
    CaseOutcome,
    CaseReport,
    ConsistencyOutcome,
    EligibilityExpectation,
    GoldenTenderCase,
    ScoringExpectation,
    format_report,
    load_golden_manifest,
    main,
    parse_golden_cases,
    run_eval,
    score_case,
    score_consistency,
)


# ── manifest parsing ──────────────────────────────────────────────────────────


def test_parse_golden_cases_valid() -> None:
    cases = parse_golden_cases(
        {
            "cases": [
                {"case_dir": "data/t1", "expected_verdict": "approved"},
                {
                    "case_dir": "data/t2",
                    "expected_verdict": "manual_review",
                    "expected_manual_review_reason": "rule_gap",
                    "eligibility_expectations": [
                        {"check": "营业执照", "expected_status": "pass"}
                    ],
                    "scoring_expectations": [
                        {"item": "技术方案", "expected_statuses": ["scored"]}
                    ],
                    "min_total_score": 60,
                    "max_total_score": 90,
                    "require_policy_refs": False,
                    "max_item_spread": 2,
                    "max_total_spread": 10,
                    "repeat": 5,
                    "note": "n",
                },
            ]
        }
    )
    assert [c.case_dir for c in cases] == ["data/t1", "data/t2"]
    second = cases[1]
    assert second.expected_manual_review_reason == "rule_gap"
    assert second.eligibility_expectations == (
        EligibilityExpectation(check="营业执照", expected_status="pass"),
    )
    assert second.scoring_expectations == (
        ScoringExpectation(item="技术方案", expected_statuses=("scored",)),
    )
    assert (second.min_total_score, second.max_total_score) == (60, 90)
    assert second.require_policy_refs is False
    assert (second.max_item_spread, second.max_total_spread) == (2, 10)
    assert second.repeat == 5


def test_parse_golden_cases_defaults() -> None:
    cases = parse_golden_cases({"cases": [{"case_dir": "d", "expected_verdict": "approved"}]})
    case = cases[0]
    assert case.require_policy_refs is True
    assert case.repeat == 3
    assert case.eligibility_expectations == ()
    assert case.scoring_expectations == ()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"cases": []},
        {"cases": "nope"},
        {"cases": [42]},
        {"cases": [{"expected_verdict": "approved"}]},  # missing case_dir
        {"cases": [{"case_dir": "d", "expected_verdict": "bogus"}]},
        {"cases": [{"case_dir": "d"}]},  # missing verdict
    ],
)
def test_parse_golden_cases_rejects_bad_payloads(payload: dict) -> None:
    with pytest.raises(ValueError):
        parse_golden_cases(payload)


def test_load_golden_manifest_rejects_non_object_root(tmp_path: Path) -> None:
    bad = tmp_path / "m.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_golden_manifest(bad)


# ── score_case: verdict / manual_review_reason ────────────────────────────────


def test_score_case_verdict_match_passes() -> None:
    g = GoldenTenderCase(case_dir="d", expected_verdict="approved", require_policy_refs=False)
    outcome = score_case(g, {"verdict": "approved"})
    assert outcome.passed
    assert outcome.mismatches == []


def test_score_case_verdict_mismatch() -> None:
    g = GoldenTenderCase(case_dir="d", expected_verdict="approved", require_policy_refs=False)
    outcome = score_case(g, {"verdict": "rejected"})
    assert not outcome.passed
    assert "verdict" in outcome.mismatches[0]


def test_score_case_reason_mismatch() -> None:
    g = GoldenTenderCase(
        case_dir="d",
        expected_verdict="manual_review",
        expected_manual_review_reason="rule_gap",
        require_policy_refs=False,
    )
    outcome = score_case(
        g, {"verdict": "manual_review", "manual_review_reason": "data_conflict"}
    )
    assert not outcome.passed
    assert any("manual_review_reason" in m for m in outcome.mismatches)


def test_score_case_reason_not_checked_when_unset() -> None:
    g = GoldenTenderCase(case_dir="d", expected_verdict="manual_review", require_policy_refs=False)
    outcome = score_case(g, {"verdict": "manual_review", "manual_review_reason": "rule_gap"})
    assert outcome.passed


# ── score_case: eligibility_checks ─────────────────────────────────────────────


def test_score_case_eligibility_match_passes() -> None:
    g = GoldenTenderCase(
        case_dir="d",
        expected_verdict="approved",
        require_policy_refs=False,
        eligibility_expectations=(EligibilityExpectation(check="营业执照", expected_status="pass"),),
    )
    actual = {
        "verdict": "approved",
        "extracted_data": {"eligibility_checks": [{"check": "营业执照", "status": "pass"}]},
    }
    assert score_case(g, actual).passed


def test_score_case_eligibility_mismatch_fails() -> None:
    g = GoldenTenderCase(
        case_dir="d",
        expected_verdict="approved",
        require_policy_refs=False,
        eligibility_expectations=(EligibilityExpectation(check="营业执照", expected_status="pass"),),
    )
    actual = {
        "verdict": "approved",
        "extracted_data": {"eligibility_checks": [{"check": "营业执照", "status": "fail"}]},
    }
    outcome = score_case(g, actual)
    assert not outcome.passed
    assert any("营业执照" in m for m in outcome.mismatches)


def test_score_case_eligibility_missing_check_fails() -> None:
    g = GoldenTenderCase(
        case_dir="d",
        expected_verdict="approved",
        require_policy_refs=False,
        eligibility_expectations=(EligibilityExpectation(check="安全生产许可证", expected_status="pass"),),
    )
    actual = {"verdict": "approved", "extracted_data": {"eligibility_checks": []}}
    outcome = score_case(g, actual)
    assert not outcome.passed


# ── score_case: scoring[] status + bandwidth ───────────────────────────────────


def test_score_case_scoring_status_match_passes() -> None:
    g = GoldenTenderCase(
        case_dir="d",
        expected_verdict="approved",
        require_policy_refs=False,
        scoring_expectations=(ScoringExpectation(item="技术方案", expected_statuses=("scored",)),),
    )
    actual = {
        "verdict": "approved",
        "extracted_data": {"scoring": [{"item": "技术方案", "max": 60, "score": 45, "status": "scored"}]},
    }
    assert score_case(g, actual).passed


def test_score_case_scoring_status_mismatch_fails() -> None:
    g = GoldenTenderCase(
        case_dir="d",
        expected_verdict="approved",
        require_policy_refs=False,
        scoring_expectations=(ScoringExpectation(item="技术方案", expected_statuses=("scored",)),),
    )
    actual = {
        "verdict": "approved",
        "extracted_data": {
            "scoring": [{"item": "技术方案", "max": 60, "score": None, "status": "manual_review"}]
        },
    }
    outcome = score_case(g, actual)
    assert not outcome.passed
    assert any("技术方案" in m for m in outcome.mismatches)


def test_score_case_total_score_within_band_passes() -> None:
    g = GoldenTenderCase(
        case_dir="d",
        expected_verdict="approved",
        require_policy_refs=False,
        min_total_score=60,
        max_total_score=90,
    )
    actual = {
        "verdict": "approved",
        "extracted_data": {"scoring": [{"item": "a", "max": 100, "score": 75, "status": "scored"}]},
    }
    outcome = score_case(g, actual)
    assert outcome.passed
    assert outcome.total_score == 75
    assert outcome.scored_item_count == 1


def test_score_case_total_score_below_band_fails() -> None:
    g = GoldenTenderCase(
        case_dir="d", expected_verdict="approved", require_policy_refs=False, min_total_score=60
    )
    actual = {
        "verdict": "approved",
        "extracted_data": {"scoring": [{"item": "a", "max": 100, "score": 10, "status": "scored"}]},
    }
    assert not score_case(g, actual).passed


def test_score_case_null_scores_excluded_from_total() -> None:
    """null（不可判定）分不计入合计/项数——round1 F2 语义。"""
    g = GoldenTenderCase(case_dir="d", expected_verdict="manual_review", require_policy_refs=False)
    actual = {
        "verdict": "manual_review",
        "extracted_data": {
            "scoring": [
                {"item": "a", "max": 60, "score": 40, "status": "scored"},
                {"item": "b", "max": 40, "score": None, "status": "manual_review"},
            ]
        },
    }
    outcome = score_case(g, actual)
    assert outcome.total_score == 40
    assert outcome.scored_item_count == 1


# ── score_case: policy_refs hard rule ──────────────────────────────────────────


def test_score_case_policy_refs_required_and_empty_fails() -> None:
    g = GoldenTenderCase(case_dir="d", expected_verdict="approved")  # require_policy_refs defaults True
    outcome = score_case(g, {"verdict": "approved", "policy_refs": []})
    assert not outcome.passed
    assert any("policy_refs" in m for m in outcome.mismatches)


def test_score_case_policy_refs_required_and_present_passes() -> None:
    g = GoldenTenderCase(case_dir="d", expected_verdict="approved")
    outcome = score_case(g, {"verdict": "approved", "policy_refs": ["evalmethod-3"]})
    assert outcome.passed


def test_score_case_policy_refs_not_required_skips_check() -> None:
    g = GoldenTenderCase(case_dir="d", expected_verdict="approved", require_policy_refs=False)
    outcome = score_case(g, {"verdict": "approved", "policy_refs": []})
    assert outcome.passed


def test_score_case_accumulates_multiple_mismatches() -> None:
    g = GoldenTenderCase(case_dir="d", expected_verdict="approved", min_total_score=80)
    outcome = score_case(g, {"verdict": "rejected", "policy_refs": [], "extracted_data": {}})
    # verdict mismatch + min_total_score mismatch + policy_refs mismatch
    assert len(outcome.mismatches) == 3


# ── score_consistency ───────────────────────────────────────────────────────────


def _scoring_payload(*items: tuple[str, float | None]) -> dict:
    return {
        "verdict": "manual_review",
        "extracted_data": {
            "scoring": [
                {"item": name, "max": 100, "score": score, "status": "scored" if score is not None else "manual_review"}
                for name, score in items
            ]
        },
    }


def test_score_consistency_computes_spreads() -> None:
    g = GoldenTenderCase(case_dir="d", expected_verdict="manual_review")
    runs = [
        _scoring_payload(("a", 40), ("b", 20)),
        _scoring_payload(("a", 41), ("b", 25)),
        _scoring_payload(("a", 30), ("b", 19)),
    ]
    outcome = score_consistency(g, runs)
    assert outcome.run_count == 3
    assert outcome.item_counts == [2, 2, 2]
    assert outcome.item_spread == 0
    assert outcome.total_scores == [60, 66, 49]
    assert outcome.total_spread == pytest.approx(17)
    assert not outcome.skipped


def test_score_consistency_all_null_run_counts_as_zero_and_widens_spread() -> None:
    """S7 案例B 崩塌形态：全 null run 记 0/0，正应撑大极差被闸看见（round1 F2）。"""
    g = GoldenTenderCase(case_dir="d", expected_verdict="manual_review")
    runs = [
        _scoring_payload(("a", 40), ("b", 20)),
        _scoring_payload(("a", 41), ("b", 25)),
        _scoring_payload(("a", None), ("b", None)),  # 全 null 崩塌
    ]
    outcome = score_consistency(g, runs)
    assert outcome.item_counts == [2, 2, 0]
    assert outcome.total_scores == [60, 66, 0]
    assert outcome.item_spread == 2
    assert outcome.total_spread == pytest.approx(66)


def test_score_consistency_warning_mode_does_not_fail_on_exceeded_spread() -> None:
    """首版警告模式：超标只记 warnings，不置整体失败（design round1 F4 止损前）。"""
    g = GoldenTenderCase(
        case_dir="d",
        expected_verdict="manual_review",
        max_item_spread=1,
        max_total_spread=5,
    )
    runs = [
        _scoring_payload(("a", 40), ("b", 20)),
        _scoring_payload(("a", None), ("b", None)),
    ]
    outcome = score_consistency(g, runs)
    assert outcome.item_spread_exceeded is True
    assert outcome.total_spread_exceeded is True
    assert outcome.warnings  # recorded, not raised/failed


def test_score_consistency_within_threshold_no_warnings() -> None:
    g = GoldenTenderCase(
        case_dir="d", expected_verdict="manual_review", max_item_spread=0, max_total_spread=20
    )
    runs = [_scoring_payload(("a", 40)), _scoring_payload(("a", 45))]
    outcome = score_consistency(g, runs)
    assert outcome.item_spread_exceeded is False
    assert outcome.total_spread_exceeded is False
    assert outcome.warnings == []


@pytest.mark.parametrize("runs", [[], [_scoring_payload(("a", 40))]])
def test_score_consistency_repeat_below_two_is_skipped_gracefully(runs) -> None:
    """round2 F7 边界：repeat<2 不崩、不算伪极差，标记 skipped。"""
    g = GoldenTenderCase(case_dir="d", expected_verdict="manual_review")
    outcome = score_consistency(g, runs)
    assert outcome.skipped is True
    assert outcome.item_spread == 0
    assert outcome.total_spread == 0
    assert outcome.warnings == []


# ── reporting ─────────────────────────────────────────────────────────────────


def test_format_report_counts_and_marks() -> None:
    reports = [
        CaseReport(
            case_dir="a",
            run_outcomes=[CaseOutcome("a", True, "approved")],
            consistency=ConsistencyOutcome(
                run_count=1, item_counts=[], total_scores=[], item_spread=0, total_spread=0,
                item_spread_exceeded=False, total_spread_exceeded=False, skipped=True,
            ),
        ),
        CaseReport(
            case_dir="b",
            run_outcomes=[CaseOutcome("b", False, "rejected", mismatches=["verdict: ..."])],
            consistency=ConsistencyOutcome(
                run_count=1, item_counts=[], total_scores=[], item_spread=0, total_spread=0,
                item_spread_exceeded=False, total_spread_exceeded=False, skipped=True,
            ),
        ),
        CaseReport(case_dir="c", run_outcomes=[], consistency=None, errors=["Timeout"]),
    ]
    report = format_report(reports)
    assert "1/3 passed" in report
    assert "[PASS]" in report and "a" in report
    assert "[FAIL]" in report
    assert "[ERROR] c" in report


def test_format_report_surfaces_consistency_warnings() -> None:
    reports = [
        CaseReport(
            case_dir="a",
            run_outcomes=[CaseOutcome("a", True, "manual_review")],
            consistency=ConsistencyOutcome(
                run_count=2, item_counts=[2, 0], total_scores=[60, 0], item_spread=2, total_spread=60,
                item_spread_exceeded=True, total_spread_exceeded=True,
                warnings=["item_spread 2 exceeds max_item_spread 1 (warning mode)"],
            ),
        ),
    ]
    report = format_report(reports)
    assert "warning mode" in report


# ── run_eval / CLI (monkeypatched runner, no live gateway) ─────────────────────


def test_run_eval_repeats_per_case_and_scores(monkeypatch) -> None:
    import server.tender.eval as eval_mod

    calls: list[str] = []

    async def fake_run(*, request_id, tenant, directory_path, project_id=None, bid_id=None, on_progress=None, model=None):
        calls.append(request_id)
        return {"verdict": "manual_review", "policy_refs": []}, object()

    monkeypatch.setattr(eval_mod, "run_tender_evaluation", fake_run)

    cases = [GoldenTenderCase(case_dir="d", expected_verdict="manual_review", require_policy_refs=False, repeat=2)]
    reports = asyncio.run(run_eval(cases))
    assert len(calls) == 2
    assert reports[0].consistency.run_count == 2


def test_run_eval_single_case_error_recorded_not_raised(monkeypatch) -> None:
    import server.tender.eval as eval_mod

    async def fake_run(**kwargs):
        raise RuntimeError("gateway boom")

    monkeypatch.setattr(eval_mod, "run_tender_evaluation", fake_run)

    cases = [GoldenTenderCase(case_dir="d", expected_verdict="manual_review", repeat=2)]
    reports = asyncio.run(run_eval(cases))
    assert reports[0].errors
    assert not reports[0].passed


def test_main_exits_nonzero_on_failure(monkeypatch, tmp_path) -> None:
    import server.tender.eval as eval_mod

    async def fake_run(**kwargs):
        return {"verdict": "approved", "policy_refs": []}, object()

    monkeypatch.setattr(eval_mod, "run_tender_evaluation", fake_run)

    manifest = tmp_path / "m.json"
    manifest.write_text(
        '{"cases": [{"case_dir": "d", "expected_verdict": "manual_review", "require_policy_refs": false, "repeat": 1}]}',
        encoding="utf-8",
    )
    exit_code = main(["--manifest", str(manifest)])
    assert exit_code == 1  # verdict mismatch (approved vs expected manual_review)


def test_main_passes_model_override_through(monkeypatch, tmp_path) -> None:
    import server.tender.eval as eval_mod

    captured: dict = {}

    async def fake_run(*, model=None, **kwargs):
        captured["model"] = model
        return {"verdict": "manual_review", "policy_refs": []}, object()

    monkeypatch.setattr(eval_mod, "run_tender_evaluation", fake_run)

    manifest = tmp_path / "m.json"
    manifest.write_text(
        '{"cases": [{"case_dir": "d", "expected_verdict": "manual_review", "require_policy_refs": false, "repeat": 1}]}',
        encoding="utf-8",
    )
    main(["--manifest", str(manifest), "--model", "deepseek-v4-pro"])
    assert captured["model"] == "deepseek-v4-pro"
