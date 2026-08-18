"""P0.2 · 推理强度白名单按部署声明，剔除非白名单值时留 WARNING。

``_VALID_EFFORTS`` 写死 ``{low, medium, high, xhigh, max}``，但端点的合法档位由端点的
chat template 决定：本次部署的端点自校验 ``reasoning_effort``，只认三档，收到 ``high``/
``max`` 直接 400。现状靠 ``.env`` 的 ``CLAUDE_REASONING_EFFORT=medium`` 压住，**任何
per-call 传 high/max 的路径仍会 400**（评标 per-call 默认就传 ``xhigh``），而且换端点后
又要重踩一遍。

两条纪律写进测试：

1. 白名单**可按部署声明**（env 覆盖），未声明时与现状逐字一致——零行为变更是硬要求，
   全平台的 audit/expense/tender 都走这条路。
2. 非白名单值被剔除时**必须留一条 WARNING**。现在是静默 pop：调用方以为自己设了
   ``xhigh``，实际发出去的是端点默认，两者的判断质量差得远，却没有任何痕迹。

**不得硬编码任何模型名**：白名单是部署事实，不是代码该知道的模型知识——写死模型名等于
把"换端点要重踩"这件事固化进源码。
"""

from __future__ import annotations

import logging

import pytest

from server.common import agent_bridge
from server.common.agent_bridge import build_options

_ENV = "CLAUDE_VALID_REASONING_EFFORTS"
# 本次部署端点实际接受的三档（写成部署声明，不写成"某模型的档位"）。
_DECLARED = "xhigh, medium , low"


@pytest.fixture
def warnings(monkeypatch):
    """收 agent_bridge 的 WARNING 记录。"""
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    agent_bridge.logger.addHandler(handler)
    monkeypatch.delenv("CLAUDE_REASONING_EFFORT", raising=False)
    yield records
    agent_bridge.logger.removeHandler(handler)


def _dropped(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    return [r for r in records if r.levelno >= logging.WARNING]


# ── 声明白名单后：非白名单值剔除 + 出声 ─────────────────────────────────────


def test_declared_whitelist_drops_out_of_range_effort_and_warns(monkeypatch, warnings):
    """AC：声明白名单为 {xhigh,medium,low} 时传 high → 被剔除**且**产出 WARNING。"""
    monkeypatch.setenv(_ENV, _DECLARED)

    assert build_options(effort="high").effort is None

    dropped = _dropped(warnings)
    assert dropped, "静默 pop 正是本项要治的病：调用方以为设了 effort，实际发出去的是端点默认"
    message = dropped[0].getMessage()
    assert "high" in message, "必须点名被剔掉的是哪个值"
    assert "xhigh" in message, "必须给出本部署声明的白名单，否则运维不知道该改成什么"


def test_declared_whitelist_keeps_a_declared_value(monkeypatch, warnings):
    monkeypatch.setenv(_ENV, _DECLARED)

    assert build_options(effort="xhigh").effort == "xhigh"
    assert not _dropped(warnings), "白名单内的值不该产生噪音"


def test_declaration_tolerates_spacing_and_case(monkeypatch, warnings):
    """env 是人手写的，`XHigh , low` 这种写法不该让整条声明失效。"""
    monkeypatch.setenv(_ENV, "XHigh , low")

    assert build_options(effort="xhigh").effort == "xhigh"
    assert build_options(effort="medium").effort is None


def test_env_level_effort_is_filtered_by_the_declaration(monkeypatch, warnings):
    """per-call 与 env 两条来源同一把闸——只堵 per-call 等于没堵（.env 也可能写错档位）。"""
    monkeypatch.setenv(_ENV, _DECLARED)
    monkeypatch.setenv("CLAUDE_REASONING_EFFORT", "max")

    assert build_options().effort is None
    assert _dropped(warnings)


# ── 未声明时：与现状逐字一致 ─────────────────────────────────────────────────


@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
def test_builtin_values_are_all_accepted_when_nothing_is_declared(monkeypatch, effort, warnings):
    """零行为变更：未声明 → 内置五档全部照收（audit/expense/tender 现有调用不受影响）。"""
    monkeypatch.delenv(_ENV, raising=False)

    assert build_options(effort=effort).effort == effort
    assert not _dropped(warnings)


def test_blank_declaration_falls_back_to_the_builtin_set(monkeypatch, warnings):
    """空/全空白声明当没声明处理——配置写错不该把所有档位一起废掉。"""
    monkeypatch.setenv(_ENV, "   ")

    assert build_options(effort="max").effort == "max"


def test_unknown_value_is_still_dropped_when_nothing_is_declared(monkeypatch, warnings):
    """未声明时非法值仍剔除（现状），但从今往后要出声。"""
    monkeypatch.delenv(_ENV, raising=False)

    assert build_options(effort="ultra").effort is None
    assert _dropped(warnings), "剔除必须留痕，这是本项要修的静默 pop"


def test_absent_effort_stays_silent(monkeypatch, warnings):
    """没传 effort ≠ 传了个非法值——前者不该产生 WARNING，否则这条信号会被无视。"""
    monkeypatch.delenv(_ENV, raising=False)

    assert build_options().effort is None
    assert build_options(effort="").effort is None
    assert not _dropped(warnings)


# ── 白名单不得挂在模型名上 ───────────────────────────────────────────────────


def test_the_whitelist_never_branches_on_a_model_name(monkeypatch, warnings):
    """同一个 effort 在不同 model 下必须得到同一结果——白名单是部署事实，不是模型知识。"""
    monkeypatch.setenv(_ENV, _DECLARED)

    assert build_options(model="model-a", effort="high").effort is None
    assert build_options(model="model-b", effort="high").effort is None
    assert build_options(model="model-a", effort="low").effort == "low"
    assert build_options(model="model-b", effort="low").effort == "low"
