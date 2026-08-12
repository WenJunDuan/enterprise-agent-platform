"""H3 KD2/KD5：doc 层 ocr_status 扩档（degraded/partial）+ failed_files 落库 + 预热心跳。

此前 doc 层只有 ready|failed 两档：任一页降级 Tesseract 的低质底稿、以及 10 个文件失败 2 个的
残缺底稿，都以 ``ready`` 永久落库 → 之后永不重跑、部分失败对状态机完全不可见。
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from server.ocr import prewarm_scheduler
from server.ocr.pipeline import OcrDocReport
from server.stores import tender_doc_store as store
from server.tender import doc_pipeline


def _pid() -> str:
    return f"tp-{uuid.uuid4().hex[:16]}"


def _seed_project(pid: str, *, case_path: str = "/case/tender") -> None:
    store.upsert_project_doc(
        project_id=pid,
        tenant="t1",
        tender_files="[]",
        ocr_status="running",
        case_path=case_path,
    )


def _seed_bid(pid: str, bid_id: str, *, case_path: str = "/case/bid") -> None:
    store.upsert_bid_doc(
        project_id=pid,
        bid_id=bid_id,
        tenant="t1",
        bidder_name="投标人甲",
        bid_files="[]",
        ocr_status="running",
        case_path=case_path,
    )


# ── store：枚举 + failed_files + case_path ────────────────────────────────────


def test_ocr_statuses_include_degraded_and_partial():
    assert {"pending", "running", "ready", "degraded", "partial", "failed"} == store.OCR_STATUSES


@pytest.mark.parametrize("status", ["degraded", "partial"])
def test_update_bid_doc_ocr_persists_new_statuses_with_failed_files(status):
    pid, bid_id = _pid(), store.new_bid_id()
    _seed_bid(pid, bid_id)

    store.update_bid_doc_ocr(
        pid,
        bid_id,
        tenant="t1",
        ocr_text="底稿",
        status=status,
        failed_files=["broken-1.pdf", "broken-2.pdf"],
    )

    row = store.get_bid_doc(pid, bid_id, "t1")
    assert row["ocr_status"] == status
    assert json.loads(row["ocr_failed_files"]) == ["broken-1.pdf", "broken-2.pdf"]


def test_update_project_doc_ocr_persists_failed_files():
    pid = _pid()
    _seed_project(pid)

    store.update_project_doc_ocr(
        pid,
        tenant="t1",
        ocr_text="底稿",
        ocr_clarity=None,
        status="partial",
        failed_files=["x.pdf"],
    )

    row = store.get_project_doc(pid, "t1")
    assert row["ocr_status"] == "partial"
    assert json.loads(row["ocr_failed_files"]) == ["x.pdf"]


@pytest.mark.parametrize(
    "writer",
    ["bid", "project"],
)
def test_unknown_ocr_status_is_rejected_fail_fast(writer):
    """未知枚举值绝不静默落库（落进去后读侧只能猜，最坏被当 ready）。"""
    pid, bid_id = _pid(), store.new_bid_id()
    _seed_bid(pid, bid_id)
    _seed_project(pid)

    with pytest.raises(ValueError, match="ocr_status"):
        if writer == "bid":
            store.update_bid_doc_ocr(
                pid, bid_id, tenant="t1", ocr_text="x", status="mostly-ready"
            )
        else:
            store.update_project_doc_ocr(
                pid, tenant="t1", ocr_text="x", ocr_clarity=None, status="mostly-ready"
            )


def test_upsert_persists_case_path_for_reruns():
    """评标入口要能"自动重跑一次该 doc 的预热 OCR"，就必须知道文件落在哪。"""
    pid, bid_id = _pid(), store.new_bid_id()
    _seed_project(pid, case_path="/case/tender-42")
    _seed_bid(pid, bid_id, case_path="/case/bid-42")

    assert store.get_project_doc(pid, "t1")["case_path"] == "/case/tender-42"
    assert store.get_bid_doc(pid, bid_id, "t1")["case_path"] == "/case/bid-42"


def test_touch_only_refreshes_rows_still_running():
    """心跳只刷在途行：终态行被"刷新"会让 stale 判定永远不触发。"""
    pid, bid_id = _pid(), store.new_bid_id()
    _seed_bid(pid, bid_id)
    before = store.get_bid_doc(pid, bid_id, "t1")["updated_at"]

    store.touch_bid_doc_ocr(pid, bid_id, tenant="t1")
    touched = store.get_bid_doc(pid, bid_id, "t1")["updated_at"]

    store.update_bid_doc_ocr(pid, bid_id, tenant="t1", ocr_text="ok", status="ready")
    finished_at = store.get_bid_doc(pid, bid_id, "t1")["updated_at"]
    store.touch_bid_doc_ocr(pid, bid_id, tenant="t1")

    assert touched >= before
    assert store.get_bid_doc(pid, bid_id, "t1")["updated_at"] == finished_at


def test_touch_project_doc_only_refreshes_running_rows():
    pid = _pid()
    _seed_project(pid)
    store.touch_project_doc_ocr(pid, tenant="t1")
    assert store.get_project_doc(pid, "t1")["ocr_status"] == "running"

    store.update_project_doc_ocr(
        pid, tenant="t1", ocr_text="ok", ocr_clarity=None, status="ready"
    )
    finished_at = store.get_project_doc(pid, "t1")["updated_at"]
    store.touch_project_doc_ocr(pid, tenant="t1")

    assert store.get_project_doc(pid, "t1")["updated_at"] == finished_at


# ── doc_pipeline：报告状态落库 + 心跳 ─────────────────────────────────────────


def _patch_report(monkeypatch, report: OcrDocReport, text: str = "底稿正文") -> None:
    monkeypatch.setattr(
        doc_pipeline, "prewarm_and_report", lambda *_a, **_k: (text, report)
    )


@pytest.mark.parametrize(
    "report,expected_status,expected_failed",
    [
        (OcrDocReport("ready", (), ()), "ready", []),
        # F6：降级文件也进"有问题的文件"清单，warning 才点得出名字。
        (OcrDocReport("degraded", (), ("scan.pdf",)), "degraded", ["scan.pdf"]),
        (
            OcrDocReport("partial", ("broken.pdf",), ("scan.pdf",)),
            "partial",
            ["broken.pdf", "scan.pdf"],
        ),
    ],
)
def test_bid_doc_ocr_writes_report_status(
    monkeypatch, report, expected_status, expected_failed
):
    """AC2/AC3：degraded/partial 如实落库，绝不冒充 ready。"""
    pid, bid_id = _pid(), store.new_bid_id()
    _seed_bid(pid, bid_id)
    _patch_report(monkeypatch, report)

    asyncio.run(doc_pipeline.run_bid_doc_ocr(pid, bid_id, "/case/bid", tenant="t1"))

    row = store.get_bid_doc(pid, bid_id, "t1")
    assert row["ocr_status"] == expected_status
    assert row["ocr_text"] == "底稿正文"
    if expected_failed is not None:
        assert json.loads(row["ocr_failed_files"] or "[]") == expected_failed


def test_bid_doc_ocr_failed_report_writes_failed(monkeypatch):
    pid, bid_id = _pid(), store.new_bid_id()
    _seed_bid(pid, bid_id)
    _patch_report(monkeypatch, OcrDocReport("failed", ("a.pdf",), ()), text="（无识别内容）")

    asyncio.run(doc_pipeline.run_bid_doc_ocr(pid, bid_id, "/case/bid", tenant="t1"))

    row = store.get_bid_doc(pid, bid_id, "t1")
    assert row["ocr_status"] == "failed"
    assert row["ocr_text"] is None


def test_project_doc_degraded_still_runs_criteria_extraction(monkeypatch):
    """降级底稿仍可解析评分标准——degraded 是质量信号，不是"没有底稿"。"""
    pid = _pid()
    _seed_project(pid)
    _patch_report(monkeypatch, OcrDocReport("degraded", (), ("scan.pdf",)))
    extracted: list[str] = []

    async def _fake_extract(project_id, case_path, ocr_text, tenant):
        extracted.append(ocr_text)

    monkeypatch.setattr(doc_pipeline, "extract_project_doc_info", _fake_extract)

    asyncio.run(doc_pipeline.run_project_doc_ocr(pid, "/case/tender", tenant="t1"))

    assert store.get_project_doc(pid, "t1")["ocr_status"] == "degraded"
    assert extracted == ["底稿正文"]


def test_prewarm_touches_updated_at_on_a_doc_level_ticker(monkeypatch):
    """KD5：心跳是 doc 级周期 ticker，不是"每处理完一个文件才 touch"。

    单个大文件跑满整个预热窗口时也必须持续刷新——否则 updated_at 变陈旧，评标侧 in-flight
    oracle 误判 stale → inline 双跑复活（正是本 sprint 要杀的病灶）。
    """
    pid, bid_id = _pid(), store.new_bid_id()
    _seed_bid(pid, bid_id)
    monkeypatch.setattr(prewarm_scheduler, "PREWARM_TOUCH_INTERVAL_SEC", 0.01)
    touches: list[int] = []
    monkeypatch.setattr(
        doc_pipeline, "touch_bid_doc_ocr", lambda *_a, **_k: touches.append(1)
    )

    def _slow_single_file_ocr(*_a, **_k):
        import time

        time.sleep(0.08)  # 一个大文件，中间没有"文件处理完"这种时机
        return "底稿正文", OcrDocReport("ready", (), ())

    monkeypatch.setattr(doc_pipeline, "prewarm_and_report", _slow_single_file_ocr)

    asyncio.run(doc_pipeline.run_bid_doc_ocr(pid, bid_id, "/case/bid", tenant="t1"))

    assert len(touches) >= 2, "ticker 必须在单文件识别期间反复刷新 updated_at"
    assert store.get_bid_doc(pid, bid_id, "t1")["ocr_status"] == "ready"


def test_degraded_and_failed_files_survive_the_real_seam_into_the_warning(monkeypatch):
    """F6/spec-M1/G1：穿透 summarize_ocr_results → update_bid_doc_ocr → 读回 → 结论 warning。

    只 mock 到 OCR 引擎边界（``pipeline.extract_dir``），中间的归纳、落库、读回、渲染全走真实
    实现——此前测试用手工构造的 doc 行绕过了这条接缝，degraded 文件名一路丢到 warning 里为空。
    """
    from server.ocr import pipeline
    from server.tender import runner

    pid, bid_id = _pid(), store.new_bid_id()
    _seed_bid(pid, bid_id)
    results = [
        {"path": "/case/bid/ok.pdf", "kind": "ocr", "pages": [{"markdown": "正文", "page_number": 1}]},
        {
            "path": "/case/bid/scan.pdf",
            "kind": "ocr",
            "pages": [{"markdown": "降级正文", "page_number": 1}],
            "degraded": True,
        },
        {"path": "/case/bid/broken.pdf", "kind": "error", "error": "boom"},
    ]
    monkeypatch.setattr(pipeline, "extract_dir", lambda *_a, **_k: results)

    asyncio.run(doc_pipeline.run_bid_doc_ocr(pid, bid_id, "/case/bid", tenant="t1"))

    row = store.get_bid_doc(pid, bid_id, "t1")
    assert row["ocr_status"] == "partial"
    warnings = runner._ocr_integrity_warnings(None, row)
    assert len(warnings) == 1
    assert set(warnings[0]["files"]) == {"broken.pdf", "scan.pdf"}
    assert "scan.pdf" in warnings[0]["message"], "降级文件也要点名（此前只点名彻底失败的）"


def test_degraded_only_doc_still_names_the_degraded_file(monkeypatch):
    """F6：纯 degraded（无失败文件）时 warning 也必须点名，否则用户无从判断影响面。"""
    from server.ocr import pipeline
    from server.tender import runner

    pid, bid_id = _pid(), store.new_bid_id()
    _seed_bid(pid, bid_id)
    results = [
        {
            "path": "/case/bid/scan.pdf",
            "kind": "ocr",
            "pages": [{"markdown": "降级正文", "page_number": 1}],
            "degraded": True,
        }
    ]
    monkeypatch.setattr(pipeline, "extract_dir", lambda *_a, **_k: results)

    asyncio.run(doc_pipeline.run_bid_doc_ocr(pid, bid_id, "/case/bid", tenant="t1"))

    row = store.get_bid_doc(pid, bid_id, "t1")
    assert row["ocr_status"] == "degraded"
    assert runner._ocr_integrity_warnings(None, row)[0]["files"] == ["scan.pdf"]


def _age_bid_row(pid: str, bid_id: str, seconds: float) -> None:
    """把行的 updated_at 人为调旧，模拟"已经排队很久"。"""
    from datetime import datetime, timedelta, timezone

    from server.platform.paths import PLATFORM_DB_FILE
    from server.platform.sqlite_store import connect_sqlite

    stale = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as conn:
        conn.execute(
            "UPDATE tender_bid_docs SET updated_at = ? WHERE project_id = ? AND bid_id = ?",
            (stale, pid, bid_id),
        )


def test_heartbeat_covers_the_upload_semaphore_queue(monkeypatch):
    """F2：心跳必须早于上传信号量排队起跑——排队 400s 的真在途预热不得被判 stale。

    此前 ticker 在 `async with get_upload_ocr_semaphore()` **之内**才起，排队期间零心跳：
    前一个大标占着名额时，后一个标的 updated_at 一路变陈旧 → 评标侧 oracle 判 stale →
    另起 inline OCR → 双跑复活（本 sprint 要杀的病灶）。
    """
    from server.tender import doc_layer

    pid, bid_id = _pid(), store.new_bid_id()
    _seed_bid(pid, bid_id)
    _age_bid_row(pid, bid_id, 400)  # 模拟已排队 400s（> 默认 300s stale 阈值）
    monkeypatch.setattr(prewarm_scheduler, "PREWARM_TOUCH_INTERVAL_SEC", 0.01)
    touches: list[int] = []
    real_touch = store.touch_bid_doc_ocr

    def _counting_touch(*args, **kwargs):
        touches.append(1)
        real_touch(*args, **kwargs)

    monkeypatch.setattr(doc_pipeline, "touch_bid_doc_ocr", _counting_touch)
    ocr_started: list[int] = []
    _patch_report(monkeypatch, OcrDocReport("ready", (), ()))
    original_report = doc_pipeline.prewarm_and_report

    def _tracked_report(*args, **kwargs):
        ocr_started.append(1)
        return original_report(*args, **kwargs)

    monkeypatch.setattr(doc_pipeline, "prewarm_and_report", _tracked_report)

    async def _scenario() -> dict:
        # 把上传闸压到 1 个名额，用一次 acquire 就能复现"前一个大标占满、后来者排队"。
        monkeypatch.setattr(prewarm_scheduler, "_UPLOAD_OCR_SEMAPHORE", asyncio.Semaphore(1))
        async with prewarm_scheduler.get_upload_ocr_semaphore():  # 名额被别人占住
            task = asyncio.create_task(
                doc_pipeline.run_bid_doc_ocr(pid, bid_id, "/case/bid", tenant="t1")
            )
            await asyncio.sleep(0.08)
            assert ocr_started == [], "OCR 还没开始跑（仍在排队），这正是要覆盖的窗口"
            queued_row = store.get_bid_doc(pid, bid_id, "t1")
        await task
        return queued_row

    queued_row = asyncio.run(_scenario())

    assert len(touches) >= 2, "排队期间必须持续心跳（且首次立即执行）"
    assert doc_layer.is_prewarm_in_flight(queued_row, stale_sec=300) is True
    assert store.get_bid_doc(pid, bid_id, "t1")["ocr_status"] == "ready"


def test_prewarm_runs_on_the_named_ocr_executor(monkeypatch):
    """KD4 接线：预热 OCR 必须落在命名池线程上，不占 asyncio 默认池。"""
    pid, bid_id = _pid(), store.new_bid_id()
    _seed_bid(pid, bid_id)
    thread_names: list[str] = []

    def _record_thread(*_a, **_k):
        import threading

        thread_names.append(threading.current_thread().name)
        return "底稿正文", OcrDocReport("ready", (), ())

    monkeypatch.setattr(doc_pipeline, "prewarm_and_report", _record_thread)

    asyncio.run(doc_pipeline.run_bid_doc_ocr(pid, bid_id, "/case/bid", tenant="t1"))

    assert thread_names and all(name.startswith("ocr") for name in thread_names)
