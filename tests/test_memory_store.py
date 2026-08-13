"""Tests for server/stores/memory_store.py – _load_memory_files exception isolation."""

from __future__ import annotations

import json
import logging
from pathlib import Path


def _make_store(tmp_path: Path):
    """Return a SQLiteMemoryStore backed by tmp_path (isolated DB + memory root)."""
    from server.stores.memory_store import SQLiteMemoryStore

    db_path = tmp_path / "memory.db"
    memory_root = tmp_path / "memory"
    memory_root.mkdir()
    return SQLiteMemoryStore(db_path=db_path, memory_root=memory_root)


class TestLoadMemoryFilesExceptionIsolation:
    """Corrupt / unreadable JSON files must not crash the full index load."""

    def test_bad_json_file_is_skipped(self, tmp_path: Path):
        store = _make_store(tmp_path)
        memory_root = store.memory_root

        # Good file
        good = memory_root / "good.json"
        good.write_text(
            json.dumps(
                {
                    "memory_id": "mem-001",
                    "domain": "expense",
                    "memory_type": "audit_case",
                    "title": "Test memory",
                    "summary": "summary",
                    "recommended_verdict": "approved",
                    "rationale": "ok",
                    "tags": [],
                    "distilled_by": "test",
                    "distilled_at": "2024-01-01T00:00:00Z",
                    "source_trace": {
                        "request_id": "req-001",
                        "result_file": "file.json",
                    },
                }
            ),
            encoding="utf-8",
        )

        # Corrupt file
        bad = memory_root / "bad.json"
        bad.write_text("{not valid json !!!", encoding="utf-8")

        records = store._load_memory_files()

        # Bad file skipped; good file loaded
        assert len(records) == 1
        assert records[0]["memory_id"] == "mem-001"

    def test_bad_json_does_not_raise(self, tmp_path: Path):
        store = _make_store(tmp_path)
        memory_root = store.memory_root

        (memory_root / "corrupt.json").write_text("{{{{", encoding="utf-8")

        # Must not raise
        records = store._load_memory_files()
        assert records == []

    def test_bad_file_warning_is_logged(self, tmp_path: Path, caplog):
        store = _make_store(tmp_path)
        memory_root = store.memory_root

        (memory_root / "broken.json").write_text("not-json", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="server.stores.memory_store"):
            store._load_memory_files()

        assert any("corrupt" in record.message or "skipping" in record.message for record in caplog.records)

    def test_good_files_load_when_mixed_with_bad(self, tmp_path: Path):
        store = _make_store(tmp_path)
        memory_root = store.memory_root

        def _good_payload(memory_id: str) -> dict:
            return {
                "memory_id": memory_id,
                "domain": "expense",
                "memory_type": "audit_case",
                "title": f"Memory {memory_id}",
                "summary": "summary",
                "recommended_verdict": "approved",
                "rationale": "ok",
                "tags": [],
                "distilled_by": "test",
                "distilled_at": "2024-01-01T00:00:00Z",
                "source_trace": {
                    "request_id": f"req-{memory_id}",
                    "result_file": "file.json",
                },
            }

        (memory_root / "a_good.json").write_text(json.dumps(_good_payload("mem-a")), encoding="utf-8")
        (memory_root / "b_bad.json").write_text("{invalid", encoding="utf-8")
        (memory_root / "c_good.json").write_text(json.dumps(_good_payload("mem-c")), encoding="utf-8")

        records = store._load_memory_files()

        loaded_ids = {r["memory_id"] for r in records}
        assert loaded_ids == {"mem-a", "mem-c"}
        assert len(records) == 2
