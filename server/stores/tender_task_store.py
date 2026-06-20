"""Tender async-task status store — thin wrapper over the generic TaskStore (round4 F7).

域隔离：``tender_tasks`` 表独立于 ``audit_tasks``（``mode`` 仍表示提交模式 directory/upload，
不承载域信息）。无 legacy backfill（tender 是新域，无旧 ``tasks.json`` 历史面）。
逻辑在 ``server.stores.task_store.TaskStore``；导出与历史一致的函数名使调用方零改。
"""

from __future__ import annotations

from server.stores.task_store import TaskStore

_STORE = TaskStore("tender_tasks")

upsert_tender_task = _STORE.upsert
delete_tender_task = _STORE.delete
get_tender_task = _STORE.get
list_tender_tasks = _STORE.list
get_tender_task_admin = _STORE.get_admin
list_tender_tasks_admin = _STORE.list_admin
recover_stale_tender_tasks = _STORE.recover_stale
