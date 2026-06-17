"""Offline coverage for the golden-case eval harness scoring + manifest parsing.

The runner itself needs a live gateway and is not exercised here; the pure
scoring/parsing surface (which is where regressions would silently corrupt a
pass/fail verdict) is fully covered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from server.audit.eval import (
    CaseOutcome,
    GoldenCase,
    format_report,
    load_golden_manifest,
    parse_golden_cases,
    score_case,
)

_FIXTURES = Path(__file__).parent / "eval_fixtures"


# ── manifest parsing ──────────────────────────────────────────────────────────
def test_parse_golden_cases_valid() -> None:
    cases = parse_golden_cases(
        {
            "cases": [
                {"case_dir": "data/c1", "expected_verdict": "approved"},
                {
                    "case_dir": "data/c2",
                    "expected_verdict": "manual_review",
                    "expected_manual_review_reason": "missing_approval",
                    "min_risk_score": 10,
                    "max_risk_score": 60,
                    "note": "n",
                },
            ]
        }
    )
    assert [c.case_dir for c in cases] == ["data/c1", "data/c2"]
    assert cases[1].expected_manual_review_reason == "missing_approval"
    assert (cases[1].min_risk_score, cases[1].max_risk_score) == (10, 60)


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


def test_load_golden_manifest_reads_committed_fixture() -> None:
    cases = load_golden_manifest(_FIXTURES / "golden_manifest.json")
    assert len(cases) == 1
    assert cases[0].case_dir == "tests/eval_fixtures/placeholder-invoice"
    assert cases[0].expected_verdict == "rejected"
    assert cases[0].min_risk_score == 70


def test_load_golden_manifest_rejects_non_object_root(tmp_path: Path) -> None:
    bad = tmp_path / "m.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_golden_manifest(bad)


def test_committed_fixture_case_dir_exists() -> None:
    """The template manifest must point at a real, present case directory."""
    case = load_golden_manifest(_FIXTURES / "golden_manifest.json")[0]
    project_root = Path(__file__).resolve().parents[1]
    assert (project_root / case.case_dir / "audit-request.json").is_file()


# ── scoring ───────────────────────────────────────────────────────────────────
def test_score_case_verdict_match_passes() -> None:
    g = GoldenCase(case_dir="d", expected_verdict="approved")
    outcome = score_case(g, {"verdict": "approved", "risk_score": 5})
    assert outcome.passed
    assert outcome.mismatches == []


def test_score_case_verdict_mismatch() -> None:
    g = GoldenCase(case_dir="d", expected_verdict="approved")
    outcome = score_case(g, {"verdict": "rejected"})
    assert not outcome.passed
    assert "verdict" in outcome.mismatches[0]


def test_score_case_reason_mismatch() -> None:
    g = GoldenCase(
        case_dir="d",
        expected_verdict="manual_review",
        expected_manual_review_reason="missing_approval",
    )
    outcome = score_case(g, {"verdict": "manual_review", "manual_review_reason": "rule_gap"})
    assert not outcome.passed
    assert any("manual_review_reason" in m for m in outcome.mismatches)


def test_score_case_reason_not_checked_when_unset() -> None:
    g = GoldenCase(case_dir="d", expected_verdict="manual_review")
    outcome = score_case(g, {"verdict": "manual_review", "manual_review_reason": "rule_gap"})
    assert outcome.passed


@pytest.mark.parametrize(
    ("risk", "expected_pass"),
    [(70, True), (85, True), (69, False), (None, False), (True, False)],
)
def test_score_case_min_risk_band(risk: object, expected_pass: bool) -> None:
    g = GoldenCase(case_dir="d", expected_verdict="rejected", min_risk_score=70)
    outcome = score_case(g, {"verdict": "rejected", "risk_score": risk})
    assert outcome.passed is expected_pass


def test_score_case_max_risk_band() -> None:
    g = GoldenCase(case_dir="d", expected_verdict="approved", max_risk_score=40)
    assert score_case(g, {"verdict": "approved", "risk_score": 40}).passed
    assert not score_case(g, {"verdict": "approved", "risk_score": 41}).passed


def test_score_case_accumulates_multiple_mismatches() -> None:
    g = GoldenCase(
        case_dir="d",
        expected_verdict="approved",
        min_risk_score=80,
    )
    outcome = score_case(g, {"verdict": "rejected", "risk_score": 10})
    assert len(outcome.mismatches) == 2


# ── reporting ─────────────────────────────────────────────────────────────────
def test_format_report_counts_and_marks() -> None:
    outcomes = [
        CaseOutcome("a", True, "approved", "approved"),
        CaseOutcome("b", False, "approved", "rejected", mismatches=["verdict: ..."]),
        CaseOutcome("c", False, "approved", None, error="Timeout"),
    ]
    report = format_report(outcomes)
    assert "1/3 passed" in report
    assert "[PASS]  a" in report
    assert "[FAIL]  b" in report
    assert "[ERROR] c: Timeout" in report
