"""R5：tender worker 超时 graceful-fail 回归（F5 用户侧 UX）。

锁定：评标超时（asyncio.wait_for 触发 TimeoutError）→ worker 不抛/不崩，置 status=failed
+ error_detail（含"超时"）+ progress="评标超时"。SDK 侧子进程终止见 client.py:73-87 / subprocess_cli.py
disconnect terminate/kill（本测试覆盖 worker 状态机侧）。
"""

from __future__ import annotations

import asyncio

import server.routes.tender_worker as tw


def test_tender_timeout_sets_failed_status(monkeypatch):
    captured: list[dict] = []
    monkeypatch.setattr(tw, "upsert_tender_task", lambda payload: captured.append(payload))
    monkeypatch.setattr(tw, "update_tender_progress", lambda *a, **k: None)
    monkeypatch.setattr(tw, "TENDER_TIMEOUT_SEC", 0.05)

    async def _hang(**kwargs):  # 模拟评标挂起，超过超时
        await asyncio.sleep(5)

    monkeypatch.setattr(tw, "_run_evaluation", _hang)

    asyncio.run(
        tw._execute_inner(
            request_id="r-timeout",
            tenant="default",
            directory_path="/tmp/nonexistent-case",
            source_mode="directory",
        )
    )

    statuses = [c.get("status") for c in captured]
    assert "running" in statuses  # 起始置 running
    assert statuses[-1] == "failed"  # 终态 failed（不崩、不抛）
    failed = next(c for c in captured if c.get("status") == "failed")
    assert "超时" in (failed.get("error_detail") or "")
    assert failed.get("progress_message") == "评标超时"


def test_tender_generic_failure_sets_failed_status(monkeypatch):
    # 非超时异常也 graceful → failed + error_detail（对账 except 分支）
    captured: list[dict] = []
    monkeypatch.setattr(tw, "upsert_tender_task", lambda payload: captured.append(payload))
    monkeypatch.setattr(tw, "update_tender_progress", lambda *a, **k: None)
    monkeypatch.setattr(tw, "TENDER_TIMEOUT_SEC", 30)

    async def _boom(**kwargs):
        raise RuntimeError("模型网关 500")

    monkeypatch.setattr(tw, "_run_evaluation", _boom)

    asyncio.run(
        tw._execute_inner(
            request_id="r-fail",
            tenant="default",
            directory_path="/tmp/x",
            source_mode="directory",
        )
    )
    failed = next(c for c in captured if c.get("status") == "failed")
    assert "模型网关 500" in (failed.get("error_detail") or "")
