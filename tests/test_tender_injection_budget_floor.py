"""P0.1 · 预算悬崖：证据额度跌破可论证下界时显式失败，且两种原因可区分。

2026-08-18 把部署 env 切成 ``TENDER_EFFECTIVE_CONTEXT_TOKENS=95000`` /
``TENDER_SCAFFOLD_RESERVE_TOKENS=50000`` 后，``plan_injection`` 的账目
``evidence = effective − scaffold − criteria − effective/4`` 里 **criteria 是变量而
scaffold/margin 是常量**，于是（12 项、实测值）：

===================  ==================  =====================================
criteria (token)     evidence (token)    结果
===================  ==================  =====================================
5,000                16,250              per_item 1,354
15,000               6,250               per_item 520 —— 静默产出的无用额度
21,000               250                 per_item 20 —— 同上
22,342               −1,092              已有的 InjectionBudgetExhausted
===================  ==================  =====================================

本文件钉两件事：

1. **无用额度不许静默产出**——中间那两档必须与最后一档同族失败，而不是返回一个
   per_item 只够半句话的"计划"。
2. **失败原因必须可区分**——「窗口装不下」（再怎么调 env 也放不下）与「配置压过头」
   （scaffold 留额吃掉了本该给证据的空间）的解锁动作完全不同，混成一条消息等于没说。

**下界的取法**：证据额度不得低于它要回答的那一层规则本身的额度（``evidence ≥ criteria``，
等价于 ``per_item ≥ criteria_tokens / query_count``）。这是链路级判据、无自由参数、不绑任何
一份标书：一个每项分到的证据额度还装不下该项规则原文的注入，模型只能照着招标文件的评分表
给投标打分——critic 离线复跑 ``53f94fd0`` 观测到的正是这个形态（投标报价 82 分项拿到的
301 token 是招标层废标条款）。

**为什么不取 ``query_count × MAX_CHUNK_CHARS``**（计划档原文提的下界）：那个门槛在本系统
跑过的**每一种**配置下都不可达，见 ``test_the_ideal_one_full_chunk_floor_is_documented_as_unreachable``。
"""

from __future__ import annotations

import json

import pytest

from server.tender import injection_budget as budget

# 部署实测 env（2026-08-18 `docker exec agent-backend printenv`）。
DEPLOYED_EFFECTIVE = "95000"
DEPLOYED_SCAFFOLD = "50000"
# 实测项目的检索项数（12 项评分 + 资格规则，critic 复跑那单用的就是这个量级）。
DEPLOYED_QUERY_COUNT = 12

# 「配置压过头」那一档特有的解锁指令。用它区分两条消息的**处方**，而不是区分"有没有提到
# scaffold"——两条消息都会在账目里用 env 名给数字打标签，那是诊断不是处方。
_SCAFFOLD_UNLOCK = "解锁：把 TENDER_SCAFFOLD_RESERVE_TOKENS 调到不超过"


def _criteria_sized(target_tokens: int, *, item_count: int = DEPLOYED_QUERY_COUNT) -> dict:
    """造一份**实测 token 数不低于** ``target_tokens`` 的 criteria。

    体量由 ``criteria_tokens``（真正进 prompt 的 ``indent=2`` 序列化形态）现场量，
    不用估算值——预算判据本身就是按实测走的，测试也必须同源。
    """
    criteria: dict = {
        "items": [{"item": f"评分项{i}", "max": 5} for i in range(item_count)],
        "eligibility_rules": [{"check": "营业执照", "requirement": "有效期内"}],
    }
    while budget.criteria_tokens(criteria) < target_tokens:
        shortfall = target_tokens - budget.criteria_tokens(criteria)
        criteria["scoring_rule_text"] = criteria.get("scoring_rule_text", "") + "评分细则原文" * max(
            1, shortfall // 6
        )
    return criteria


def _deploy_env(monkeypatch) -> None:
    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", DEPLOYED_EFFECTIVE)
    monkeypatch.setenv("TENDER_SCAFFOLD_RESERVE_TOKENS", DEPLOYED_SCAFFOLD)


# ── 无用额度不许静默产出 ─────────────────────────────────────────────────────


def test_large_criteria_on_the_deployed_env_fails_with_the_measured_numbers(monkeypatch):
    """AC：大 criteria（≥22,000 tok）+ 95K/50K → 异常消息同时含实测 criteria、effective/scaffold、标定档。"""
    _deploy_env(monkeypatch)
    criteria = _criteria_sized(22_000)
    measured = budget.criteria_tokens(criteria)

    with pytest.raises(budget.InjectionBudgetExhausted) as excinfo:
        budget.plan_injection(criteria=criteria, query_count=DEPLOYED_QUERY_COUNT)

    message = str(excinfo.value)
    assert str(measured) in message, "必须带**实测**的 criteria token 数，不是估算或区间"
    assert DEPLOYED_EFFECTIVE in message, "必须带当前 effective 上限"
    assert DEPLOYED_SCAFFOLD in message, "必须带当前 scaffold 留额"
    assert budget.CALIBRATION_DOC_PATH in message


def test_per_item_budget_below_the_rule_layer_fails_instead_of_being_planned(monkeypatch):
    """criteria=15,000 tok 那一档：此前静默产出 per_item=520，现在必须显式失败。"""
    _deploy_env(monkeypatch)
    criteria = _criteria_sized(15_000)

    with pytest.raises(budget.InjectionBudgetExhausted):
        budget.plan_injection(criteria=criteria, query_count=DEPLOYED_QUERY_COUNT)


def test_every_plan_that_is_returned_can_answer_the_rules_it_carries():
    """不变量：凡是**返回**的计划，证据额度都不低于规则层额度（下界由构造保证）。"""
    for item_count in (1, 5, 12, 20, 40):
        criteria = _criteria_sized(200, item_count=item_count)
        plan = budget.plan_injection(criteria=criteria, query_count=item_count)
        assert plan.evidence_tokens >= plan.criteria_tokens, (
            f"{item_count} 项：证据额度 {plan.evidence_tokens} < 规则额度 {plan.criteria_tokens}，"
            "这样的注入只能让模型照着招标评分表给投标打分"
        )


def test_a_project_with_many_rich_rules_fails_before_thinning_every_item(monkeypatch):
    """项数多到每项证据额度装不下该项规则原文时，同样是显式失败而不是薄计划。

    与「criteria 太大」是同一条下界的另一个方向：那边是单项规则太长，这边是项数太多。
    """
    _deploy_env(monkeypatch)
    with pytest.raises(budget.InjectionBudgetExhausted):
        budget.plan_injection(criteria=_criteria_sized(21_000, item_count=60), query_count=60)


# ── 两种原因必须可区分 ───────────────────────────────────────────────────────


def test_over_reserved_config_is_reported_as_a_fixable_configuration(monkeypatch):
    """95K 窗口 + 50K scaffold + 15K criteria：窗口本身放得下，是留额压过头 → 可配置解锁。"""
    _deploy_env(monkeypatch)

    with pytest.raises(budget.InjectionBudgetExhausted) as excinfo:
        budget.plan_injection(criteria=_criteria_sized(15_000), query_count=DEPLOYED_QUERY_COUNT)

    assert excinfo.value.cause == "reserve_too_large"
    assert _SCAFFOLD_UNLOCK in str(excinfo.value), "解锁动作必须点名可调的那个 env 与它的上界"


def test_window_that_cannot_fit_is_reported_as_such(monkeypatch):
    """criteria 大到即便 scaffold 归零也装不下 → 这不是配置问题，是本部署评不了这个项目。"""
    _deploy_env(monkeypatch)
    # 判据：criteria + 下界(=criteria) 超过窗口去掉循环余量后的全部空间。
    criteria = _criteria_sized(40_000)

    with pytest.raises(budget.InjectionBudgetExhausted) as excinfo:
        budget.plan_injection(criteria=criteria, query_count=DEPLOYED_QUERY_COUNT)

    assert excinfo.value.cause == "window_too_small"
    message = str(excinfo.value)
    assert _SCAFFOLD_UNLOCK not in message, (
        "窗口装不下时不该指使运维去调 scaffold——调到 0 也放不下，那是把人往错方向送"
    )
    assert "改配置无用" in message, "必须明说这条路不通，否则运维会先去试 env"
    assert budget.CALIBRATION_DOC_PATH in message


def test_the_two_causes_are_machine_readable_and_disjoint(monkeypatch):
    """原因是机器码而不是靠 grep 中文消息——上层要按它分流（配置工单 vs 换模型）。"""
    _deploy_env(monkeypatch)
    causes = set()
    for target in (15_000, 40_000):
        with pytest.raises(budget.InjectionBudgetExhausted) as excinfo:
            budget.plan_injection(
                criteria=_criteria_sized(target), query_count=DEPLOYED_QUERY_COUNT
            )
        causes.add(excinfo.value.cause)
    assert causes == {"reserve_too_large", "window_too_small"}


# ── 可达性：新下界不得把跑得通的配置判死 ─────────────────────────────────────


def test_the_production_shape_that_actually_worked_still_plans():
    """回归闸：2026-08-18 生产那次（默认 200K/90K，证据层出 29 块）必须仍能出计划。

    收紧下界最大的风险是"落笔即不可达"——把一个**实测跑通过**的配置判成硬失败。
    """
    criteria = _criteria_sized(22_342)
    plan = budget.plan_injection(criteria=criteria, query_count=DEPLOYED_QUERY_COUNT)
    assert plan.per_item_tokens > 0
    assert plan.evidence_tokens >= plan.criteria_tokens


def test_the_ideal_one_full_chunk_floor_is_documented_as_unreachable():
    """计划档提的 ``query_count × MAX_CHUNK_CHARS`` 下界，在默认标定下就已不可达。

    留这条测试是为了让下一个想"顺手收紧到一个完整 chunk"的人先看到算术：
    默认 200K 标定下，规则层与循环余量吃掉 70%，20 项 × 4,000 = 80,000 > 可用的 60,000。
    收紧到那个门槛等于宣布本系统跑过的每一种配置都不可评。
    """
    from server.tender.evidence_chunks import MAX_CHUNK_CHARS

    plan = budget.plan_injection(criteria=None, query_count=1)
    available = plan.total_tokens - plan.scaffold_tokens - plan.margin_tokens
    assert available < 20 * MAX_CHUNK_CHARS, (
        "若本断言失败说明标定/留额已变，可重新评估是否收紧到「每项一个完整 chunk」"
    )


def test_zero_criteria_path_is_unchanged():
    """回落路径（无 criteria 注入块）不受新下界影响——那条路上规则层额度为 0。"""
    plan = budget.plan_injection(criteria=None, query_count=1)
    assert plan.criteria_tokens == 0
    assert plan.evidence_tokens > 0


def test_criteria_measurement_used_by_the_floor_is_the_prompt_shape():
    """下界用的 criteria 体量必须是真正进 prompt 的 ``indent=2`` 形态（紧凑序列化低估三成）。"""
    criteria = _criteria_sized(1_000)
    assert budget.criteria_tokens(criteria) == len(
        json.dumps(criteria, ensure_ascii=False, indent=2)
    )
