"""评标必须等 criteria 抽取到终态再取底稿（2026-08-17 实测时序缺陷）。

事故：评标 01:40:18 取底稿时招标层 criteria 尚未落库，01:40:54 才抽完（晚 36 秒）。
`wait_doc_layer_ready` 只等两层 OCR 到终态、不看 criteria，于是 `build_evidence_context`
走"无 criteria → 交回既有路径"分支——证据层（S3 主体）整个没启用，784KB 底稿退回
全量注入 + 截断，用户看到的是被截断的评标。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from server.tender.doc_layer import _criteria_pending

STALE_SEC = 120.0


def _doc(status: str, *, age_sec: float = 1.0) -> dict:
    stamp = (datetime.now(UTC) - timedelta(seconds=age_sec)).isoformat()
    return {"criteria_status": status, "updated_at": stamp}


def test_running_extraction_is_worth_waiting_for():
    """抽取在跑且心跳新鲜 → 该等，否则证据层拿不到 criteria。"""
    assert _criteria_pending(_doc("running"), STALE_SEC) is True
    assert _criteria_pending(_doc("pending"), STALE_SEC) is True


def test_terminal_status_releases_immediately():
    """ready/failed 都是终态——failed 也不该再等（等下去不会变好）。"""
    assert _criteria_pending(_doc("ready"), STALE_SEC) is False
    assert _criteria_pending(_doc("failed"), STALE_SEC) is False


def test_stale_running_is_not_worth_waiting_for():
    """进程重启遗留的僵尸 running：心跳陈旧 → 按"不会有了"处理，别白等到上限。"""
    assert _criteria_pending(_doc("running", age_sec=STALE_SEC * 3), STALE_SEC) is False


def test_missing_or_malformed_rows_never_block():
    """缺行/坏时间戳一律放行——等待是优化，不能变成新的卡死点。"""
    assert _criteria_pending(None, STALE_SEC) is False
    assert _criteria_pending({"criteria_status": "running"}, STALE_SEC) is False
    assert _criteria_pending({"criteria_status": "running", "updated_at": "坏值"}, STALE_SEC) is False
