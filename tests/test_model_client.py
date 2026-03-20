import json
import logging

import httpx
import pytest

from server.model_client import ModelSettings, UpstreamError, build_chat_request, chat_once, extract_text, load_settings


def test_load_settings_prefers_generic_env_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_MODEL", raising=False)
    monkeypatch.setenv("MODEL_BASE_URL", "http://127.0.0.1:1234/")
    monkeypatch.setenv("MODEL_NAME", "demo-model")
    monkeypatch.setenv("MODEL_API_KEY", "")

    settings = load_settings()

    assert settings.base_url == "http://127.0.0.1:1234"
    assert settings.model == "demo-model"
    assert settings.api_key is None


def test_load_settings_supports_legacy_env_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:1234/")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("AGENT_MODEL", "legacy-model")

    settings = load_settings()

    assert settings.base_url == "http://127.0.0.1:1234"
    assert settings.model == "legacy-model"
    assert settings.api_key is None


def test_load_settings_requires_model_name_from_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.chdir(tmp_path)
    for key in [
        "MODEL_BASE_URL",
        "MODEL_NAME",
        "MODEL_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_API_KEY",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_API_KEY",
        "AGENT_MODEL",
    ]:
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValueError, match="MODEL_NAME"):
        load_settings()


def test_build_chat_request_omits_auth_header_without_api_key() -> None:
    request = build_chat_request(
        "ping",
        ModelSettings(base_url="http://127.0.0.1:1234", model="demo-model", api_key=None),
    )

    assert str(request.url) == "http://127.0.0.1:1234/v1/chat/completions"
    assert request.headers.get("Authorization") is None

    payload = json.loads(request.content.decode("utf-8"))
    assert payload == {
        "model": "demo-model",
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
    }


def test_extract_text_supports_string_and_content_blocks() -> None:
    assert extract_text({"choices": [{"message": {"content": "pong"}}]}) == "pong"
    assert extract_text(
        {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "hello"},
                            {"type": "text", "text": "world"},
                        ]
                    }
                }
            ]
        }
    ) == "hello\nworld"


def test_chat_once_calls_openai_compatible_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "pong"}}]}

    class FakeClient:
        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def send(self, request: httpx.Request) -> FakeResponse:
            assert str(request.url) == "http://127.0.0.1:1234/v1/chat/completions"
            return FakeResponse()

    monkeypatch.setattr("server.model_client._build_http_client", lambda settings: FakeClient())

    result = chat_once(
        "ping",
        ModelSettings(base_url="http://127.0.0.1:1234", model="demo-model", api_key=None),
    )

    assert result == "pong"


def test_chat_once_logs_debug_and_info_for_fast_success(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "pong"}}]}

    class FakeClient:
        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def send(self, request: httpx.Request) -> FakeResponse:
            return FakeResponse()

    timings = iter([10.0, 10.5])

    monkeypatch.setattr("server.model_client._build_http_client", lambda settings: FakeClient())
    monkeypatch.setattr("server.model_client.perf_counter", lambda: next(timings))
    caplog.set_level(logging.DEBUG, logger="enterprise_agent")

    result = chat_once(
        "ping",
        ModelSettings(base_url="http://127.0.0.1:1234", model="demo-model", api_key=None),
        request_id="req-fast",
    )

    assert result == "pong"
    assert any(
        record.levelname == "DEBUG" and "sending upstream request" in record.message
        for record in caplog.records
    )
    assert any(
        record.levelname == "INFO" and "upstream request finished" in record.message
        for record in caplog.records
    )


def test_chat_once_logs_warning_for_slow_success(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "pong"}}]}

    class FakeClient:
        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def send(self, request: httpx.Request) -> FakeResponse:
            return FakeResponse()

    timings = iter([10.0, 25.0])

    monkeypatch.setattr("server.model_client._build_http_client", lambda settings: FakeClient())
    monkeypatch.setattr("server.model_client.perf_counter", lambda: next(timings))
    caplog.set_level(logging.WARNING, logger="enterprise_agent")

    result = chat_once(
        "ping",
        ModelSettings(base_url="http://127.0.0.1:1234", model="demo-model", api_key=None),
        request_id="req-slow",
    )

    assert result == "pong"
    assert any(
        record.levelname == "WARNING" and "slow upstream response" in record.message
        for record in caplog.records
    )


def test_chat_once_wraps_upstream_failures(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class FakeClient:
        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def send(self, request: httpx.Request):
            raise RuntimeError("boom")

    monkeypatch.setattr("server.model_client._build_http_client", lambda settings: FakeClient())
    caplog.set_level(logging.ERROR, logger="enterprise_agent")

    with pytest.raises(UpstreamError, match="boom"):
        chat_once(
            "ping",
            ModelSettings(base_url="http://127.0.0.1:1234", model="demo-model", api_key=None),
            request_id="req-error",
        )

    assert any(
        record.levelname == "ERROR" and "upstream request failed" in record.message
        for record in caplog.records
    )


def test_build_ssl_context_uses_certifi_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_default_context(*, cafile=None, capath=None, cadata=None):
        captured["cafile"] = cafile
        return "ssl-context"

    monkeypatch.setattr("server.model_client.certifi.where", lambda: "/tmp/certifi.pem")
    monkeypatch.setattr("server.model_client.ssl.create_default_context", fake_create_default_context)

    context = __import__("server.model_client", fromlist=["_build_ssl_context"])._build_ssl_context()

    assert context == "ssl-context"
    assert captured["cafile"] == "/tmp/certifi.pem"
