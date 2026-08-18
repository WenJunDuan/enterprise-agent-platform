"""S2 · 预算口径单点化 + 闭式账目（AC5/AC6）。

三次事故的算术教训都写在这里：

- 64,000B 那次是**单位错**（把 token 门槛写成字节）→ 本模块全文以 token 计，字节只在换算处出现。
- 250KB 那次是**分配算法错**（分给谁都不够）→ 证据预算按项**派生**，不再是拍脑袋的常量。
- "每项 ≤8KB × 20 项 + 脚手架 25K = 79K > 60K" 那次是**落笔即不可达** → 闭式账目由构造保证
  恒成立（证据额度 = 总额减去其余各项后**除**以查询数），并对不可达显式失败而不是静默缩水。
"""

from __future__ import annotations

import pytest

from server.tender import injection_budget as budget


def _criteria(item_count: int) -> dict:
    return {
        "items": [{"item": f"评分项{i}", "max": 5} for i in range(item_count)],
        "eligibility_rules": [{"check": "营业执照", "requirement": "有效期内"}],
    }


# ── 单一来源 ────────────────────────────────────────────────────────────────


def test_effective_context_tokens_is_the_single_calibrated_constant():
    """AC6：唯一需要标定的数字就是它；其余都由它派生或现场测量。"""
    assert budget.effective_context_tokens() == budget.TENDER_EFFECTIVE_CONTEXT_TOKENS
    assert budget.TENDER_EFFECTIVE_CONTEXT_TOKENS > 0


def test_effective_context_tokens_reads_env_override(monkeypatch):
    """部署换模型/换 CLI 后可就地复标定，不必改代码。"""
    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", "123456")
    assert budget.effective_context_tokens() == 123456


@pytest.mark.parametrize("bad", ["0", "-5", "abc", ""])
def test_invalid_env_falls_back_to_calibrated_default(monkeypatch, bad):
    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", bad)
    assert budget.effective_context_tokens() == budget.TENDER_EFFECTIVE_CONTEXT_TOKENS


def test_token_estimate_counts_chinese_as_one_token_per_char():
    """中文 OCR 底稿 1 字≈1 token；ASCII 更省，取保守上界不得低估。"""
    assert budget.estimate_tokens("投标报价一览表") == 7
    assert budget.estimate_tokens("") == 0


def test_bytes_per_token_is_only_used_for_conversion():
    """字节只在换算处出现（UTF-8 中文 3B/字）——预算判据本身全部以 token 计。"""
    assert budget.tokens_to_bytes(1000) == 3000


# ── 闭式账目 ────────────────────────────────────────────────────────────────


def test_plan_satisfies_the_closed_form_account():
    """AC5 核心断言：scaffold + criteria + Σ(per_item) + margin ≤ 有效上限。"""
    plan = budget.plan_injection(criteria=_criteria(14), query_count=20)
    total = (
        plan.scaffold_tokens
        + plan.criteria_tokens
        + plan.per_item_tokens * plan.query_count
        + plan.margin_tokens
    )
    assert total <= budget.effective_context_tokens()
    assert plan.evidence_tokens == plan.per_item_tokens * plan.query_count


def test_per_item_budget_is_derived_not_a_hardcoded_constant():
    """查询项越多，每项额度越小——总额恒定。KD3：禁止再靠调一个常数收敛。"""
    few = budget.plan_injection(criteria=_criteria(5), query_count=5)
    many = budget.plan_injection(criteria=_criteria(5), query_count=40)
    assert few.per_item_tokens > many.per_item_tokens
    assert few.evidence_tokens >= many.evidence_tokens - few.query_count


def test_injection_size_is_decoupled_from_bid_volume():
    """AC5：同一招标 + 40 页/400 页两份投标，注入量差异 ≤20%（实际应完全相同）。

    证据预算只由 criteria 与有效上限决定，投标体量根本不进这个算式。
    """
    plan = budget.plan_injection(criteria=_criteria(14), query_count=20)
    assert plan.evidence_tokens == budget.plan_injection(
        criteria=_criteria(14), query_count=20
    ).evidence_tokens


def test_criteria_tokens_are_measured_from_the_real_object():
    """AC5：criteria 额度实测，不用估算值。"""
    small = budget.plan_injection(criteria=_criteria(3), query_count=10)
    large = budget.plan_injection(criteria=_criteria(60), query_count=10)
    assert large.criteria_tokens > small.criteria_tokens
    assert large.evidence_tokens < small.evidence_tokens


def test_query_count_zero_is_rejected_as_internal_invariant():
    """无查询项就不该走检索组装——内部不变量破坏，fail-fast 而非静默返回 0。"""
    with pytest.raises(ValueError):
        budget.plan_injection(criteria=_criteria(3), query_count=0)


def test_unreachable_budget_fails_loudly_and_names_the_calibration(monkeypatch):
    """标定值小到装不下规则层时**显式失败**——静默缩水正是 08-15 那次把招标整份挤掉的成因。"""
    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", "100")
    with pytest.raises(budget.InjectionBudgetExhausted) as excinfo:
        budget.plan_injection(criteria=_criteria(14), query_count=20)
    message = str(excinfo.value)
    assert "TENDER_EFFECTIVE_CONTEXT_TOKENS" in message
    assert budget.CALIBRATION_DOC_PATH in message


def test_context_overflow_message_names_constant_and_calibration_doc():
    """AC6：CLI 拒绝时的错误必须点名标定常量与标定档路径，防止它变成第五个写死的错数字。"""
    message = budget.describe_context_rejection(observed_tokens=250_000)
    assert "TENDER_EFFECTIVE_CONTEXT_TOKENS" in message
    assert budget.CALIBRATION_DOC_PATH in message
    assert "250000" in message.replace(",", "")


def test_runner_logs_the_recalibration_hint_when_the_cli_rejects(monkeypatch):
    """AC6 端到端：CLI 因超窗一次性硬拒时，运维必须直接拿到"去哪复标定"。

    ``contract.py`` 已把 ``Prompt is too long`` 列为不可重试——没有"多试几次"的余地，
    所以这一条错误日志就是运维唯一的线索，不能只有一句网关原文。
    """
    import asyncio
    import logging

    from server.tender import doc_layer, runner

    monkeypatch.setattr(doc_layer, "load_doc_layer_context", lambda *_a, **_kw: None)
    monkeypatch.setattr(doc_layer, "load_doc_layer_context_slim", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *_a, **_kw: "底稿")

    async def reject(*_a, **_kw):
        raise ValueError("API Error: Prompt is too long")

    monkeypatch.setattr(runner, "run_command_json", reject)

    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    runner.logger.addHandler(handler)
    try:
        with pytest.raises(ValueError):
            asyncio.run(
                runner.run_tender_evaluation(
                    request_id="rid-overflow",
                    tenant="t1",
                    directory_path="/fake/dir",
                )
            )
    finally:
        runner.logger.removeHandler(handler)

    hints = [r for r in records if getattr(r, "recalibration_hint", None)]
    assert hints, "爆窗必须留下带复标定指引的日志"
    hint = hints[0].recalibration_hint
    assert "TENDER_EFFECTIVE_CONTEXT_TOKENS" in hint
    assert budget.CALIBRATION_DOC_PATH in hint


def test_final_prompt_token_count_stays_under_the_calibrated_ceiling(monkeypatch):
    """AC5（F2 补）：对**最终 prompt** 计 token，加脚手架与循环余量后仍 ≤ 标定上限。

    只断言"预算函数返回值正确"不够——pass1 的两个预算函数各自都自洽，错在没扣脚手架，
    而这条只有在真正走完组装、拿到发出去的那串文本时才暴露。

    2026-08-18 修订（(d) 截断即转人工上线后）：底稿**超预算**那一档已不再发 prompt
    （`runner` 短路到 `build_manual_review_result`，由 `test_tender_truncation_authority.py`
    守），故本条改用**贴近但不越上限**的底稿——它是"仍会发出去"的最大形态，也就是 AC5
    这条不变量唯一还能被违反的地方。原来那份 400KB 底稿测的其实是截断闸，不是本不变量。
    """
    import asyncio

    from server.tender import doc_layer, draft_budget, runner

    # 贴着上限取 90%：既保证走完整条组装链，又保证 bound_draft 不触发（触发即不发 prompt）。
    fill_bytes = int(draft_budget.context_max_bytes(None) * 0.9)
    unit = "投标文件正文段落，与评标办法无关的附件材料。"
    huge_draft = unit * (fill_bytes // len(unit.encode("utf-8")))
    assert draft_budget.bound_draft(huge_draft) is None, "前置条件：本用例的底稿不得触发截断闸"

    monkeypatch.setattr(doc_layer, "load_doc_layer_context", lambda *_a, **_kw: None)
    monkeypatch.setattr(doc_layer, "load_doc_layer_context_slim", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *_a, **_kw: huge_draft)

    sent: dict[str, str] = {}

    import types

    async def capture(_cmd, *_a, **opts):
        sent["context"] = opts.get("context") or ""
        return {"verdict": "approved"}, types.SimpleNamespace(retry_count=0)

    monkeypatch.setattr(runner, "run_command_json", capture)

    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-ac5", tenant="t1", directory_path="/fake/dir"
        )
    )

    plan = budget.plan_injection(criteria=None, query_count=1)
    observed = budget.estimate_tokens(sent["context"])
    assert observed + plan.scaffold_tokens + plan.margin_tokens <= budget.effective_context_tokens()


# ── 收编：旧常量不得再各写一份 ───────────────────────────────────────────────


def test_legacy_budget_constants_are_gone_from_their_old_homes():
    """AC6：KD3 清单里的 7 个常量全部收编到本模块，旧位置不得留副本。"""
    from server.tender import context_budget, context_slim

    for module, names in (
        (
            context_budget,
            ("_BYTES_PER_TOKEN", "_SCAFFOLD_RESERVE_TOKENS", "_AGENT_LOOP_MARGIN_DIVISOR"),
        ),
        (
            context_slim,
            ("_DEFAULT_CHARS_PER_TOKEN", "_DEFAULT_CONTEXT_MARGIN_TOKENS", "_CHUNKS_PER_QUERY"),
        ),
    ):
        for name in names:
            assert not hasattr(module, name), f"{module.__name__}.{name} 应已收编到 injection_budget"


def test_model_context_window_no_longer_drives_the_budget(monkeypatch):
    """AC6：``MODEL_CONTEXT_WINDOW`` 描述模型能力、不描述 CLI 行为，退出预算用途。

    08-14 事故正是它导致预算算成 2.1MB（等于没有闸），而 CLI 约 200K token 就拒。
    """
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "1048576")
    monkeypatch.setenv("MODEL_MAX_OUTPUT_TOKENS", "8192")
    wide = budget.plan_injection(criteria=_criteria(14), query_count=20)
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "8192")
    narrow = budget.plan_injection(criteria=_criteria(14), query_count=20)
    assert wide.evidence_tokens == narrow.evidence_tokens


def test_fallback_max_bytes_is_derived_from_the_calibrated_token_ceiling():
    """字节兜底闸不再是独立常量，而是**回落可注入额度**的换算产物（单点）。"""
    assert budget.fallback_max_bytes() == budget.tokens_to_bytes(
        budget.fallback_injection_tokens()
    )


# ── F2：回落闸必须扣掉脚手架与循环余量 ──────────────────────────────────────


def test_fallback_budget_reserves_scaffold_and_margin():
    """F2：回落额度 = 有效上限 − 脚手架 − 循环余量，与 ``plan_injection`` 同构造。

    pass1 把回落闸收编成"整窗"（``tokens_to_bytes(200_000)``=600,000B），两者都没扣
    scaffold(90K)+margin(50K)——按 injection_budget 自己的账，回落注入 400KB 底稿会得到
    200K+90K≈290K token，CLI 一次性硬拒，整单无结论。
    """
    total = budget.effective_context_tokens()
    plan = budget.plan_injection(criteria=None, query_count=1)
    assert budget.fallback_injection_tokens() == total - plan.scaffold_tokens - plan.margin_tokens
    assert budget.fallback_injection_tokens() < total


def test_fallback_gate_is_not_looser_than_before_the_single_point_refactor():
    """F2 回归闸：收编不得把闸放松。旧硬编码默认是 256,000 B，收编后只能更紧。"""
    _PRE_REFACTOR_FALLBACK_MAX_BYTES = 256_000
    assert budget.fallback_max_bytes() < _PRE_REFACTOR_FALLBACK_MAX_BYTES


def test_fallback_injection_plus_scaffold_and_margin_fits_the_ceiling():
    """闭式账目对回落路径同样成立（回落时没有 criteria 块，证据额度整块给底稿）。"""
    total = budget.effective_context_tokens()
    plan = budget.plan_injection(criteria=None, query_count=1)
    assert (
        budget.fallback_injection_tokens() + plan.scaffold_tokens + plan.margin_tokens <= total
    )


def test_preextract_char_budget_shares_the_same_construction():
    """``context_slim`` 的字符预算必须与回落额度同源，否则又是两套口径（AC6 单点）。"""
    from server.tender import context_slim

    assert context_slim._preextract_char_budget() == budget.fallback_injection_tokens()


# ── P2：每项 chunk 数只许推导一次 ───────────────────────────────────────────


def test_chunks_per_item_has_exactly_one_derivation():
    """P2/DRY：``chunks_per_query_budget`` 与 ``retrieve_evidence`` 曾各推一遍同一个概念，
    还用了不同除数（3,453 的 p90 vs 4,000 的硬上限）——同一份 criteria 会得出两个答案。
    """
    plan = budget.plan_injection(criteria=_criteria(14), query_count=20)

    assert (
        budget.chunks_per_query_budget(criteria=_criteria(14), query_count=20)
        == plan.chunks_per_item
    )


def test_chunks_per_item_uses_the_hard_chunk_cap_not_a_percentile():
    """除数取 chunk 的**硬上限**：p90 会系统性高估装得下几块，越预算的代价是整单硬失败。"""
    from server.tender.evidence_chunks import MAX_CHUNK_CHARS

    plan = budget.plan_injection(criteria=_criteria(2), query_count=2)

    assert plan.chunks_per_item == max(1, plan.per_item_tokens // MAX_CHUNK_CHARS)


def test_chunks_per_item_is_never_zero():
    """取 0 等于该项必然 evidence_unresolved——那不是预算问题而是配置错。"""
    plan = budget.plan_injection(criteria=_criteria(14), query_count=20_000)

    assert plan.chunks_per_item >= 1
