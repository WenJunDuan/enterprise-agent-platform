"""Application logging helpers."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from server.config import LoggingSettings, load_logging_settings


LOGGER_NAME = "enterprise_agent"
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(*, force: bool = False) -> LoggingSettings:
    settings = load_logging_settings()
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(settings.level)
    logger.propagate = True

    if force:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=settings.level, format=LOG_FORMAT)
    else:
        root_logger.setLevel(settings.level)

    settings.log_file.parent.mkdir(parents=True, exist_ok=True)
    log_path = settings.log_file.resolve()

    for handler in logger.handlers:
        if getattr(handler, "_enterprise_agent_file", False):
            handler.setLevel(settings.level)
            if Path(handler.baseFilename).resolve() == log_path:
                return settings

    file_handler = RotatingFileHandler(
        settings.log_file,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(settings.level)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    file_handler._enterprise_agent_file = True  # type: ignore[attr-defined]
    logger.addHandler(file_handler)
    return settings


def get_logger(name: str | None = None) -> logging.Logger:
    if not name:
        return logging.getLogger(LOGGER_NAME)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
