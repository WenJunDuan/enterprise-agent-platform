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


def test_orphan_cleanup_resolves_known_against_project_root(tmp_path, monkeypatch):
    # codex round 4 P2：known 用 PROJECT_ROOT（非 CWD）解析相对 case_path，
    # 否则从非项目目录跑 maintenance 会把活跃任务目录漏出 known、误删。
    monkeypatch.setattr("server.platform.maintenance.SUBMISSION_ROOT_DIR", tmp_path)
    monkeypatch.setattr("server.platform.maintenance.PROJECT_ROOT", tmp_path)
    active = tmp_path / "r1"
    active.mkdir()
    old = time.time() - 10 * 86400
    os.utime(active, (old, old))
    monkeypatch.setattr(
        "server.platform.maintenance.list_audit_tasks_admin",
        lambda: [{"case_path": "r1", "source_mode": "upload", "status": "running"}],
    )
    workdir = tmp_path / "elsewhere"
    workdir.mkdir()
    monkeypatch.chdir(workdir)  # CWD ≠ PROJECT_ROOT

    removed = cleanup_orphan_submission_directories(days=7)
    assert str(active.resolve()) not in removed  # 活跃任务目录（known 命中）不被误删
    assert active.exists()
