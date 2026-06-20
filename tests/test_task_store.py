"""泛型 TaskStore 安全守卫：非法表名被拒（f-string SQL 注入防线的回归测试）。"""

from __future__ import annotations

import pytest

from server.stores.task_store import TaskStore


def test_rejects_unsafe_table_name():
    with pytest.raises(ValueError):
        TaskStore("bad-name!; DROP TABLE x")


def test_rejects_uppercase_table_name():
    with pytest.raises(ValueError):
        TaskStore("AuditTasks")


def test_accepts_valid_table_name():
    # 合法表名（小写字母开头 + 下划线/数字）正常构造（复用已存在的 audit_tasks 表）。
    store = TaskStore("audit_tasks")
    assert store.table == "audit_tasks"
