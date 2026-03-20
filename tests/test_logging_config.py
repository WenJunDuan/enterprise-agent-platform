import logging

import pytest

from server.logging_config import configure_logging, get_logger


def test_configure_logging_writes_debug_logs_to_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    log_file = tmp_path / "service.log"
    monkeypatch.setenv("APP_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("APP_LOG_FILE", str(log_file))

    settings = configure_logging(force=True)
    logger = get_logger("tests")
    logger.debug("debug log smoke test")

    for handler in logging.getLogger("enterprise_agent").handlers:
        handler.flush()

    content = log_file.read_text(encoding="utf-8")
    assert settings.level_name == "DEBUG"
    assert "DEBUG" in content
    assert "debug log smoke test" in content
