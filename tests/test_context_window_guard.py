"""Unit tests for the S7 context-truncation guard.

背景：平台默认模型从 V4Pro[1M] 切到窗口小得多的 Flash 后，把数百页标书 OCR 底稿整段
内联会在网关侧被静默截断 → 模型拿半截证据评分。本 guard 让运维声明活动模型的上下文窗口
（env ``MODEL_CONTEXT_WINDOW``），注入 prompt 预估 token + 预留输出 token 超窗时记 WARNING。

两条纪律锁在测试里：
1. opt-in——``MODEL_CONTEXT_WINDOW`` 未设/非正数时 guard 完全静默、零行为变更。
2. 触发条件——``预估输入 + 预留输出 > 窗口`` 才告警，且预估随 ``MODEL_CHARS_PER_TOKEN`` 可调。
"""

from __future__ import annotations

import logging

from server.common.agent_bridge import warn_if_context_may_truncate
from server.platform.config import resolve_model_context_window

_GUARD_LOGGER = "server.common.agent_bridge"


# ── resolve_model_context_window：env 解析纪律 ──


def test_window_unset_is_zero():
    assert resolve_model_context_window({}) == 0


def test_window_valid_int():
    assert resolve_model_context_window({"MODEL_CONTEXT_WINDOW": "65536"}) == 65536


def test_window_invalid_falls_back_to_zero():
    assert resolve_model_context_window({"MODEL_CONTEXT_WINDOW": "abc"}) == 0


def test_window_non_positive_is_zero():
    assert resolve_model_context_window({"MODEL_CONTEXT_WINDOW": "-5"}) == 0
    assert resolve_model_context_window({"MODEL_CONTEXT_WINDOW": "0"}) == 0


# ── warp_if_context_may_truncate：opt-in + 触发条件 ──


def test_guard_disabled_when_window_unset(monkeypatch, caplog):
    """未声明窗口 → 返回 None、不记日志（零行为变更）。"""
    monkeypatch.delenv("MODEL_CONTEXT_WINDOW", raising=False)
    with caplog.at_level(logging.WARNING, logger=_GUARD_LOGGER):
        result = warn_if_context_may_truncate("标" * 500_000)
    assert result is None
    assert not caplog.records


def test_guard_silent_when_prompt_fits(monkeypatch, caplog):
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "10000")
    monkeypatch.setenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "1000")
    monkeypatch.setenv("MODEL_CHARS_PER_TOKEN", "1.0")
    with caplog.at_level(logging.WARNING, logger=_GUARD_LOGGER):
        result = warn_if_context_may_truncate("x" * 100)  # ~100 tokens + 1000 << 10000
    assert result is None
    assert not caplog.records


def test_guard_warns_when_input_plus_output_exceeds_window(monkeypatch, caplog):
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "10000")
    monkeypatch.setenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "1000")
    monkeypatch.setenv("MODEL_CHARS_PER_TOKEN", "1.0")
    with caplog.at_level(logging.WARNING, logger=_GUARD_LOGGER):
        result = warn_if_context_may_truncate("x" * 20_000)  # 20000 + 1000 > 10000
    assert result is not None
    assert result["estimated_input_tokens"] == 20_000
    assert result["reserved_output_tokens"] == 1_000
    assert result["context_window"] == 10_000
    assert len(caplog.records) == 1
    assert "MODEL_CONTEXT_WINDOW" in caplog.text


def test_chars_per_token_scales_estimate(monkeypatch):
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "1000000")  # 大窗口，避免触发告警干扰
    monkeypatch.setenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "0")
    monkeypatch.setenv("MODEL_CHARS_PER_TOKEN", "2.0")
    # 用一个必然超窗的小窗口二次验证换算：len=20000, 2.0 char/token → 10000 tokens
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "5000")
    result = warn_if_context_may_truncate("x" * 20_000)
    assert result is not None
    assert result["estimated_input_tokens"] == 10_000


def test_invalid_chars_per_token_uses_default(monkeypatch):
    """MODEL_CHARS_PER_TOKEN 非法（空/负/非数）→ 回落默认 1.5，不炸。"""
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "1000")
    monkeypatch.setenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "0")
    monkeypatch.setenv("MODEL_CHARS_PER_TOKEN", "not-a-number")
    result = warn_if_context_may_truncate("x" * 3000)  # 3000/1.5 = 2000 > 1000
    assert result is not None
    assert result["estimated_input_tokens"] == 2000


def test_flash_sized_window_flags_large_bid(monkeypatch, caplog):
    """真实形态 sanity：Flash 级 64K 窗口 + 十万字标书底稿 → 必告警。"""
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "65536")
    monkeypatch.setenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "32000")
    monkeypatch.delenv("MODEL_CHARS_PER_TOKEN", raising=False)  # 默认 1.5
    with caplog.at_level(logging.WARNING, logger=_GUARD_LOGGER):
        result = warn_if_context_may_truncate("标" * 100_000)  # ~66666 tokens
    assert result is not None
    assert caplog.records
