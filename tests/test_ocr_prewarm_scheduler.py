"""S3: OCR 预热编排基建（server.ocr.prewarm_scheduler）+ 错误标记校验（pipeline.is_ocr_text_valid）。

这些通用 OCR 能力从 routes/tender.py 下沉到 ocr feature 层（用户要求：合并进 server/ocr/，
不在调用层重复定义）。本测试锁定其行为与归属。
"""

from __future__ import annotations

import asyncio

import pytest

from server.ocr.pipeline import OCR_ERROR_PREFIX, is_ocr_text_valid
from server.ocr.prewarm_scheduler import (
    cancel_project_ocr_tasks,
    get_upload_ocr_semaphore,
    track_upload_ocr_task,
)


def test_is_ocr_text_valid_true_for_real_text():
    assert is_ocr_text_valid("第 1 页\n评分标准…") is True


def test_is_ocr_text_valid_false_for_empty_or_blank():
    assert is_ocr_text_valid("") is False
    assert is_ocr_text_valid("   \n\t ") is False


def test_is_ocr_text_valid_false_for_error_marker():
    assert is_ocr_text_valid(f"{OCR_ERROR_PREFIX} OCR engine down") is False


def test_get_upload_ocr_semaphore_is_singleton():
    assert get_upload_ocr_semaphore() is get_upload_ocr_semaphore()


def test_cancel_project_ocr_tasks_noop_when_no_tasks():
    assert cancel_project_ocr_tasks("tp-none-s3") == 0


def test_track_then_cancel_flow():
    async def _run() -> None:
        started = asyncio.Event()

        async def _long() -> None:
            started.set()
            await asyncio.sleep(60)

        task = asyncio.create_task(_long())
        track_upload_ocr_task(task, "tp-s3")
        await started.wait()

        assert cancel_project_ocr_tasks("tp-s3") == 1
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0)  # 让 done 回调跑完（桶自清）
        assert cancel_project_ocr_tasks("tp-s3") == 0  # 已清空

    asyncio.run(_run())
