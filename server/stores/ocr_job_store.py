"""OCR job async-task status store — thin wrapper over the generic TaskStore.

D9 streaming-ocr T2/T3: binds an independent ``ocr_jobs`` table (round4 F7 pattern,
same as ``audit_task_store`` / ``tender_task_store``). No legacy backfill — this is a
new feature with no prior JSON blob to import. Kept as a wrapper (not raw ``TaskStore``
calls in routes/worker) so the table name and any future OCR-job-specific behaviour
stay in one place, mirroring the existing domain stores.
"""

from __future__ import annotations

from server.stores.task_store import TaskStore

_STORE = TaskStore("ocr_jobs")

upsert_ocr_job = _STORE.upsert
get_ocr_job = _STORE.get
update_ocr_job_progress = _STORE.update_progress
recover_stale_ocr_jobs = _STORE.recover_stale
