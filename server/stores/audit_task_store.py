"""Audit async-task status store — thin wrapper over the generic TaskStore (round4 F7).

逻辑在 ``server.stores.task_store.TaskStore``；这里只绑定 ``audit_tasks`` 表 + 一次性
legacy ``tasks.json`` backfill，并导出与历史一致的函数名，使既有调用方
(routes/worker/api/cli/ops) 零改。
"""

from __future__ import annotations

from server.platform.paths import LEGACY_AUDIT_TASK_FILE
from server.stores.task_store import TaskStore

_STORE = TaskStore("audit_tasks", legacy_file=LEGACY_AUDIT_TASK_FILE)

upsert_audit_task = _STORE.upsert
delete_audit_task = _STORE.delete
try_transition_audit_task = _STORE.try_transition       # round4 F6：原子 retry 占位
delete_audit_task_if_idle = _STORE.delete_if_idle        # round4 F6：原子守卫删除
get_audit_task = _STORE.get
list_audit_tasks = _STORE.list
get_audit_task_admin = _STORE.get_admin
list_audit_tasks_admin = _STORE.list_admin
recover_stale_audit_tasks = _STORE.recover_stale
