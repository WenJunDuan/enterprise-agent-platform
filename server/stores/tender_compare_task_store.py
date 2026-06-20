"""Tender compare-task status store — 招标横比异步任务状态机。

绑定独立表 ``tender_compare_tasks``（codex P1.2：**不复用 ``tender_tasks``**），使横比任务与
单投标人评标任务彻底隔离——``_project_bid_roster`` 只聚合 ``tender_tasks``，compare 任务不会
被误当成在途投标人。逻辑复用泛型 ``TaskStore``（同 audit/tender）。
"""

from __future__ import annotations

from server.stores.task_store import TaskStore

_STORE = TaskStore("tender_compare_tasks")

upsert_compare_task = _STORE.upsert
delete_compare_task = _STORE.delete
try_transition_compare_task = _STORE.try_transition
get_compare_task = _STORE.get
list_compare_tasks = _STORE.list
get_compare_task_admin = _STORE.get_admin
recover_stale_compare_tasks = _STORE.recover_stale
