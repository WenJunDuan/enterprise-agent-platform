import pytest

from server.config import ModelSettings
from server.core import MemoryWriteError, run_chat
from server.memory_writer import MemoryRecord


def test_run_chat_returns_standardized_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "server.core.load_model_settings",
        lambda: ModelSettings(base_url="http://127.0.0.1:1234", model="demo-model", api_key=None),
    )
    monkeypatch.setattr(
        "server.core.chat_once",
        lambda message, settings, request_id="-": f"reply:{message}",
    )

    result = run_chat("hello", source="api", request_id="req-123")

    assert result.status == "ok"
    assert result.request_id == "req-123"
    assert result.source == "api"
    assert result.model == "demo-model"
    assert result.output_text == "reply:hello"
    assert result.memory_path is None


def test_run_chat_can_append_business_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "server.core.load_model_settings",
        lambda: ModelSettings(base_url="http://127.0.0.1:1234", model="demo-model", api_key=None),
    )
    monkeypatch.setattr(
        "server.core.chat_once",
        lambda message, settings, request_id="-": "reply:approved",
    )

    appended = {}

    def fake_append(record: MemoryRecord) -> str:
        appended["record"] = record
        return "knowledge/memory/2026/03/2026-03-20.md"

    monkeypatch.setattr("server.core.append_memory_record", fake_append)

    result = run_chat(
        "hello",
        source="api",
        request_id="req-456",
        memory_record=MemoryRecord(
            source="claude",
            domain="expense",
            scenario="travel reimbursement",
            input_summary="employee submitted taxi receipt",
            outcome="requires manager approval",
            reusable_judgment="Taxi receipts above the limit still require manager approval.",
        ),
    )

    assert appended["record"].scenario == "travel reimbursement"
    assert result.memory_path == "knowledge/memory/2026/03/2026-03-20.md"


def test_run_chat_raises_when_business_memory_append_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "server.core.load_model_settings",
        lambda: ModelSettings(base_url="http://127.0.0.1:1234", model="demo-model", api_key=None),
    )
    monkeypatch.setattr(
        "server.core.chat_once",
        lambda message, settings, request_id="-": "reply:approved",
    )
    monkeypatch.setattr(
        "server.core.append_memory_record",
        lambda record: (_ for _ in ()).throw(RuntimeError("disk full")),
    )

    with pytest.raises(MemoryWriteError, match="disk full"):
        run_chat(
            "hello",
            source="api",
            request_id="req-789",
            memory_record=MemoryRecord(
                source="claude",
                domain="expense",
                scenario="travel reimbursement",
                input_summary="employee submitted taxi receipt",
                outcome="requires manager approval",
            ),
        )
