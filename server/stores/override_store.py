"""Human-override feedback store (G5：人工否决→案例记忆 的唯一复利回路).

人工否决/改判一次 = 一条高置信负样本。Python 只**记录**这条原始反馈（哪个 request、
原判→人判、理由）；把它提炼成案例记忆由 Claude 侧 ``distill-memory`` 完成（gotcha：
审核判断与记忆提炼都在 Claude 侧）。distill 据 ``list_pending_overrides`` 生成案例记忆后
``mark_distilled``，下次同型案件经 memory-query 召回为**风险提示**（仍按当前规则复检，不自动判）。

分层：只依赖 platform（受 test_stores_only_import_platform 守卫）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from server.platform.paths import PLATFORM_DB_FILE, ensure_local_layout
from server.platform.sqlite_store import connect_sqlite

ensure_local_layout()


def _initialize_schema() -> None:
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS human_overrides (
                request_id TEXT PRIMARY KEY,
                original_verdict TEXT,
                human_verdict TEXT NOT NULL,
                reason TEXT,
                distilled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_human_overrides_distilled
                ON human_overrides (distilled, created_at DESC);
            """
        )


_initialize_schema()


def record_override(
    request_id: str,
    *,
    human_verdict: str,
    original_verdict: str | None = None,
    reason: str | None = None,
) -> None:
    """记录一次人工否决/改判（同 request_id 再记则覆盖，distilled 重置为 0 以便重新提炼）。"""
    now = datetime.now(timezone.utc).isoformat()
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO human_overrides "
            "(request_id, original_verdict, human_verdict, reason, distilled, created_at) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (request_id, original_verdict, human_verdict, reason, now),
        )


def get_override(request_id: str) -> dict[str, Any] | None:
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        row = connection.execute(
            "SELECT * FROM human_overrides WHERE request_id = ?", (request_id,)
        ).fetchone()
        return dict(row) if row else None


def list_pending_overrides(limit: int = 50) -> list[dict[str, Any]]:
    """尚未提炼成案例记忆的人工否决（供 Claude 侧 distill-memory 消费）。"""
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        rows = connection.execute(
            "SELECT * FROM human_overrides WHERE distilled = 0 "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def mark_distilled(request_id: str) -> None:
    """distill 已据本条生成案例记忆后调用，避免重复提炼。"""
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        connection.execute(
            "UPDATE human_overrides SET distilled = 1 WHERE request_id = ?", (request_id,)
        )
