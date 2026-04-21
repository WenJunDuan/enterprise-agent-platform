from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = PROJECT_ROOT / ".claude" / "hooks" / "review-output.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("review_output_hook", HOOK_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_review_options_disables_tools_and_hooks() -> None:
    module = _load_module()

    options = module._build_review_options()

    assert options.allowed_tools == []
    assert options.max_turns == 1
    assert options.hooks == {}


def test_run_second_review_returns_result_message_text(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()

    async def fake_query(*, prompt: str, options):
        yield AssistantMessage(content=[TextBlock(text="PASS")], model="test-model", session_id="sess-1")
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="sess-1",
            total_cost_usd=0.01,
            result="PASS",
            structured_output=None,
        )

    monkeypatch.setattr(module, "query", fake_query)

    result = asyncio.run(module._run_second_review('{"ok": true}'))

    assert result == "PASS"


def test_run_second_review_raises_on_sdk_error(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()

    async def fake_query(*, prompt: str, options):
        yield ResultMessage(
            subtype="error",
            duration_ms=1,
            duration_api_ms=1,
            is_error=True,
            num_turns=1,
            session_id="sess-1",
            total_cost_usd=0.01,
            result="boom",
            structured_output=None,
        )

    monkeypatch.setattr(module, "query", fake_query)

    with pytest.raises(RuntimeError):
        asyncio.run(module._run_second_review('{"ok": true}'))


def test_should_run_second_review_skips_low_risk_approved() -> None:
    module = _load_module()

    should_run = module._should_run_second_review(
        {
            "response": {
                "verdict": "approved",
                "risk_score": 20,
                "manual_review_reason": None,
            }
        }
    )

    assert should_run is False


def test_should_run_second_review_runs_for_high_risk_or_conflict_cases() -> None:
    module = _load_module()

    assert (
        module._should_run_second_review(
            {"response": {"verdict": "approved", "risk_score": 80, "manual_review_reason": None}}
        )
        is True
    )
    assert (
        module._should_run_second_review(
            {
                "response": {
                    "verdict": "manual_review",
                    "risk_score": 30,
                    "manual_review_reason": "pre_approval_mismatch",
                }
            }
        )
        is True
    )
    assert (
        module._should_run_second_review(
            {"response": {"verdict": "rejected", "risk_score": 40, "manual_review_reason": None}}
        )
        is True
    )
