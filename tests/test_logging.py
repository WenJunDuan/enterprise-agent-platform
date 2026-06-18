"""企业日志：级别分流 + 滚动 + gz 备份（log4j2 风格 file appenders）。

锁定 configure_logging 的文件落盘行为：app.log 收全量、error.log 只收 WARN+、
默认不写盘（测试安全）、超阈值滚动且备份 gz 压缩。
"""

from __future__ import annotations

import logging

import pytest

from server.platform.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def _restore_logging():
    """每个用例后把 root logging 复位成 stdout-only，避免文件 handler 泄漏到其他测试。"""
    yield
    configure_logging("INFO", "json")


def _flush_root() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


def test_no_files_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("LOG_TO_FILES", raising=False)
    configure_logging("INFO", "json", log_dir=tmp_path)  # to_files 默认取 env(未设)→ False
    logging.getLogger("test.nofile").info("should not hit disk")
    assert not (tmp_path / "app.log").exists()
    assert not (tmp_path / "error.log").exists()


def test_file_appenders_split_by_level(tmp_path):
    configure_logging("INFO", "json", to_files=True, log_dir=tmp_path)
    log = logging.getLogger("test.split")
    log.info("an-info-line")
    log.error("an-error-line")
    _flush_root()

    app_log = (tmp_path / "app.log").read_text(encoding="utf-8")
    error_log = (tmp_path / "error.log").read_text(encoding="utf-8")

    # app.log 收全量
    assert "an-info-line" in app_log
    assert "an-error-line" in app_log
    # error.log 只收 WARN+（log4j2 ThresholdFilter）
    assert "an-error-line" in error_log
    assert "an-info-line" not in error_log


def test_file_logs_are_json(tmp_path):
    import json

    configure_logging("INFO", "kv", to_files=True, log_dir=tmp_path)  # console 用 kv，文件仍 JSON
    logging.getLogger("test.json").warning("structured-payload")
    _flush_root()

    line = (tmp_path / "app.log").read_text(encoding="utf-8").strip().splitlines()[-1]
    parsed = json.loads(line)  # 文件始终 JSON，可解析
    assert parsed["level"] == "WARNING"
    assert parsed["message"] == "structured-payload"


def test_rotation_produces_gzip_backups(tmp_path):
    configure_logging("INFO", "json", to_files=True, log_dir=tmp_path, max_bytes=800, backup_count=3)
    log = logging.getLogger("test.rotate")
    for i in range(300):
        log.info("padding line %03d to exceed the tiny max_bytes rollover threshold", i)
    _flush_root()

    backups = sorted(tmp_path.glob("app.log.*.gz"))
    assert backups, "expected at least one gzipped rotated backup"
    # 备份数受 backup_count 约束
    assert len(backups) <= 3
