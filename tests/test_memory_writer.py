from datetime import datetime
from pathlib import Path
from threading import Barrier, Thread

import pytest

from server.memory_writer import MemoryRecord, append_memory_record


def test_append_memory_record_writes_daily_business_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_MEMORY_ROOT", "knowledge/runtime-memory")

    path = append_memory_record(
        MemoryRecord(
            source="claude",
            domain="expense",
            scenario="travel reimbursement",
            input_summary="employee submitted taxi receipt",
            outcome="requires manager approval",
            rule_ids=("expense.travel.001",),
            manual_confirmation="Finance asked for manager confirmation before reimbursement.",
            reusable_judgment="Taxi receipts above the limit still require manager approval.",
            pending_rule_updates=("Add approval requirement for out-of-policy taxi receipts.",),
            references=("knowledge/external/travel-policy.md",),
        ),
        now=datetime(2026, 3, 20, 9, 30, 0),
    )

    assert path == Path("knowledge/runtime-memory/2026/03/2026-03-20.md")

    content = (tmp_path / path).read_text(encoding="utf-8")
    assert "# 业务运行记忆 - 2026-03-20" in content
    assert "### 09:30:00 | expense | travel reimbursement" in content
    assert "expense.travel.001" in content
    assert "Taxi receipts above the limit still require manager approval." in content
    assert "Add approval requirement for out-of-policy taxi receipts." in content


def test_append_memory_record_reuses_existing_daily_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_MEMORY_ROOT", "knowledge/memory")

    first_path = append_memory_record(
        MemoryRecord(
            source="claude",
            domain="expense",
            scenario="scenario-a",
            input_summary="input-a",
            outcome="outcome-a",
        ),
        now=datetime(2026, 3, 20, 9, 30, 0),
    )
    second_path = append_memory_record(
        MemoryRecord(
            source="claude",
            domain="expense",
            scenario="scenario-b",
            input_summary="input-b",
            outcome="outcome-b",
        ),
        now=datetime(2026, 3, 20, 10, 0, 0),
    )

    assert first_path == second_path

    content = (tmp_path / first_path).read_text(encoding="utf-8")
    assert content.count("# 业务运行记忆 - 2026-03-20") == 1
    assert "### 09:30:00 | expense | scenario-a" in content
    assert "### 10:00:00 | expense | scenario-b" in content


def test_append_memory_record_serializes_concurrent_appends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_MEMORY_ROOT", "knowledge/memory")

    barrier = Barrier(4)
    exceptions: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=5)
            append_memory_record(
                MemoryRecord(
                    source="claude",
                    domain="expense",
                    scenario=f"scenario-{index}",
                    input_summary=f"input-{index}",
                    outcome=f"outcome-{index}",
                ),
                now=datetime(2026, 3, 20, 9, 30 + index, 0),
            )
        except BaseException as exc:  # pragma: no cover - surfaced by assertion below
            exceptions.append(exc)

    threads = [Thread(target=worker, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not exceptions

    content = (tmp_path / "knowledge" / "memory" / "2026" / "03" / "2026-03-20.md").read_text(
        encoding="utf-8"
    )
    for index in range(4):
        assert f"scenario-{index}" in content
