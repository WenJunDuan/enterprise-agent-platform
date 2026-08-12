"""H3 pass3：补底稿重跑的失败语义（N1/N2/N3/N6）。

补跑是"尽力补救"：**它绝不能让手上那份可用的降级底稿变得更差**。pass2 实测的破口是
``run_*_doc_ocr`` 自己吞掉异常并写 ``ocr_text=NULL, status=failed``——补跑"正常返回"，
恢复逻辑不触发，degraded 底稿被清空，评标只能退回 inline 全量重 OCR。

本组测试全程用真实 store 行与真实 ``run_*_doc_ocr``，只把 OCR 引擎入口
（``doc_pipeline.prewarm_and_report``）换掉——恢复逻辑必须在真实落库路径上成立。
"""

from __future__ import annotations

import asyncio
import json
import uuid

from server.ocr.pipeline import OcrDocReport
from server.stores import tender_doc_store as store
from server.tender import doc_pipeline, doc_rerun


def _pid() -> str:
    return f"tp-{uuid.uuid4().hex[:16]}"


def _seed_impaired_bid(pid: str, bid_id: str, *, status: str = "degraded") -> None:
    store.upsert_bid_doc(
        project_id=pid,
        bid_id=bid_id,
        tenant="t1",
        bidder_name="投标人甲",
        bid_files="[]",
        ocr_status="running",
        case_path="/case/bid",
    )
    store.update_bid_doc_ocr(
        pid,
        bid_id,
        tenant="t1",
        ocr_text="旧的降级底稿",
        status=status,
        failed_files=["scan.pdf"],
    )


def _seed_impaired_project(pid: str, *, status: str = "partial") -> None:
    store.upsert_project_doc(
        project_id=pid,
        tenant="t1",
        tender_files="[]",
        ocr_status="running",
        case_path="/case/tender",
    )
    store.update_project_doc_ocr(
        pid,
        tenant="t1",
        ocr_text="旧的招标底稿",
        ocr_clarity=None,
        status=status,
        failed_files=["chapter-3.pdf"],
    )


def _rows(pid: str, bid_id: str) -> tuple[dict | None, dict | None]:
    return store.get_project_doc(pid, "t1"), store.get_bid_doc(pid, bid_id, "t1")


def test_failed_rerun_restores_both_text_and_status(monkeypatch):
    """N1：补跑失败后，ocr_text 与 ocr_status 都必须回到补跑前的值。

    此前只回滚 status：run_bid_doc_ocr 的失败分支已经把 ocr_text 无条件 SET 成 NULL，
    读层随后拿不到底稿 → 退回 inline 全量重 OCR（正是本 sprint 要杀的负载来源）。
    """
    pid, bid_id = _pid(), store.new_bid_id()
    _seed_impaired_bid(pid, bid_id)

    def _engine_down(*_a, **_k):
        raise RuntimeError("OCR engine down")

    monkeypatch.setattr(doc_pipeline, "prewarm_and_report", _engine_down)
    marked: list[tuple] = []
    real_mark = doc_rerun.mark_doc_rerunning

    def _spy_mark(*args, **kwargs):
        marked.append(args)
        real_mark(*args, **kwargs)  # 真的置 running（不 mock 成 no-op）

    monkeypatch.setattr(doc_rerun, "mark_doc_rerunning", _spy_mark)

    asyncio.run(
        doc_rerun.rerun_prewarm_for_degraded_docs(pid, bid_id, "t1", _rows(pid, bid_id))
    )

    row = store.get_bid_doc(pid, bid_id, "t1")
    assert marked, "补跑前确实置过 running（去重语义仍在）"
    assert row["ocr_text"] == "旧的降级底稿"
    assert row["ocr_status"] == "degraded"
    assert json.loads(row["ocr_failed_files"]) == ["scan.pdf"]


def test_successful_rerun_keeps_the_new_result(monkeypatch):
    """N1 反向：补跑成功（ready）不得被"恢复"逻辑回滚掉。"""
    pid, bid_id = _pid(), store.new_bid_id()
    _seed_impaired_bid(pid, bid_id)
    monkeypatch.setattr(
        doc_pipeline,
        "prewarm_and_report",
        lambda *_a, **_k: ("补齐后的底稿", OcrDocReport("ready", (), ())),
    )

    asyncio.run(
        doc_rerun.rerun_prewarm_for_degraded_docs(pid, bid_id, "t1", _rows(pid, bid_id))
    )

    row = store.get_bid_doc(pid, bid_id, "t1")
    assert row["ocr_status"] == "ready"
    assert row["ocr_text"] == "补齐后的底稿"


def test_partial_success_only_rolls_back_the_unfinished_segment(monkeypatch):
    """N2：招标层已补好、投标层超时 → 只回滚投标层，不能把补好的招标层刷回 degraded。"""
    pid, bid_id = _pid(), store.new_bid_id()
    _seed_impaired_project(pid)
    _seed_impaired_bid(pid, bid_id)
    monkeypatch.setattr(doc_rerun, "rerun_budget_sec", lambda **_k: 0.15)

    async def _slow_bid(*_a, **_k):
        await asyncio.sleep(10)

    monkeypatch.setattr(
        doc_pipeline,
        "prewarm_and_report",
        lambda *_a, **_k: ("补齐后的招标底稿", OcrDocReport("ready", (), ())),
    )
    monkeypatch.setattr(doc_pipeline, "run_bid_doc_ocr", _slow_bid)

    asyncio.run(
        doc_rerun.rerun_prewarm_for_degraded_docs(pid, bid_id, "t1", _rows(pid, bid_id))
    )

    project_row = store.get_project_doc(pid, "t1")
    bid_row = store.get_bid_doc(pid, bid_id, "t1")
    assert project_row["ocr_status"] == "ready", "补好的段不得被回滚"
    assert project_row["ocr_text"] == "补齐后的招标底稿"
    assert bid_row["ocr_status"] == "degraded", "未完成的段回到补跑前状态"
    assert bid_row["ocr_text"] == "旧的降级底稿"


def test_timed_out_rerun_never_leaves_the_row_stuck_running(monkeypatch):
    """N6：补跑超时后行不能停在 running——那会让前端轮询永不终止（pass1-F1 锁死形态）。"""
    pid, bid_id = _pid(), store.new_bid_id()
    _seed_impaired_bid(pid, bid_id)
    monkeypatch.setattr(doc_rerun, "rerun_budget_sec", lambda **_k: 0.1)

    async def _slow(*_a, **_k):
        await asyncio.sleep(10)

    monkeypatch.setattr(doc_pipeline, "run_bid_doc_ocr", _slow)

    asyncio.run(
        doc_rerun.rerun_prewarm_for_degraded_docs(pid, bid_id, "t1", _rows(pid, bid_id))
    )

    assert store.get_bid_doc(pid, bid_id, "t1")["ocr_status"] == "degraded"


def test_rerun_budget_shrinks_with_the_budget_already_spent(monkeypatch):
    """N3：等待预热吃掉的时间要计入——等满上限后补跑预算必须显著收缩。"""
    monkeypatch.setenv("TENDER_TIMEOUT_SEC", "600")

    fresh = doc_rerun.rerun_budget_sec()
    after_long_wait = doc_rerun.rerun_budget_sec(spent_sec=400)  # 等满 300s 上限之后

    assert fresh > 10
    assert after_long_wait < fresh / 2
    assert doc_rerun.rerun_budget_sec(spent_sec=10_000) >= 1.0  # 下界仍在，不会退化成 0
