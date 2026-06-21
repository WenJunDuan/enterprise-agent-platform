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


def _day_dir(base):
    """日志按日期目录分区：<base>/<YYYYMMDD>/（便于按日滚动删除）。"""
    from datetime import datetime

    return base / datetime.now().strftime("%Y%m%d")


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

    app_log = (_day_dir(tmp_path) / "app.log").read_text(encoding="utf-8")
    error_log = (_day_dir(tmp_path) / "error.log").read_text(encoding="utf-8")

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

    line = (_day_dir(tmp_path) / "app.log").read_text(encoding="utf-8").strip().splitlines()[-1]
    parsed = json.loads(line)  # 文件始终 JSON，可解析
    assert parsed["level"] == "WARNING"
    assert parsed["message"] == "structured-payload"


def test_rotation_produces_gzip_backups(tmp_path):
    configure_logging("INFO", "json", to_files=True, log_dir=tmp_path, max_bytes=800, backup_count=3)
    log = logging.getLogger("test.rotate")
    for i in range(300):
        log.info("padding line %03d to exceed the tiny max_bytes rollover threshold", i)
    _flush_root()

    backups = sorted(_day_dir(tmp_path).glob("app.log.*.gz"))
    assert backups, "expected at least one gzipped rotated backup"
    # 备份数受 backup_count 约束
    assert len(backups) <= 3


# ── uvicorn access log 噪音过滤（/health 健康探测刷屏）──────────────────────────


def _access_record(line: str) -> logging.LogRecord:
    return logging.LogRecord("uvicorn.access", logging.INFO, "", 0, line, None, None)


def test_access_noise_filter_exact_path_and_status():
    from server.platform.logging_setup import _AccessNoiseFilter

    f = _AccessNoiseFilter(("/health",))
    # /health 成功响应 → 过滤（噪音）
    assert f.filter(_access_record('127.0.0.1 - "GET /health HTTP/1.1" 200')) is False
    # 业务请求 → 保留
    assert f.filter(_access_record('127.0.0.1 - "POST /tender/projects HTTP/1.1" 200')) is True
    # /health 的 5xx → 保留（健康检查失败要能看到，codex r4 P1）
    assert f.filter(_access_record('127.0.0.1 - "GET /health HTTP/1.1" 503')) is True
    # query 串里含 /health 但 exact path 不是 → 不误伤
    assert f.filter(_access_record('1.1.1.1 - "GET /x?to=/health HTTP/1.1" 200')) is True


def test_install_access_log_filter_reads_env(monkeypatch):
    from server.platform.logging_setup import _AccessNoiseFilter, install_access_log_filter

    monkeypatch.setenv("ACCESS_LOG_NOISE_PATHS", "/health,/tender/tasks")
    acc = logging.getLogger("uvicorn.access")
    acc.filters = [flt for flt in acc.filters if not isinstance(flt, _AccessNoiseFilter)]
    try:
        install_access_log_filter()
        installed = [flt for flt in acc.filters if isinstance(flt, _AccessNoiseFilter)]
        assert installed, "应给 uvicorn.access 装一个噪音 filter"
        # 两个 env 路径都过滤
        assert installed[0].filter(_access_record('- "GET /tender/tasks/x HTTP/1.1" 200')) is False
    finally:
        acc.filters = [flt for flt in acc.filters if not isinstance(flt, _AccessNoiseFilter)]
