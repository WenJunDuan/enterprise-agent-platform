"""Golden-case regression harness for the inline audit path.

Runs a set of declared cases through ``run_inline_directory_audit`` and compares
each actual ``verdict`` (and optionally ``manual_review_reason`` / a risk-score
band) against a golden expectation. Use it as a safety net before changing
``AUDIT_INSTRUCTIONS``, swapping the gateway model (qwen ↔ cloud), or tuning the
``AUDIT_*`` knobs — run once before and once after to see whether decisions moved.

The scoring is pure and unit-tested. The runner needs a live model gateway, so
run it on the deployment host (not in CI):

    uv run python -m server.audit.eval --manifest tests/eval_fixtures/golden_manifest.json

Real cases live under ``data/`` (gitignored); point ``--manifest`` at a file that
references them. The committed fixture under ``tests/eval_fixtures/`` is a
synthetic template showing the manifest + case layout — calibrate the expected
values against a known-good run on the target deployment before trusting them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from server.audit.runner import run_inline_directory_audit

_VALID_VERDICTS = {"approved", "rejected", "manual_review"}


@dataclass(frozen=True, slots=True)
class GoldenCase:
    """One declared expectation for a case directory."""

    case_dir: str
    expected_verdict: str
    expected_manual_review_reason: str | None = None
    min_risk_score: int | None = None
    max_risk_score: int | None = None
    note: str = ""


@dataclass(slots=True)
class CaseOutcome:
    """Scoring result for one case after comparison."""

    case_dir: str
    passed: bool
    expected_verdict: str
    actual_verdict: Any
    mismatches: list[str] = field(default_factory=list)
    error: str | None = None


def parse_golden_cases(payload: dict[str, Any]) -> list[GoldenCase]:
    """Validate and convert a manifest payload into GoldenCase objects."""
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("manifest must contain a non-empty 'cases' array")
    cases: list[GoldenCase] = []
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
            GoldenCase(
                case_dir=case_dir,
                expected_verdict=verdict,
                expected_manual_review_reason=item.get("expected_manual_review_reason") or None,
                min_risk_score=item.get("min_risk_score"),
                max_risk_score=item.get("max_risk_score"),
                note=str(item.get("note") or ""),
            )
        )
    return cases


def load_golden_manifest(path: Path) -> list[GoldenCase]:
    """Load and validate a golden manifest JSON file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be a JSON object")
    return parse_golden_cases(payload)


def score_case(golden: GoldenCase, actual: dict[str, Any]) -> CaseOutcome:
    """Compare one actual audit result against its golden expectation.

    Pure: takes the parsed result dict, returns the outcome. The runner owns all
    the gateway I/O so this stays unit-testable offline.
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

    risk = actual.get("risk_score")
    risk_is_number = isinstance(risk, (int, float)) and not isinstance(risk, bool)
    if golden.min_risk_score is not None and (not risk_is_number or risk < golden.min_risk_score):
        mismatches.append(f"risk_score: expected >= {golden.min_risk_score}, got {risk}")
    if golden.max_risk_score is not None and (not risk_is_number or risk > golden.max_risk_score):
        mismatches.append(f"risk_score: expected <= {golden.max_risk_score}, got {risk}")

    return CaseOutcome(
        case_dir=golden.case_dir,
        passed=not mismatches,
        expected_verdict=golden.expected_verdict,
        actual_verdict=actual_verdict,
        mismatches=mismatches,
    )


def format_report(outcomes: list[CaseOutcome]) -> str:
    """Render a human-readable pass/fail summary."""
    passed = sum(1 for outcome in outcomes if outcome.passed)
    lines = [f"Golden eval: {passed}/{len(outcomes)} passed", ""]
    for outcome in outcomes:
        if outcome.error is not None:
            lines.append(f"  [ERROR] {outcome.case_dir}: {outcome.error}")
        elif outcome.passed:
            lines.append(f"  [PASS]  {outcome.case_dir} ({outcome.actual_verdict})")
        else:
            lines.append(f"  [FAIL]  {outcome.case_dir}")
            lines.extend(f"            - {mismatch}" for mismatch in outcome.mismatches)
    return "\n".join(lines)


async def run_eval(cases: list[GoldenCase]) -> list[CaseOutcome]:
    """Run every case through the inline audit and score it.

    A gateway/contract failure on one case is recorded as an ERROR outcome rather
    than aborting the whole run — one flaky case shouldn't hide the rest.
    """
    outcomes: list[CaseOutcome] = []
    for golden in cases:
        request_id = f"eval-{Path(golden.case_dir).name}"
        try:
            result, _meta = await run_inline_directory_audit(
                golden.case_dir, request_id=request_id, tenant=None
            )
        except Exception as exc:  # noqa: BLE001 - harness reports failures, never crashes
            outcomes.append(
                CaseOutcome(
                    case_dir=golden.case_dir,
                    passed=False,
                    expected_verdict=golden.expected_verdict,
                    actual_verdict=None,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        actual = result if isinstance(result, dict) else {}
        outcomes.append(score_case(golden, actual))
    return outcomes


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: load manifest, run cases, print report, exit nonzero on any failure."""
    parser = argparse.ArgumentParser(
        description="Run the golden-case audit regression harness against a live gateway."
    )
    parser.add_argument(
        "--manifest", required=True, type=Path, help="Path to the golden manifest JSON."
    )
    args = parser.parse_args(argv)

    cases = load_golden_manifest(args.manifest)
    outcomes = asyncio.run(run_eval(cases))
    print(format_report(outcomes))
    return 0 if all(outcome.passed for outcome in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
