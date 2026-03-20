import os
from pathlib import Path

import pytest

from server.config import load_memory_settings, load_model_settings


def test_load_model_settings_reads_from_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MODEL_BASE_URL=http://127.0.0.1:1234",
                "MODEL_NAME=demo-model",
                "UPSTREAM_TIMEOUT_SECONDS=45",
                "SLOW_REQUEST_THRESHOLD_SECONDS=12",
                "APP_MEMORY_ROOT=knowledge/runtime-memory",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

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
        "UPSTREAM_TIMEOUT_SECONDS",
        "SLOW_REQUEST_THRESHOLD_SECONDS",
        "APP_MEMORY_ROOT",
    ]:
        monkeypatch.delenv(key, raising=False)

    model_settings = load_model_settings()
    memory_settings = load_memory_settings()

    assert model_settings.base_url == "http://127.0.0.1:1234"
    assert model_settings.model == "demo-model"
    assert model_settings.timeout_seconds == 45.0
    assert model_settings.slow_request_threshold_seconds == 12.0
    assert memory_settings.root_dir == Path("knowledge/runtime-memory")


def test_process_env_overrides_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "MODEL_BASE_URL=http://127.0.0.1:1234\nMODEL_NAME=file-model\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODEL_NAME", "process-model")

    settings = load_model_settings()

    assert settings.model == "process-model"


def test_load_settings_does_not_leak_env_file_values_into_process_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APP_MEMORY_ROOT", raising=False)
    (tmp_path / ".env").write_text(
        "MODEL_BASE_URL=http://127.0.0.1:1234\nMODEL_NAME=demo-model\nAPP_MEMORY_ROOT=knowledge/runtime-memory\n",
        encoding="utf-8",
    )

    settings = load_memory_settings()

    assert settings.root_dir == Path("knowledge/runtime-memory")
    assert os.getenv("APP_MEMORY_ROOT") is None
