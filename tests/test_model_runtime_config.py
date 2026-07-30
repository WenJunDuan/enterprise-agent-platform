"""Model-specific runtime budgets must come from deployment configuration."""

from __future__ import annotations

import json

from server.common.agent_bridge import build_options
from server.platform.config import (
    resolve_model_context_window,
    resolve_model_max_output_tokens,
)


def _profiles(monkeypatch):
    monkeypatch.setenv(
        "MODEL_PROFILES_JSON",
        json.dumps(
            {
                "small-model": {
                    "context_window": 100,
                    "max_output_tokens": 10,
                },
                "large-model": {
                    "context_window": 1000,
                    "max_output_tokens": 80,
                },
            }
        ),
    )
    monkeypatch.delenv("MODEL_CONTEXT_WINDOW", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", raising=False)


def test_model_profile_resolves_window_and_output(monkeypatch):
    _profiles(monkeypatch)

    assert resolve_model_context_window(model="small-model") == 100
    assert resolve_model_max_output_tokens(model="small-model") == 10
    assert resolve_model_context_window(model="large-model") == 1000
    assert resolve_model_max_output_tokens(model="large-model") == 80


def test_build_options_passes_profile_output_to_only_that_cli(monkeypatch):
    _profiles(monkeypatch)

    options = build_options(model="small-model")

    assert options.model == "small-model"
    assert options.env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "10"


def test_build_options_does_not_invent_model_output_limit(monkeypatch):
    _profiles(monkeypatch)
    monkeypatch.setenv("MODEL_NAME", "unprofiled-model")

    options = build_options()

    assert "CLAUDE_CODE_MAX_OUTPUT_TOKENS" not in options.env
