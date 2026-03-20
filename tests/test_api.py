import logging
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from server.api import app
from server.core import MemoryWriteError
from server.model_client import ModelSettings, UpstreamError


def test_health_reports_loaded_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "server.api.load_settings",
        lambda: ModelSettings(base_url="http://127.0.0.1:1234", model="demo-model", api_key=None),
    )

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "base_url": "http://127.0.0.1:1234",
        "model": "demo-model",
        "api_key_configured": False,
    }
    assert response.headers["X-Request-ID"]


def test_chat_returns_model_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "server.api.load_settings",
        lambda: ModelSettings(base_url="http://127.0.0.1:1234", model="demo-model", api_key=None),
    )
    monkeypatch.setattr(
        "server.api.run_chat",
        lambda message, source, request_id, settings=None: SimpleNamespace(output_text=f"reply:{message}"),
    )

    client = TestClient(app)
    response = client.post("/chat", json={"message": "hello"})

    assert response.status_code == 200
    assert response.json() == {"model": "demo-model", "response": "reply:hello"}


def test_chat_surfaces_upstream_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "server.api.load_settings",
        lambda: ModelSettings(base_url="http://127.0.0.1:1234", model="demo-model", api_key=None),
    )

    def raise_upstream(message, source, request_id, settings=None):
        raise UpstreamError("upstream unavailable")

    monkeypatch.setattr("server.api.run_chat", raise_upstream)

    client = TestClient(app)
    response = client.post("/chat", json={"message": "hello"})

    assert response.status_code == 502
    assert response.json() == {"detail": "upstream unavailable"}


def test_chat_surfaces_memory_write_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "server.api.load_settings",
        lambda: ModelSettings(base_url="http://127.0.0.1:1234", model="demo-model", api_key=None),
    )

    def raise_memory_write_error(message, source, request_id, settings=None):
        raise MemoryWriteError("business memory append failed: disk full")

    monkeypatch.setattr("server.api.run_chat", raise_memory_write_error)

    client = TestClient(app)
    response = client.post("/chat", json={"message": "hello"})

    assert response.status_code == 500
    assert response.json() == {"detail": "business memory append failed: disk full"}


def test_init_is_not_exposed_via_http() -> None:
    client = TestClient(app)
    response = client.post("/init")

    assert response.status_code == 404


def test_startup_logs_warning_when_upstream_api_key_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        "server.api.load_settings",
        lambda: ModelSettings(base_url="http://127.0.0.1:1234", model="demo-model", api_key=None),
    )
    monkeypatch.setenv("APP_LOG_FILE", str(tmp_path / "service.log"))
    monkeypatch.setenv("APP_LOG_LEVEL", "DEBUG")
    caplog.set_level(logging.WARNING, logger="enterprise_agent")

    with TestClient(app):
        pass

    assert any(
        record.levelname == "WARNING" and "upstream api key not configured" in record.message
        for record in caplog.records
    )
