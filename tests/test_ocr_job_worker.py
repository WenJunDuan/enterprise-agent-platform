"""D9 streaming-ocr T3：job worker 单测。

覆盖 design.md/plan.md T3 验收：准入闸 + 引用追踪（round4 F5 先例）、三态流转
（running → completed/failed）、units.jsonl 并发 append 完整性、partial 单调递增不回退、
0 单元 job 立即 completed（F4）、超时/异常 → failed、recover_stale 不触碰 units.jsonl（F5）。

用 native 文本文件驱动真实 extract_dir（route=native，无需 OCR 引擎/云服务）——只 mock
故障注入路径，不 mock 到底稿产出本身。
"""

from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid

import pytest

from server.routes import ocr_job_worker as worker
from server.routes.upload_helpers import build_case_dir
from server.stores.ocr_job_store import get_ocr_job, recover_stale_ocr_jobs, upsert_ocr_job

_TENANT = "ocr-job-worker-test"


@pytest.fixture
def rid():
    return f"job-{uuid.uuid4().hex}"


@pytest.fixture
def case_dir(rid):
    path = build_case_dir(_TENANT, "ocr", rid)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _write_files(target, count: int) -> None:
    for i in range(count):
        (target / f"doc-{i}.txt").write_text(f"内容 {i}", encoding="utf-8")


# ── 准入闸 / 引用追踪（round4 F5 先例，镜像 test_audit_worker.py）───────────


def test_admission_available_true_when_under_cap(monkeypatch):
    monkeypatch.setattr(worker, "_BACKGROUND_OCR_JOB_TASKS", set())
    monkeypatch.setattr(worker, "MAX_PENDING_OCR_JOBS", 2)
    assert worker.admission_available() is True


def test_admission_blocks_at_cap(monkeypatch):
    monkeypatch.setattr(worker, "_BACKGROUND_OCR_JOB_TASKS", {object(), object()})
    monkeypatch.setattr(worker, "MAX_PENDING_OCR_JOBS", 2)
    assert worker.admission_available() is False  # 在途已达上限 → 路由回 503


def test_track_task_keeps_ref_then_autoremoves(monkeypatch):
    fresh: set = set()
    monkeypatch.setattr(worker, "_BACKGROUND_OCR_JOB_TASKS", fresh)

    async def _scenario() -> asyncio.Task:
        async def _noop() -> None:
            return None

        task = asyncio.create_task(_noop())
        worker._track_task(task)
        assert task in fresh
        await task
        await asyncio.sleep(0)
        return task

    finished = asyncio.run(_scenario())
    assert finished not in fresh


# ── 三态流转 + units.jsonl ─────────────────────────────────────────────────


def test_execute_ocr_job_completes_and_writes_units(case_dir, rid):
    _write_files(case_dir, 3)
    asyncio.run(worker.execute_ocr_job(request_id=rid, tenant=_TENANT))

    record = get_ocr_job(rid, tenant=_TENANT)
    assert record is not None
    assert record["status"] == "completed"
    assert record["started_at"] is not None
    assert record["finished_at"] is not None

    units_path = case_dir / "units.jsonl"
    lines = [line for line in units_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert {p["file"] for p in parsed} == {str(case_dir / f"doc-{i}.txt") for i in range(3)}
    assert all(p["status"] == "ok" for p in parsed)

    progress = json.loads(record["progress_message"])
    assert progress == {"done": 3, "total": 3}


def test_execute_ocr_job_zero_files_completes_immediately(case_dir, rid):
    # case_dir 存在但为空目录 → total=0 → 立即 completed，不悬空等一个不会来的单元事件（F4）。
    asyncio.run(worker.execute_ocr_job(request_id=rid, tenant=_TENANT))
    record = get_ocr_job(rid, tenant=_TENANT)
    assert record["status"] == "completed"
    assert json.loads(record["progress_message"]) == {"done": 0, "total": 0}
    assert not (case_dir / "units.jsonl").exists()


def test_units_jsonl_concurrent_append_integrity(case_dir, rid):
    # 多文件触发 extract_dir 内部 ThreadPoolExecutor 并行 → on_unit_complete 从多个 worker
    # 线程并发调用；每行须是独立合法 JSON、总行数精确等于文件数（无交错/截断行）。
    n = 12
    _write_files(case_dir, n)
    asyncio.run(worker.execute_ocr_job(request_id=rid, tenant=_TENANT))

    lines = (case_dir / "units.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == n
    for line in lines:
        unit = json.loads(line)  # 交错写会产生非法 JSON 行，此处即失败
        assert set(unit) == {"file", "page", "status", "payload", "from_cache"}


def test_progress_done_monotonic_nondecreasing(case_dir, rid, monkeypatch):
    _write_files(case_dir, 6)
    seen: list[int] = []
    original = worker.update_ocr_job_progress

    def _spy(request_id: str, message: str) -> None:
        seen.append(json.loads(message)["done"])
        original(request_id, message)

    monkeypatch.setattr(worker, "update_ocr_job_progress", _spy)
    asyncio.run(worker.execute_ocr_job(request_id=rid, tenant=_TENANT))
    assert seen == sorted(seen)  # 单调不回退（partial results T3 验收）
    assert seen[-1] == 6


def test_execute_ocr_job_failure_sets_failed(case_dir, rid, monkeypatch):
    _write_files(case_dir, 2)

    def _boom(*args, **kwargs):
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(worker, "extract_dir", _boom)
    asyncio.run(worker.execute_ocr_job(request_id=rid, tenant=_TENANT))

    record = get_ocr_job(rid, tenant=_TENANT)
    assert record["status"] == "failed"
    assert "engine exploded" in record["error_detail"]


def test_execute_ocr_job_timeout_sets_failed(case_dir, rid, monkeypatch):
    _write_files(case_dir, 1)
    monkeypatch.setattr(worker, "OCR_JOB_TIMEOUT_SEC", 0.01)
    monkeypatch.setattr(worker, "_run_job_sync", lambda *a, **k: time.sleep(0.3))

    asyncio.run(worker.execute_ocr_job(request_id=rid, tenant=_TENANT))

    record = get_ocr_job(rid, tenant=_TENANT)
    assert record["status"] == "failed"
    assert "超时" in record["error_detail"]


# ── F5：recover_stale 不触碰 units.jsonl ──────────────────────────────────


def test_recover_stale_does_not_touch_units_jsonl(case_dir, rid):
    units_path = case_dir / "units.jsonl"
    units_path.write_text(
        '{"file": "a.txt", "page": null, "status": "ok", "payload": {}, "from_cache": false}\n',
        encoding="utf-8",
    )
    upsert_ocr_job(
        {
            "request_id": rid,
            "tenant": _TENANT,
            "status": "running",
            "mode": "upload",
            "source_mode": "upload",
            "case_path": str(case_dir),
            "started_at": "2000-01-01T00:00:00+00:00",
            "updated_at": "2000-01-01T00:00:00+00:00",
            "progress_message": json.dumps({"done": 1, "total": 2}),
        }
    )
    recovered = recover_stale_ocr_jobs(timeout_seconds=0, now="2099-01-01T00:00:00+00:00")
    assert rid in recovered

    record = get_ocr_job(rid, tenant=_TENANT)
    assert record["status"] == "failed"
    assert units_path.exists()
    assert "a.txt" in units_path.read_text(encoding="utf-8")  # partial 保留供人工核查
