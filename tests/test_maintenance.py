"""maintenance: 孤儿 submission 目录清理。

OCR 端点（/ocr/extract、/ocr/fill）的上传目录不登记为 audit task，超时 / 崩溃残留
需按 mtime 兜底清理；这里锁定「过期孤儿删、retention 内保留」。
"""

from __future__ import annotations

import os
import time

from server.platform.maintenance import cleanup_orphan_submission_directories


def test_orphan_submission_dir_removed_when_old(tmp_path, monkeypatch):
    monkeypatch.setattr("server.platform.maintenance.SUBMISSION_ROOT_DIR", tmp_path)
    orphan = tmp_path / "ocr-orphan"
    orphan.mkdir()
    (orphan / "f.txt").write_text("x", encoding="utf-8")
    old = time.time() - 10 * 86400  # 10 天前
    os.utime(orphan, (old, old))

    removed = cleanup_orphan_submission_directories(days=7)
    assert str(orphan.resolve()) in removed
    assert not orphan.exists()


def test_recent_orphan_dir_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr("server.platform.maintenance.SUBMISSION_ROOT_DIR", tmp_path)
    orphan = tmp_path / "ocr-recent"
    orphan.mkdir()

    removed = cleanup_orphan_submission_directories(days=7)  # 刚建，retention 内 → 保留
    assert str(orphan.resolve()) not in removed
    assert orphan.exists()
