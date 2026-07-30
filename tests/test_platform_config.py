"""D11/R6 configuration guardrails and startup deployment hints."""

from __future__ import annotations

import logging

import pytest

from server.platform.config import (
    get_app_settings,
    validate_tender_ocr_timeout_budget,
)


@pytest.fixture(autouse=True)
def _clear_app_settings_cache():
    get_app_settings.cache_clear()
    yield
    get_app_settings.cache_clear()


def test_warns_when_ocr_cloud_wait_exceeds_half_tender_timeout(monkeypatch, caplog):
    monkeypatch.setenv("TENDER_TIMEOUT_SEC", "100")
    monkeypatch.setenv("OCR_VL_CLOUD_MAX_WAIT", "51")
    caplog.set_level(logging.WARNING)

    validate_tender_ocr_timeout_budget()

    assert any("OCR_VL_CLOUD_MAX_WAIT" in record.getMessage() for record in caplog.records)


def test_does_not_warn_at_half_tender_timeout(monkeypatch, caplog):
    monkeypatch.setenv("TENDER_TIMEOUT_SEC", "100")
    monkeypatch.setenv("OCR_VL_CLOUD_MAX_WAIT", "50")
    caplog.set_level(logging.WARNING)

    validate_tender_ocr_timeout_budget()

    assert not caplog.records


def test_app_settings_logs_cache_v2_first_rerun_hint(monkeypatch, caplog):
    monkeypatch.setenv("TENDER_TIMEOUT_SEC", "100")
    monkeypatch.setenv("OCR_VL_CLOUD_MAX_WAIT", "50")
    caplog.set_level(logging.INFO)

    get_app_settings()

    messages = [record.getMessage() for record in caplog.records]
    assert any("OCR cache v4" in message and "first rerun" in message for message in messages)
