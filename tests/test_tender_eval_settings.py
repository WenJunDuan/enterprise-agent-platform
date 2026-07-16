"""Lock the env→TenderEvalSettings mapping (D1 T3).

Mirrors ``tests/test_audit_settings.py``: TENDER_EVAL_MODEL is the only knob, read fresh
(no caching) so a deployment host can flip it without a restart. Empty (default) means
"do not override" — the per-call model override in server.tender.runner stays a no-op,
so production tender_worker behavior is unchanged unless someone deliberately sets
TENDER_EVAL_MODEL for an eval run.
"""

from __future__ import annotations

import pytest

from server.platform.config import TenderEvalSettings, get_tender_eval_settings


@pytest.fixture(autouse=True)
def _clear_tender_eval_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TENDER_EVAL_MODEL", raising=False)


def test_default_model_is_empty() -> None:
    assert get_tender_eval_settings() == TenderEvalSettings(model="")


def test_model_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENDER_EVAL_MODEL", "deepseek-v4-pro")
    assert get_tender_eval_settings().model == "deepseek-v4-pro"


def test_model_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TENDER_EVAL_MODEL", "  deepseek-v4-pro  ")
    assert get_tender_eval_settings().model == "deepseek-v4-pro"


def test_settings_are_read_fresh_each_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """No lru_cache: changing env between calls must take effect (runtime-flippable)."""
    assert get_tender_eval_settings().model == ""
    monkeypatch.setenv("TENDER_EVAL_MODEL", "qwen-flash")
    assert get_tender_eval_settings().model == "qwen-flash"
