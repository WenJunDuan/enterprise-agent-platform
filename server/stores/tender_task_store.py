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
try_transition_tender_task = _STORE.try_transition       # round4 F6：原子 retry 占位
delete_tender_task_if_idle = _STORE.delete_if_idle        # round4 F6：原子守卫删除
get_tender_task = _STORE.get
list_tender_tasks = _STORE.list
get_tender_task_admin = _STORE.get_admin
list_tender_tasks_admin = _STORE.list_admin
recover_stale_tender_tasks = _STORE.recover_stale
update_tender_progress = _STORE.update_progress           # 思考流式：评标进度轻量写


def list_tender_tasks_by_project(
    tenant: str,
    project_id: str,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """列某招标项目下的投标评标任务。

    tender 边界统一用 ``project_id``（codex P2.4）——泛型 TaskStore 内部以 ``group_id`` 落库，
    本 wrapper 把 project_id 映射成 group_id 过滤，使 ``group_id`` 不泄漏到路由层 DTO。
    """
    return _STORE.list(
        tenant, status=status, limit=limit, offset=offset, group_id=project_id
    )
