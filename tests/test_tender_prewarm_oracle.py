"""H3 KD5/KD2：预热 in-flight oracle、双跑消解、非 ready 底稿的评标入口决策。

实测病灶：评标等预热 360s 超时后**无条件**回落 inline 全量重 OCR，而预热并不取消 → 同一批
文件两条流水线并跑，负载翻倍形成正反馈。修法是先判"预热是否真的在途"（doc 行 running +
updated_at 新鲜），在途就继续等（上限从 tender 总预算派生），不在途才回落。
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta

import pytest

from server.tender import doc_layer, doc_rerun, runner


def _row(status: str, *, age_sec: float = 0.0, text: str = "底稿", **extra) -> dict:
    updated_at = (datetime.now(UTC) - timedelta(seconds=age_sec)).isoformat()
    return {
        "bid_id": "bid-1",
        "bidder_name": "投标人甲",
        "ocr_status": status,
        "ocr_text": text,
        "updated_at": updated_at,
        **extra,
    }


def _patch_rows(monkeypatch, project_rows, bid_rows) -> None:
    """按调用次序逐个返回 doc 行快照（最后一个快照重复供给）。"""

    def _next(rows: list[dict | None]):
        def _reader(*_args, **_kwargs):
            return rows[0] if len(rows) == 1 else rows.pop(0)

        return _reader

    monkeypatch.setattr(doc_layer, "get_project_doc", _next(list(project_rows)))
    monkeypatch.setattr(doc_layer, "get_bid_doc", _next(list(bid_rows)))


def _fast_polling(monkeypatch) -> None:
    monkeypatch.setattr(doc_layer, "DOC_LAYER_POLL_SEC", 0.01)


# ── in-flight oracle ─────────────────────────────────────────────────────────


def test_fresh_running_row_is_in_flight_and_stale_one_is_not():
    assert doc_layer.is_prewarm_in_flight(_row("running", age_sec=5), stale_sec=300) is True
    assert doc_layer.is_prewarm_in_flight(_row("running", age_sec=900), stale_sec=300) is False
    assert doc_layer.is_prewarm_in_flight(_row("ready"), stale_sec=300) is False
    assert doc_layer.is_prewarm_in_flight(None, stale_sec=300) is False


def test_wait_returns_terminal_when_both_docs_reached_a_terminal_status(monkeypatch):
    _fast_polling(monkeypatch)
    _patch_rows(monkeypatch, [_row("ready")], [_row("degraded")])

    assert asyncio.run(doc_layer.wait_doc_layer_ready("tp-1", "bid-1", "t1")) == "terminal"


def test_wait_keeps_waiting_while_prewarm_is_in_flight(monkeypatch):
    """AC6：预热在途 → 继续等到它完成，不发起 inline。"""
    _fast_polling(monkeypatch)
    _patch_rows(
        monkeypatch,
        [_row("ready")],
        [_row("running", age_sec=1), _row("running", age_sec=1), _row("ready")],
    )

    assert asyncio.run(doc_layer.wait_doc_layer_ready("tp-1", "bid-1", "t1")) == "terminal"


def test_stale_running_row_is_treated_as_failed_immediately(monkeypatch):
    """进程重启遗留的僵尸 running：不等，直接放行 inline 回落。"""
    _fast_polling(monkeypatch)
    _patch_rows(monkeypatch, [_row("ready")], [_row("running", age_sec=9999)])

    assert asyncio.run(doc_layer.wait_doc_layer_ready("tp-1", "bid-1", "t1")) == "stale"


def test_missing_rows_do_not_wait(monkeypatch):
    _fast_polling(monkeypatch)
    _patch_rows(monkeypatch, [None], [None])

    assert asyncio.run(doc_layer.wait_doc_layer_ready("tp-1", "bid-1", "t1")) == "absent"


def test_wait_cap_is_derived_from_tender_budget_and_ends_the_wait(monkeypatch):
    """派生上限到期仍在途 → 结束等待并放行 inline 回落一次（不无限等）。"""
    _fast_polling(monkeypatch)
    monkeypatch.setenv("TENDER_TIMEOUT_SEC", "0.06")  # 上限 = 50% → 0.03s
    _patch_rows(monkeypatch, [_row("ready")], [_row("running", age_sec=1)])

    assert asyncio.run(doc_layer.wait_doc_layer_ready("tp-1", "bid-1", "t1")) == "wait_cap_reached"


def test_unknown_ocr_status_fails_fast(monkeypatch):
    """未知枚举绝不静默当 ready（新状态漏接会被立刻发现，而不是悄悄按老路走）。"""
    _fast_polling(monkeypatch)
    _patch_rows(monkeypatch, [_row("ready")], [_row("almost-ready")])

    with pytest.raises(ValueError, match="ocr_status"):
        asyncio.run(doc_layer.wait_doc_layer_ready("tp-1", "bid-1", "t1"))


def test_wait_logs_progress_while_waiting(monkeypatch, caplog):
    """等待期间输出结构化日志（并发排查的最小可观测集）。"""
    _fast_polling(monkeypatch)
    monkeypatch.setattr(doc_layer, "DOC_LAYER_LOG_INTERVAL_SEC", 0.0)
    _patch_rows(
        monkeypatch, [_row("ready")], [_row("running", age_sec=1), _row("ready")]
    )

    with caplog.at_level("INFO"):
        asyncio.run(doc_layer.wait_doc_layer_ready("tp-1", "bid-1", "t1"))

    assert any(record.message == "tender_doc_layer_wait" for record in caplog.records)


# ── 非 ready 底稿的入口决策 ──────────────────────────────────────────────────


def test_degraded_doc_layer_context_is_used_not_discarded(monkeypatch):
    """AC2：degraded 底稿仍可复用（它有内容），不该退回 inline 重 OCR。"""
    monkeypatch.setattr(
        doc_layer, "get_project_doc", lambda *_a: _row("ready", text="招标底稿")
    )
    monkeypatch.setattr(
        doc_layer, "get_bid_doc", lambda *_a: _row("degraded", text="投标底稿")
    )

    result = doc_layer.load_doc_layer_context("tp-1", "bid-1", "t1")

    assert result is not None
    assert "投标底稿" in result


def test_failed_doc_layer_context_still_returns_none(monkeypatch):
    monkeypatch.setattr(doc_layer, "get_project_doc", lambda *_a: _row("ready"))
    monkeypatch.setattr(doc_layer, "get_bid_doc", lambda *_a: _row("failed", text=None))

    assert doc_layer.load_doc_layer_context("tp-1", "bid-1", "t1") is None


def test_degraded_docs_are_rerun_exactly_once(monkeypatch):
    """AC2：入口对 degraded/partial 先自动重跑一次预热 OCR（第二次不再重跑）。"""
    reruns: list[tuple[str, str]] = []

    async def _fake_bid_ocr(project_id, bid_id, case_path, *, tenant, purpose=None):
        reruns.append(("bid", case_path))

    async def _fake_project_ocr(
        project_id, case_path, *, tenant, purpose=None, run_info_extraction=True
    ):
        reruns.append(("project", case_path))
        assert run_info_extraction is False, "重跑只补 OCR，不该再触发一次 criteria 抽取"

    from server.tender import doc_pipeline

    monkeypatch.setattr(doc_pipeline, "run_bid_doc_ocr", _fake_bid_ocr)
    monkeypatch.setattr(doc_pipeline, "run_project_doc_ocr", _fake_project_ocr)

    rows = (
        _row("partial", case_path="/case/tender"),
        _row("degraded", case_path="/case/bid"),
    )
    asyncio.run(doc_rerun.rerun_prewarm_for_degraded_docs("tp-1", "bid-1", "t1", rows))

    assert reruns == [("project", "/case/tender"), ("bid", "/case/bid")]


def test_rerun_is_skipped_when_case_path_is_unknown(monkeypatch):
    """老数据没有 case_path → 不能凭空重跑（也不该崩），只走 warning 路径。"""

    async def _explode(*_a, **_k):
        raise AssertionError("must not rerun without a known case_path")

    from server.tender import doc_pipeline

    monkeypatch.setattr(doc_pipeline, "run_bid_doc_ocr", _explode)
    monkeypatch.setattr(doc_pipeline, "run_project_doc_ocr", _explode)

    asyncio.run(
        doc_rerun.rerun_prewarm_for_degraded_docs(
            "tp-1", "bid-1", "t1", (_row("ready"), _row("partial"))
        )
    )


def test_warnings_name_the_degraded_and_missing_files():
    """AC3：结论 warning 点名失败文件。"""
    warnings = runner._ocr_integrity_warnings(
        _row("ready"),
        _row("partial", ocr_failed_files='["broken-1.pdf", "broken-2.pdf"]'),
    )

    assert len(warnings) == 1
    assert warnings[0]["status"] == "partial"
    assert warnings[0]["files"] == ["broken-1.pdf", "broken-2.pdf"]
    assert "broken-1.pdf" in warnings[0]["message"]


def test_warning_injection_lands_in_extracted_data():
    payload = {"claim_id": "c1", "extracted_data": {"scoring": []}}
    runner._inject_ocr_warnings(payload, [{"status": "degraded", "files": [], "message": "x"}])

    assert payload["extracted_data"]["ocr_warnings"][0]["message"] == "x"
    assert payload["extracted_data"]["scoring"] == []


def test_warning_injection_tolerates_missing_extracted_data():
    payload: dict = {"claim_id": "c1"}
    runner._inject_ocr_warnings(payload, [{"status": "partial", "files": ["a"], "message": "y"}])

    assert payload["extracted_data"]["ocr_warnings"][0]["files"] == ["a"]


# ── 端到端入口决策（AC2/AC6）────────────────────────────────────────────────


def _fake_meta(request_id: str):
    from server.common.agent_bridge import AgentRunMeta

    return AgentRunMeta(
        request_id=request_id,
        conversation_id="conv-test",
        claude_session_id="sess-test",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="common/audit-result.schema.json",
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def _patch_command(monkeypatch, captured: dict) -> None:
    async def _fake_run_command_json(command_name, *arguments, schema_name, **opts):
        captured["context"] = opts.get("context")
        return {"verdict": "manual_review", "extracted_data": {}}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(runner, "run_command_json", _fake_run_command_json)


def _count_inline_ocr(monkeypatch, inline_calls: list) -> None:
    monkeypatch.setattr(
        runner,
        "ocr_preprocess_block",
        lambda *_a, **_k: inline_calls.append(True) or "inline 底稿",
    )


def test_in_flight_prewarm_never_triggers_a_second_inline_ocr(monkeypatch):
    """AC6：预热在途 → 等它完成并复用，进程内只有一套 OCR（inline 调用计数 = 0）。"""
    _fast_polling(monkeypatch)
    captured: dict = {}
    inline_calls: list = []
    _patch_command(monkeypatch, captured)
    _count_inline_ocr(monkeypatch, inline_calls)
    _patch_rows(
        monkeypatch,
        [_row("ready", text="招标底稿")],
        [_row("running", age_sec=1, text=None), _row("ready", text="投标底稿")],
    )

    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-inflight",
            tenant="t1",
            directory_path="/fake/dir",
            project_id="tp-1",
            bid_id="bid-1",
        )
    )

    assert inline_calls == []
    assert "投标底稿" in captured["context"]


def test_failed_prewarm_still_falls_back_to_inline(monkeypatch):
    """AC6：预热 failed → inline 回落照常（此时预热已停，无双跑）。"""
    _fast_polling(monkeypatch)
    captured: dict = {}
    inline_calls: list = []
    _patch_command(monkeypatch, captured)
    _count_inline_ocr(monkeypatch, inline_calls)
    _patch_rows(monkeypatch, [_row("ready")], [_row("failed", text=None)])

    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-failed",
            tenant="t1",
            directory_path="/fake/dir",
            project_id="tp-1",
            bid_id="bid-1",
        )
    )

    assert inline_calls == [True]


def test_degraded_doc_reruns_once_then_warns_and_keeps_evaluating(monkeypatch):
    """AC2/AC3：重跑一次后仍 degraded/partial → 结论带结构化 warning 且评标照跑。"""
    _fast_polling(monkeypatch)
    captured: dict = {}
    inline_calls: list = []
    _patch_command(monkeypatch, captured)
    _count_inline_ocr(monkeypatch, inline_calls)
    reruns: list = []

    async def _rerun(*_a, spent_sec=0.0, **_k):
        # N3：等预热花掉的时间必须被实测出来并透传进补跑预算，不能永远按 0 算。
        reruns.append(spent_sec)

    monkeypatch.setattr(doc_rerun, "rerun_prewarm_for_degraded_docs", _rerun)
    _patch_rows(
        monkeypatch,
        [_row("ready", text="招标底稿")],
        [
            _row(
                "partial",
                text="投标底稿",
                case_path="/case/bid",
                ocr_failed_files='["chapter-3.pdf"]',
            )
        ],
    )

    payload, _meta = asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-degraded",
            tenant="t1",
            directory_path="/fake/dir",
            project_id="tp-1",
            bid_id="bid-1",
        )
    )

    assert len(reruns) == 1, "只重跑一次"
    assert reruns[0] > 0, "补跑预算要扣掉等预热已经花掉的时间（N3 实测透传）"
    assert inline_calls == [], "有可用底稿就不该再跑一遍 inline"
    warnings = payload["extracted_data"]["ocr_warnings"]
    assert warnings[0]["files"] == ["chapter-3.pdf"]
    assert "chapter-3.pdf" in captured["context"], "告警也要进模型上下文，评分项才不会被静默"


def test_loader_reraises_enum_violation_instead_of_swallowing_it(monkeypatch):
    """F4：未知枚举的 fail-fast 不能被 loader 的 blanket catch 吞成"回落 inline"。

    同一个 ValueError 在 wait 里抛、在 loader 里被吞 = 两种归宿；漏接新枚举时到底炸不炸
    取决于走到哪条路径，这正是 fail-fast 要杜绝的不确定性。
    """
    monkeypatch.setattr(doc_layer, "get_project_doc", lambda *_a: _row("ready"))
    monkeypatch.setattr(doc_layer, "get_bid_doc", lambda *_a: _row("almost-ready"))

    with pytest.raises(ValueError, match="ocr_status"):
        doc_layer.load_doc_layer_context("tp-1", "bid-1", "t1")
    with pytest.raises(ValueError, match="ocr_status"):
        doc_layer.load_doc_layer_context_slim("tp-1", "bid-1", "t1")


def test_loader_still_falls_back_on_db_failure(monkeypatch):
    """F4 反向：DB/IO 故障仍走静默回落（blanket catch 只保留给这类外部故障）。"""

    def _boom(*_a, **_k):
        raise OSError("database is locked")

    monkeypatch.setattr(doc_layer, "get_project_doc", _boom)

    assert doc_layer.load_doc_layer_context("tp-1", "bid-1", "t1") is None
    assert doc_layer.load_doc_layer_context_slim("tp-1", "bid-1", "t1") is None


def test_rerun_is_bounded_by_a_timeout_and_degrades_to_warning(monkeypatch):
    """F3：重跑挂在评标关键路径上，必须有预算上限；超时放弃（调用方走 warning），不拖垮评标。"""
    # pass3-F4：签名须跟生产调用 rerun_budget_sec(spent_sec=...) 一致，否则 TypeError 被
    # blanket catch 吞掉、_never_finishes 从未被 await，本测试空转无鉴别力。
    monkeypatch.setattr(doc_rerun, "rerun_budget_sec", lambda **_k: 0.05)
    from server.tender import doc_pipeline

    async def _never_finishes(*_a, **_k):
        await asyncio.sleep(10)

    monkeypatch.setattr(doc_pipeline, "run_bid_doc_ocr", _never_finishes)
    monkeypatch.setattr(doc_rerun, "mark_doc_rerunning", lambda *_a, **_k: None)
    started = time.monotonic()

    asyncio.run(
        doc_rerun.rerun_prewarm_for_degraded_docs(
            "tp-1", "bid-1", "t1", (_row("ready"), _row("partial", case_path="/case/bid"))
        )
    )

    assert time.monotonic() - started < 2, "重跑必须在预算内放弃，不能拖着评标一起等"


def test_rerun_marks_row_running_so_concurrent_evaluations_dedupe(monkeypatch):
    """F3：重跑前把行置回 running 并起心跳——并发评标据此判 in-flight，不会各跑一遍。"""
    from server.tender import doc_pipeline

    marked: list[tuple] = []
    monkeypatch.setattr(
        doc_rerun, "mark_doc_rerunning", lambda *args, **kwargs: marked.append(args)
    )

    async def _fake_bid_ocr(*_a, **_k):
        return None

    monkeypatch.setattr(doc_pipeline, "run_bid_doc_ocr", _fake_bid_ocr)

    asyncio.run(
        doc_rerun.rerun_prewarm_for_degraded_docs(
            "tp-1", "bid-1", "t1", (_row("ready"), _row("degraded", case_path="/case/bid"))
        )
    )

    assert marked, "重跑前必须把 doc 行置 running（复用 oracle 天然去重并发重跑）"


def test_wait_cap_shrinks_with_the_already_spent_budget(monkeypatch):
    """spec D2：等待上限要减去已耗预算，不能每次进函数都按"整份预算的一半"重新起算。"""
    from server.platform.config import get_ocr_concurrency_settings

    monkeypatch.setenv("TENDER_TIMEOUT_SEC", "600")
    full = get_ocr_concurrency_settings().doc_layer_wait_cap_sec
    assert full == 300.0

    shrunk = get_ocr_concurrency_settings(spent_sec=400).doc_layer_wait_cap_sec
    # 剩余 200s，扣掉评标保留量后只能更小，且不得为负。
    assert 0 <= shrunk < 200
    assert get_ocr_concurrency_settings(spent_sec=10_000).doc_layer_wait_cap_sec == 0


def test_wait_cap_reached_falls_back_to_inline_once_with_warning(monkeypatch):
    """F8：派生上限到期仍在途 → inline 回落一次 + prewarm_timeout warning（端到端）。"""
    _fast_polling(monkeypatch)
    monkeypatch.setenv("TENDER_TIMEOUT_SEC", "0.02")  # 上限 = 50% → 10ms
    captured: dict = {}
    inline_calls: list = []
    _patch_command(monkeypatch, captured)
    _count_inline_ocr(monkeypatch, inline_calls)
    _patch_rows(monkeypatch, [_row("ready")], [_row("running", age_sec=1, text=None)])

    payload, _meta = asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-cap",
            tenant="t1",
            directory_path="/fake/dir",
            project_id="tp-1",
            bid_id="bid-1",
        )
    )

    assert inline_calls == [True], "上限到期后回落 inline 恰好一次"
    warnings = payload["extracted_data"]["ocr_warnings"]
    assert [w["status"] for w in warnings] == ["prewarm_timeout"]


def test_ready_docs_produce_no_warning_and_no_rerun(monkeypatch):
    _fast_polling(monkeypatch)
    captured: dict = {}
    _patch_command(monkeypatch, captured)
    monkeypatch.setattr(
        doc_rerun,
        "rerun_prewarm_for_degraded_docs",
        lambda *_a, **_k: pytest.fail("ready 底稿不该触发重跑"),
    )
    _patch_rows(monkeypatch, [_row("ready", text="招标底稿")], [_row("ready", text="投标底稿")])

    payload, _meta = asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-ready",
            tenant="t1",
            directory_path="/fake/dir",
            project_id="tp-1",
            bid_id="bid-1",
        )
    )

    assert "ocr_warnings" not in payload["extracted_data"]
