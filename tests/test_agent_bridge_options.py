"""Unit tests for server/common/agent_bridge.build_options.

聚焦两点：
1. max_buffer_size — SDK 默认单条 stdout JSON 1MiB 上限会在评标注入大 OCR 底稿 /
   agent 直读大 PDF 时溢出致整单失败（B 端到端验证暴露）。锁住默认值与 env 覆盖。
2. max_budget_usd 成本封顶已按用户要求移除（不再设上限）；守卫防回归。
"""

from __future__ import annotations

from server.common.agent_bridge import build_options

DEFAULT_MAX_BUFFER = 20 * 1024 * 1024


def test_max_buffer_size_default_is_20mib():
    assert build_options().max_buffer_size == DEFAULT_MAX_BUFFER


def test_max_buffer_size_env_override(monkeypatch):
    monkeypatch.setenv("CLAUDE_MAX_BUFFER_BYTES", str(30 * 1024 * 1024))
    assert build_options().max_buffer_size == 30 * 1024 * 1024


def test_max_buffer_size_well_above_sdk_default():
    """回归守卫：默认必须显著高于 SDK 的 1MiB，否则大底稿评标会再次崩。"""
    assert build_options().max_buffer_size > 1024 * 1024


def test_no_budget_cap_set():
    """成本封顶已移除：build_options 不得再设 max_budget_usd（用户要求去掉限制）。"""
    assert build_options().max_budget_usd is None


# ── 推理强度（extended thinking）：评标/审核默认 xhigh，治 deepseek 判断随机性 ──


def test_effort_default_unset(monkeypatch):
    # 全局不默认 xhigh（codex r4 P1：避免全局 xhigh 拖慢 audit）；env 未设 → effort None 走端点默认。
    monkeypatch.delenv("CLAUDE_REASONING_EFFORT", raising=False)
    assert build_options().effort is None


def test_effort_env_override(monkeypatch):
    monkeypatch.setenv("CLAUDE_REASONING_EFFORT", "high")
    assert build_options().effort == "high"


def test_effort_invalid_env_dropped(monkeypatch):
    # 非法档位（含 off/none）→ 剔除不设，不致 ClaudeAgentOptions/CLI 报错。
    monkeypatch.setenv("CLAUDE_REASONING_EFFORT", "ultra")
    assert build_options().effort is None


def test_effort_per_call_override(monkeypatch):
    # 评标 per-call 传 effort=xhigh（tender_worker 用），即使全局 env 未设也生效。
    monkeypatch.delenv("CLAUDE_REASONING_EFFORT", raising=False)
    assert build_options(effort="xhigh").effort == "xhigh"


def test_effort_per_call_invalid_dropped(monkeypatch):
    # per-call 传非法档位也被统一校验剔除（不致 CLI 报错）。
    monkeypatch.delenv("CLAUDE_REASONING_EFFORT", raising=False)
    assert build_options(effort="bogus").effort is None
