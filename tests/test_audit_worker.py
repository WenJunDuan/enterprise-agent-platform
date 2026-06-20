"""audit_worker：round4 F5 任务生命周期——引用追踪防 GC + 准入上限。

不触发真实 claude CLI / 模型（无网络）；只锁定引用集与准入闸的纯行为。
"""

from __future__ import annotations

import asyncio

from server.routes import audit_worker as worker


def test_admission_available_true_when_under_cap(monkeypatch):
    monkeypatch.setattr(worker, "_BACKGROUND_TASKS", set())
    monkeypatch.setattr(worker, "MAX_PENDING_AUDITS", 2)
    assert worker.admission_available() is True


def test_admission_blocks_at_cap(monkeypatch):
    monkeypatch.setattr(worker, "_BACKGROUND_TASKS", {object(), object()})
    monkeypatch.setattr(worker, "MAX_PENDING_AUDITS", 2)
    assert worker.admission_available() is False  # 在途已达上限 → 路由回 503


def test_track_task_keeps_ref_then_autoremoves(monkeypatch):
    """round4 F5：fire-and-forget 任务须被强引用住（防 GC），完成后自动清出集合。"""
    fresh: set = set()
    monkeypatch.setattr(worker, "_BACKGROUND_TASKS", fresh)

    async def _scenario() -> asyncio.Task:
        async def _noop() -> None:
            return None

        task = asyncio.create_task(_noop())
        worker._track_task(task)
        assert task in fresh  # 运行中被引用住
        await task
        await asyncio.sleep(0)  # 让 done_callback 跑完
        return task

    finished = asyncio.run(_scenario())
    assert finished not in fresh  # 完成后自清，不泄漏


def test_track_task_counts_toward_admission(monkeypatch):
    """在途任务计入准入闸：追踪一个未完成任务后，到上限即拒新单。"""
    fresh: set = set()
    monkeypatch.setattr(worker, "_BACKGROUND_TASKS", fresh)
    monkeypatch.setattr(worker, "MAX_PENDING_AUDITS", 1)

    async def _scenario() -> None:
        gate = asyncio.Event()

        async def _blocked() -> None:
            await gate.wait()

        task = asyncio.create_task(_blocked())
        worker._track_task(task)
        assert worker.admission_available() is False  # 1 个在途 == 上限 → 拒
        gate.set()
        await task
        await asyncio.sleep(0)
        assert worker.admission_available() is True  # 完成清出 → 又可接单

    asyncio.run(_scenario())
