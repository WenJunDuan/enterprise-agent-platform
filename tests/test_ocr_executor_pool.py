"""H3 KD4：OCR 走命名线程池，分钟级阻塞不再污染 asyncio 默认 to_thread 池。

实测病灶：预热/inline OCR 都经 ``asyncio.to_thread``，4 核机默认池 ≈8 线程被分钟级 OCR 占满后，
**连状态写库都排队**（状态更新被 OCR 饿死）。修法是把 OCR 这类分钟级阻塞调用移到命名池，
DB 读写等毫秒级短调用留在默认池。
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

from server.ocr import prewarm_scheduler
from server.platform.config import get_ocr_concurrency_settings

_SLOW_SEC = 0.3
_STARVATION_THRESHOLD_SEC = 0.15


def _slow_ocr_call() -> str:
    time.sleep(_SLOW_SEC)
    return "ocr-done"


def _short_db_call() -> str:
    return "db-written"


async def _latency_of_short_db_call() -> float:
    started = time.monotonic()
    await asyncio.to_thread(_short_db_call)
    return time.monotonic() - started


def _run_with_tiny_default_pool(scenario) -> float:
    """在"默认池只有 2 个线程"的收缩环境里跑场景，返回短 DB 调用的延迟。

    收缩默认池是为了在毫秒级测试里复现 4 核机上"默认池被 OCR 占满"的真实形态，
    而不是靠真实 sleep 长等把 32 线程池填满（测试墙钟不可接受）。
    """

    async def _main() -> float:
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="tiny-default") as pool:
            loop.set_default_executor(pool)
            return await scenario(loop)

    return asyncio.run(_main())


async def _ocr_on_default_pool(_loop) -> float:
    """对照组：OCR 走 asyncio.to_thread（默认池）——两路在途即把池占满。"""
    ocr_tasks = [asyncio.create_task(asyncio.to_thread(_slow_ocr_call)) for _ in range(2)]
    await asyncio.sleep(0.05)  # 让两路 OCR 先占住线程
    latency = await _latency_of_short_db_call()
    await asyncio.gather(*ocr_tasks)
    return latency


async def _ocr_on_named_pool(_loop) -> float:
    """实验组：OCR 走命名池——默认池仍空闲，状态写库不排队。"""
    ocr_tasks = [
        asyncio.create_task(prewarm_scheduler.run_in_ocr_executor(_slow_ocr_call))
        for _ in range(2)
    ]
    await asyncio.sleep(0.05)
    latency = await _latency_of_short_db_call()
    await asyncio.gather(*ocr_tasks)
    return latency


def test_named_pool_keeps_db_writes_off_the_ocr_queue():
    """AC5 对照测试：默认池路径下短调用被 OCR 饿死，命名池路径下不受影响。"""
    default_pool_latency = _run_with_tiny_default_pool(_ocr_on_default_pool)
    named_pool_latency = _run_with_tiny_default_pool(_ocr_on_named_pool)

    assert default_pool_latency > _STARVATION_THRESHOLD_SEC, (
        "对照组未复现默认池饿死现象，测试失去意义"
    )
    assert named_pool_latency < _STARVATION_THRESHOLD_SEC
    assert named_pool_latency < default_pool_latency / 2


def test_ocr_executor_is_a_named_bounded_pool():
    """命名池可辨识（线程名前缀 ocr）且规模由 OCR_EXECUTOR_WORKERS 决定。"""
    executor = prewarm_scheduler.get_ocr_executor()

    assert executor is prewarm_scheduler.get_ocr_executor()  # 进程级单例，不每次新建
    assert executor._thread_name_prefix.startswith("ocr")
    assert executor._max_workers == get_ocr_concurrency_settings().executor_workers


def test_run_in_ocr_executor_forwards_args_and_kwargs():
    async def _main():
        return await prewarm_scheduler.run_in_ocr_executor(
            lambda case_dir, *, purpose: f"{case_dir}|{purpose}", "/case", purpose="tender"
        )

    assert asyncio.run(_main()) == "/case|tender"


def test_ocr_concurrency_settings_defaults(monkeypatch):
    monkeypatch.delenv("OCR_EXECUTOR_WORKERS", raising=False)
    monkeypatch.delenv("OCR_PREWARM_STALE_SEC", raising=False)
    monkeypatch.setenv("TENDER_TIMEOUT_SEC", "3600")

    settings = get_ocr_concurrency_settings()

    assert settings.executor_workers == 4
    assert settings.prewarm_stale_sec == 300.0
    # 等待上限从 tender 总预算派生（替代拍脑袋 360s）。
    assert settings.doc_layer_wait_cap_sec == 1800.0


def test_ocr_concurrency_settings_read_env_live(monkeypatch):
    monkeypatch.setenv("OCR_EXECUTOR_WORKERS", "7")
    monkeypatch.setenv("OCR_PREWARM_STALE_SEC", "120")
    monkeypatch.setenv("TENDER_TIMEOUT_SEC", "600")

    settings = get_ocr_concurrency_settings()

    assert settings.executor_workers == 7
    assert settings.prewarm_stale_sec == 120.0
    assert settings.doc_layer_wait_cap_sec == 300.0


def test_ocr_concurrency_settings_reject_nonsense_values(monkeypatch):
    monkeypatch.setenv("OCR_EXECUTOR_WORKERS", "not-a-number")
    monkeypatch.setenv("OCR_PREWARM_STALE_SEC", "-5")

    settings = get_ocr_concurrency_settings()

    assert settings.executor_workers == 4
    assert settings.prewarm_stale_sec == 300.0
