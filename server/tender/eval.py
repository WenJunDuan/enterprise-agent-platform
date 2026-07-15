"""Golden-case regression harness for the tender evaluation path.

Mirrors ``server/audit/eval.py``'s shape (pure scoring / live-gateway runner split) with
tender-specific dimensions layered on top — the S7 stress-test lesson (compound/
2026-07-01-learning-flash-tender-eval-inconsistency.md) was that verdict-only pass/fail is
not enough: the same bid scored 3 times can produce wildly different ``scoring[]`` totals
even when every run reports a "valid" verdict. So on top of the audit-style single-run
checks (verdict / manual_review_reason / policy_refs), this harness runs each case
``repeat`` times and measures the cross-run spread of "how many items got a real score" and
"what did they sum to" — that is where the 7x drift actually showed up.

The scoring below is pure and unit-tested offline (this is the D1 T1 slice: manifest
parsing + single-run scoring + cross-run consistency + reporting). The live-gateway
runner (``run_eval`` + CLI ``main``, calling ``server.tender.runner.run_tender_evaluation``)
lands in D1 T2 once the evaluation core is down there — see
``.ai_state/sprints/2026-07-02-eval-tender-scaffold/design.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from server.common.tender_output import is_real_number

_VALID_VERDICTS = {"approved", "rejected", "manual_review"}
_DEFAULT_REPEAT = 3


@dataclass(frozen=True, slots=True)
class EligibilityExpectation:
    """One declared expectation for an ``extracted_data.eligibility_checks[]`` entry."""

    check: str
    expected_status: str


@dataclass(frozen=True, slots=True)
class ScoringExpectation:
    """One declared expectation for an ``extracted_data.scoring[]`` item's status."""

    item: str
    expected_statuses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GoldenTenderCase:
    """One declared expectation for a bid case directory."""

    case_dir: str
    expected_verdict: str
    expected_manual_review_reason: str | None = None
    eligibility_expectations: tuple[EligibilityExpectation, ...] = ()
    scoring_expectations: tuple[ScoringExpectation, ...] = ()
    min_total_score: float | None = None
    max_total_score: float | None = None
    require_policy_refs: bool = True
    max_item_spread: float | None = None
    max_total_spread: float | None = None
    repeat: int = _DEFAULT_REPEAT
    note: str = ""


@dataclass(slots=True)
class CaseOutcome:
    """Single-run scoring result for one case after comparison."""

    case_dir: str
    passed: bool
    actual_verdict: Any
    mismatches: list[str] = field(default_factory=list)
    scored_item_count: int = 0
    total_score: float = 0.0
    error: str | None = None


@dataclass(slots=True)
class ConsistencyOutcome:
    """Cross-run (repeat-N) spread of scored-item-count and total-score.

    首版警告模式（design round1 F4）：``*_exceeded`` 只用于报告/警告，不影响任何 ``passed``
    判定；硬门待部署机建立基线后二次 commit 收紧（阈值来自 ``GoldenTenderCase.max_*_spread``）。
    """

    run_count: int
    item_counts: list[int]
    total_scores: list[float]
    item_spread: float
    total_spread: float
    item_spread_exceeded: bool
    total_spread_exceeded: bool
    warnings: list[str] = field(default_factory=list)
    skipped: bool = False


@dataclass(slots=True)
class CaseReport:
    """All repeat-N run outcomes + the cross-run consistency verdict for one case."""

    case_dir: str
    run_outcomes: list[CaseOutcome]
    consistency: ConsistencyOutcome | None
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Warning-mode: only per-run mismatches + gateway errors fail a case, not spread."""
        return not self.errors and all(outcome.passed for outcome in self.run_outcomes)


def _parse_eligibility_expectations(raw: Any) -> tuple[EligibilityExpectation, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        EligibilityExpectation(check=str(item["check"]), expected_status=str(item["expected_status"]))
        for item in raw
        if isinstance(item, dict) and "check" in item and "expected_status" in item
    )


def _parse_scoring_expectations(raw: Any) -> tuple[ScoringExpectation, ...]:
    if not isinstance(raw, list):
        return ()
    expectations: list[ScoringExpectation] = []
    for item in raw:
        if not isinstance(item, dict) or "item" not in item:
            continue
        statuses = item.get("expected_statuses") or []
        expectations.append(
            ScoringExpectation(item=str(item["item"]), expected_statuses=tuple(str(s) for s in statuses))
        )
    return tuple(expectations)


def parse_golden_cases(payload: dict[str, Any]) -> list[GoldenTenderCase]:
    """Validate and convert a manifest payload into GoldenTenderCase objects."""
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("manifest must contain a non-empty 'cases' array")
    cases: list[GoldenTenderCase] = []
    for index, item in enumerate(raw_cases):
        if not isinstance(item, dict):
            raise ValueError(f"cases[{index}] must be an object")
        case_dir = str(item.get("case_dir") or "").strip()
        verdict = str(item.get("expected_verdict") or "").strip()
        if not case_dir:
            raise ValueError(f"cases[{index}] missing case_dir")
        if verdict not in _VALID_VERDICTS:
            raise ValueError(
                f"cases[{index}] expected_verdict must be one of {sorted(_VALID_VERDICTS)}"
            )
        cases.append(
            GoldenTenderCase(
                case_dir=case_dir,
                expected_verdict=verdict,
                expected_manual_review_reason=item.get("expected_manual_review_reason") or None,
                eligibility_expectations=_parse_eligibility_expectations(
                    item.get("eligibility_expectations")
                ),
                scoring_expectations=_parse_scoring_expectations(item.get("scoring_expectations")),
                min_total_score=item.get("min_total_score"),
                max_total_score=item.get("max_total_score"),
                require_policy_refs=bool(item.get("require_policy_refs", True)),
                max_item_spread=item.get("max_item_spread"),
                max_total_spread=item.get("max_total_spread"),
                repeat=int(item.get("repeat") or _DEFAULT_REPEAT),
                note=str(item.get("note") or ""),
            )
        )
    return cases


def load_golden_manifest(path: Path) -> list[GoldenTenderCase]:
    """Load and validate a golden manifest JSON file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be a JSON object")
    return parse_golden_cases(payload)


def _scored_summary(actual: dict[str, Any]) -> tuple[int, float]:
    """出分项数 / 实得合计：仅数 score 通过 is_real_number 校验的 scoring[] 条目（round1 F2）。"""
    extracted = actual.get("extracted_data") if isinstance(actual, dict) else None
    scoring = extracted.get("scoring") if isinstance(extracted, dict) else None
    if not isinstance(scoring, list):
        return 0, 0.0
    count = 0
    total = 0.0
    for item in scoring:
        if not isinstance(item, dict):
            continue
        score = item.get("score")
        if is_real_number(score):
            count += 1
            total += float(score)
    return count, total


def score_case(golden: GoldenTenderCase, actual: dict[str, Any]) -> CaseOutcome:
    """Compare one actual evaluation result against its golden expectation.

    Pure: takes the parsed result dict, returns the outcome. The runner owns all the
    gateway I/O so this stays unit-testable offline.
    """
    mismatches: list[str] = []
    actual_verdict = actual.get("verdict")
    if actual_verdict != golden.expected_verdict:
        mismatches.append(f"verdict: expected {golden.expected_verdict}, got {actual_verdict}")

    if golden.expected_manual_review_reason is not None:
        actual_reason = actual.get("manual_review_reason")
        if actual_reason != golden.expected_manual_review_reason:
            mismatches.append(
                "manual_review_reason: "
                f"expected {golden.expected_manual_review_reason}, got {actual_reason}"
            )

    extracted = actual.get("extracted_data") if isinstance(actual, dict) else None
    eligibility_checks = (
        extracted.get("eligibility_checks") if isinstance(extracted, dict) else None
    )
    eligibility_by_check: dict[str, Any] = {}
    if isinstance(eligibility_checks, list):
        for check in eligibility_checks:
            if isinstance(check, dict) and isinstance(check.get("check"), str):
                eligibility_by_check[check["check"]] = check.get("status")
    for expectation in golden.eligibility_expectations:
        actual_status = eligibility_by_check.get(expectation.check)
        if actual_status != expectation.expected_status:
            mismatches.append(
                f"eligibility_checks[{expectation.check!r}]: "
                f"expected {expectation.expected_status}, got {actual_status}"
            )

    scoring = extracted.get("scoring") if isinstance(extracted, dict) else None
    scoring_by_item: dict[str, Any] = {}
    if isinstance(scoring, list):
        for item in scoring:
            if isinstance(item, dict) and isinstance(item.get("item"), str):
                scoring_by_item[item["item"]] = item.get("status")
    for expectation in golden.scoring_expectations:
        actual_status = scoring_by_item.get(expectation.item)
        if expectation.expected_statuses and actual_status not in expectation.expected_statuses:
            mismatches.append(
                f"scoring[{expectation.item!r}].status: "
                f"expected one of {expectation.expected_statuses}, got {actual_status}"
            )

    scored_item_count, total_score = _scored_summary(actual)
    if golden.min_total_score is not None and total_score < golden.min_total_score:
        mismatches.append(f"total_score: expected >= {golden.min_total_score}, got {total_score}")
    if golden.max_total_score is not None and total_score > golden.max_total_score:
        mismatches.append(f"total_score: expected <= {golden.max_total_score}, got {total_score}")

    if golden.require_policy_refs:
        policy_refs = actual.get("policy_refs") if isinstance(actual, dict) else None
        if not isinstance(policy_refs, list) or not policy_refs:
            mismatches.append("policy_refs: expected a non-empty array, got " f"{policy_refs!r}")

    return CaseOutcome(
        case_dir=golden.case_dir,
        passed=not mismatches,
        actual_verdict=actual_verdict,
        mismatches=mismatches,
        scored_item_count=scored_item_count,
        total_score=total_score,
    )


def score_consistency(
    golden: GoldenTenderCase, actual_results: list[dict[str, Any]]
) -> ConsistencyOutcome:
    """Cross-run consistency: scored-item-count spread + total-score spread across repeat-N.

    ``actual_results`` 长度 < 2（round2 F7 边界：单跑/无跑）时无法算极差，返回 ``skipped=True``
    的零值结果，不崩、不算伪极差。null 分项不计入项数/合计（复用 ``tender_output.is_real_number``），
    全 null 的 run 因此记 0/0——正是要让 S7 案例B 那种"崩塌"撑大极差、被闸看见。
    """
    if len(actual_results) < 2:
        return ConsistencyOutcome(
            run_count=len(actual_results),
            item_counts=[],
            total_scores=[],
            item_spread=0,
            total_spread=0,
            item_spread_exceeded=False,
            total_spread_exceeded=False,
            skipped=True,
        )

    summaries = [_scored_summary(actual) for actual in actual_results]
    item_counts = [count for count, _ in summaries]
    total_scores = [total for _, total in summaries]
    item_spread = max(item_counts) - min(item_counts)
    total_spread = max(total_scores) - min(total_scores)

    item_exceeded = golden.max_item_spread is not None and item_spread > golden.max_item_spread
    total_exceeded = golden.max_total_spread is not None and total_spread > golden.max_total_spread
    warnings: list[str] = []
    if item_exceeded:
        warnings.append(
            f"item_spread {item_spread} exceeds max_item_spread {golden.max_item_spread} "
            "(warning mode, not failed)"
        )
    if total_exceeded:
        warnings.append(
            f"total_spread {total_spread} exceeds max_total_spread {golden.max_total_spread} "
            "(warning mode, not failed)"
        )

    return ConsistencyOutcome(
        run_count=len(actual_results),
        item_counts=item_counts,
        total_scores=total_scores,
        item_spread=item_spread,
        total_spread=total_spread,
        item_spread_exceeded=item_exceeded,
        total_spread_exceeded=total_exceeded,
        warnings=warnings,
    )


def format_report(reports: list[CaseReport]) -> str:
    """Render a human-readable pass/fail summary, including consistency warnings."""
    passed = sum(1 for report in reports if report.passed)
    lines = [f"Tender golden eval: {passed}/{len(reports)} passed", ""]
    for report in reports:
        if report.errors:
            for error in report.errors:
                lines.append(f"  [ERROR] {report.case_dir}: {error}")
            continue
        if report.passed:
            lines.append(f"  [PASS]  {report.case_dir}")
        else:
            lines.append(f"  [FAIL]  {report.case_dir}")
            for outcome in report.run_outcomes:
                lines.extend(f"            - {mismatch}" for mismatch in outcome.mismatches)
        consistency = report.consistency
        if consistency is not None and not consistency.skipped:
            lines.append(
                f"            item_counts={consistency.item_counts} "
                f"(spread={consistency.item_spread}), "
                f"total_scores={consistency.total_scores} (spread={consistency.total_spread})"
            )
            for warning in consistency.warnings:
                lines.append(f"            [WARN] {warning}")
    return "\n".join(lines)


# run_eval (repeat-N live-gateway runner) + CLI main land in D1 T2 once
# server.tender.runner.run_tender_evaluation exists.
