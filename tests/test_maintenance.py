"""maintenance: 孤儿 submission 目录清理。

OCR 端点（/ocr/extract、/ocr/fill）的上传目录不登记为 audit task，超时 / 崩溃残留
需按 mtime 兜底清理；这里锁定「过期孤儿删、retention 内保留」。
"""

from __future__ import annotations

import os
import time

from server.ops.maintenance import (
    cleanup_old_submission_directories,
    cleanup_orphan_submission_directories,
)


def _no_tasks(monkeypatch):
    """两域 task 列表置空，孤儿清理不受真实 DB 任务影响（隔离）。"""
    monkeypatch.setattr("server.ops.maintenance.list_audit_tasks_admin", list)
    monkeypatch.setattr("server.ops.maintenance.list_tender_tasks_admin", list)


def test_orphan_submission_dir_removed_when_old(tmp_path, monkeypatch):
    monkeypatch.setattr("server.ops.maintenance.SUBMISSION_ROOT_DIR", tmp_path)
    _no_tasks(monkeypatch)
    # 新结构：孤儿叶子 case 目录 <tenant>/<domain>/<rid>（glob *//ocr/* 才扫得到）。
    orphan = tmp_path / "acme" / "ocr" / "orphan-rid"
    orphan.mkdir(parents=True)
    (orphan / "f.txt").write_text("x", encoding="utf-8")
    old = time.time() - 10 * 86400  # 10 天前
    os.utime(orphan, (old, old))

    removed = cleanup_orphan_submission_directories(days=7)
    assert str(orphan.resolve()) in removed
    assert not orphan.exists()


def test_recent_orphan_dir_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr("server.ops.maintenance.SUBMISSION_ROOT_DIR", tmp_path)
    _no_tasks(monkeypatch)
    orphan = tmp_path / "acme" / "ocr" / "recent-rid"
    orphan.mkdir(parents=True)

    removed = cleanup_orphan_submission_directories(days=7)  # 刚建，retention 内 → 保留
    assert str(orphan.resolve()) not in removed
    assert orphan.exists()


def test_orphan_cleanup_resolves_known_against_project_root(tmp_path, monkeypatch):
    # codex round 4 P2：known 用 PROJECT_ROOT（非 CWD）解析相对 case_path，
    # 否则从非项目目录跑 maintenance 会把活跃任务目录漏出 known、误删。
    monkeypatch.setattr("server.ops.maintenance.SUBMISSION_ROOT_DIR", tmp_path)
    monkeypatch.setattr("server.ops.maintenance.PROJECT_ROOT", tmp_path)
    active = tmp_path / "acme" / "audit" / "r1"  # 新叶子结构
    active.mkdir(parents=True)
    old = time.time() - 10 * 86400
    os.utime(active, (old, old))
    monkeypatch.setattr(
        "server.ops.maintenance.list_audit_tasks_admin",
        lambda: [{"case_path": "acme/audit/r1", "source_mode": "upload", "status": "running"}],
    )
    monkeypatch.setattr("server.ops.maintenance.list_tender_tasks_admin", list)
    workdir = tmp_path / "elsewhere"
    workdir.mkdir()
    monkeypatch.chdir(workdir)  # CWD ≠ PROJECT_ROOT

    removed = cleanup_orphan_submission_directories(days=7)
    assert str(active.resolve()) not in removed  # 活跃任务目录（known 命中）不被误删
    assert active.exists()


def test_orphan_cleanup_does_not_follow_symlink_escape(tmp_path, monkeypatch):
    """codex P1：symlink 叶子 case 目录不被跟随删除（绝不删 submissions 根外目标）。"""
    monkeypatch.setattr("server.ops.maintenance.SUBMISSION_ROOT_DIR", tmp_path)
    _no_tasks(monkeypatch)
    # 外部目标（submissions 根外），不应被删。
    external = tmp_path.parent / "external-secret-dir"
    external.mkdir(parents=True, exist_ok=True)
    (external / "keep.txt").write_text("KEEP", encoding="utf-8")
    # symlink 叶子伪装成 ocr case 目录，指向外部。
    domain_dir = tmp_path / "acme" / "ocr"
    domain_dir.mkdir(parents=True)
    link = domain_dir / "evil-rid"
    link.symlink_to(external, target_is_directory=True)
    old = time.time() - 10 * 86400
    os.utime(external, (old, old))

    removed = cleanup_orphan_submission_directories(days=7)
    assert str(external.resolve()) not in removed  # 外部目标未被删
    assert external.exists() and (external / "keep.txt").exists()  # 外部数据完好


def test_cleanup_old_handles_tender_and_compare_tasks(tmp_path, monkeypatch):
    """codex P2：cleanup_old 纳入 tender 任务；compare 任务 case_path='-' 安全跳过。"""
    monkeypatch.setattr("server.ops.maintenance.SUBMISSION_ROOT_DIR", tmp_path)
    monkeypatch.setattr("server.ops.maintenance.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("server.ops.maintenance.list_audit_tasks_admin", list)
    tender_case = tmp_path / "acme" / "tender" / "tp-x" / "rid"
    tender_case.mkdir(parents=True)
    monkeypatch.setattr(
        "server.ops.maintenance.list_tender_tasks_admin",
        lambda: [
            {"case_path": "acme/tender/tp-x/rid", "source_mode": "upload",
             "status": "completed", "finished_at": "2026-06-01T00:00:00+00:00"},
            # compare 任务占位 "-"，不建目录 → 必须安全跳过，不报错。
            {"case_path": "-", "source_mode": "compare", "status": "completed",
             "finished_at": "2026-06-01T00:00:00+00:00"},
        ],
    )
    removed = cleanup_old_submission_directories(days=7, now="2026-06-20T00:00:00+00:00")
    assert str(tender_case.resolve()) in removed  # tender upload 过期目录被清
    assert not tender_case.exists()
