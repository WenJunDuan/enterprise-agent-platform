"""Tender project entity store (SQLite) — 招标项目，owns N 个投标评标。

招标项目是一等领域实体（区别于 ``tender_tasks`` 的单次执行态、``results`` 的单次结论）：
一个招标 owns 多家投标人评标。bid 名册 / 排名 / recommendedBidder **不在此存**，由路由层
按需聚合 ``results``（避免去同步，见 design.md §3.1）。

``get_or_create_project`` 幂等防同 ``(tenant, tender_no)`` 并发重复建（codex P1.2）：
靠 ``UNIQUE(tenant, tender_no) WHERE tender_no IS NOT NULL`` 部分索引兜底。
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from typing import Any

from server.platform.paths import PLATFORM_DB_FILE, ensure_local_layout
from server.platform.sqlite_store import connect_sqlite

ensure_local_layout()

# 招标项目生命周期状态（对齐前端 TenderProject.status）。
VALID_PROJECT_STATUS = {"doing", "review", "done", "archived"}


@dataclass(slots=True)
class TenderProjectRecord:
    project_id: str
    tenant: str
    tender_no: str | None = None  # 招标编号（前端 code）
    title: str | None = None  # 项目名（前端 name）
    tenderee: str | None = None  # 招标人
    method: str | None = None  # 评标方法
    control_price: str | None = None  # 标底 / 控制价（前端 controlPrice）
    funding_type: str | None = None  # state_funded/other/unknown（compare 推荐终局护栏用，evalmethod_013）
    status: str = "doing"
    created_at: str = ""
    updated_at: str = ""


_FIELDS = [f.name for f in fields(TenderProjectRecord)]
_COLUMNS = ", ".join(_FIELDS)
_PLACEHOLDERS = ", ".join("?" for _ in _FIELDS)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_project_id() -> str:
    return f"tp-{uuid.uuid4().hex[:16]}"


def _initialize_schema() -> None:
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS tender_projects (
                project_id TEXT PRIMARY KEY,
                tenant TEXT NOT NULL,
                tender_no TEXT,
                title TEXT,
                tenderee TEXT,
                method TEXT,
                control_price TEXT,
                funding_type TEXT,
                status TEXT NOT NULL DEFAULT 'doing',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        # 既有表（建于 funding_type 加入前）按需补列，幂等。
        existing_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(tender_projects)").fetchall()
        }
        if "funding_type" not in existing_columns:
            connection.execute("ALTER TABLE tender_projects ADD COLUMN funding_type TEXT")
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_tender_projects_tenant
                ON tender_projects (tenant, created_at DESC);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tender_projects_tenant_no
                ON tender_projects (tenant, tender_no) WHERE tender_no IS NOT NULL;
            """
        )


_initialize_schema()


def _record_values(record: TenderProjectRecord) -> tuple[Any, ...]:
    data = asdict(record)
    return tuple(data[name] for name in _FIELDS)


def get_project(project_id: str, tenant: str) -> dict[str, Any] | None:
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        row = connection.execute(
            "SELECT * FROM tender_projects WHERE project_id = ? AND tenant = ?",
            (project_id, tenant),
        ).fetchone()
        return dict(row) if row else None


def _get_by_tender_no(
    connection: sqlite3.Connection, tenant: str, tender_no: str
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM tender_projects WHERE tenant = ? AND tender_no = ?",
        (tenant, tender_no),
    ).fetchone()
    return dict(row) if row else None


def get_or_create_project(
    *,
    tenant: str,
    tender_no: str | None = None,
    title: str | None = None,
    tenderee: str | None = None,
    method: str | None = None,
    control_price: str | None = None,
    funding_type: str | None = None,
) -> dict[str, Any]:
    """幂等建招标项目：同 ``(tenant, tender_no)`` 已存在则返回现有（codex P1.2）。

    ``tender_no`` 为空时不去重（允许多条匿名项目，每次新建）。``immediate=True`` 取写锁让
    check-then-insert 原子；并发抢建由 ``UNIQUE`` 部分索引兜底（抢输方 catch IntegrityError 回读）。
    """
    # codex P1.2：空串 "" 非 NULL 会进部分唯一索引 `WHERE tender_no IS NOT NULL`，重复 "" 插入
    # 会冲突且绕过下面 `if tender_no` 的兜底 → 500。归一为 None，让空值走"匿名多条"分支。
    tender_no = (tender_no or "").strip() or None
    now = _utc_now()
    record = TenderProjectRecord(
        project_id=new_project_id(),
        tenant=tenant,
        tender_no=tender_no,
        title=title,
        tenderee=tenderee,
        method=method,
        control_price=control_price,
        funding_type=funding_type,
        status="doing",
        created_at=now,
        updated_at=now,
    )
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as connection:
        if tender_no:
            existing = _get_by_tender_no(connection, tenant, tender_no)
            if existing:
                return existing
        try:
            connection.execute(
                f"INSERT INTO tender_projects ({_COLUMNS}) VALUES ({_PLACEHOLDERS})",
                _record_values(record),
            )
        except sqlite3.IntegrityError:
            # 并发抢建：UNIQUE(tenant, tender_no) 部分索引拦下，回读现有。
            if tender_no:
                existing = _get_by_tender_no(connection, tenant, tender_no)
                if existing:
                    return existing
            raise
    return asdict(record)


def list_projects(
    tenant: str,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    query = "SELECT * FROM tender_projects WHERE tenant = ?"
    params: list[Any] = [tenant]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def update_project_status(project_id: str, tenant: str, status: str) -> bool:
    """更新招标项目状态（doing/review/done/archived）。返回是否命中。"""
    if status not in VALID_PROJECT_STATUS:
        raise ValueError(f"invalid project status: {status!r}")
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as connection:
        cursor = connection.execute(
            "UPDATE tender_projects SET status = ?, updated_at = ? "
            "WHERE project_id = ? AND tenant = ?",
            (status, _utc_now(), project_id, tenant),
        )
        return cursor.rowcount > 0
