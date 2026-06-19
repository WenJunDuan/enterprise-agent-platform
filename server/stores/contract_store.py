"""Contract repository store (SQLite) for legal 合同审查 / 合同库.

一行一份合同（``contract_id`` PK）入统一库 ``platform.sqlite3``。结构化字段
（parties / clauses / payment_nodes / meta）以 JSON TEXT 列存储；合同原件大 blob 留文件
``data/contracts/<contract_id>/source/``，本 store 只记 ``source_path`` 指针。

分层：只依赖 platform（受 ``tests/test_layering.py::test_stores_only_import_platform`` 约束）。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from server.platform.paths import PLATFORM_DB_FILE, ensure_local_layout
from server.platform.sqlite_store import connect_sqlite

ensure_local_layout()

# 列顺序（contract_id 为 PK）。
_COLUMNS = (
    "contract_id",
    "tenant",
    "title",
    "contract_no",
    "sign_date",
    "amount",
    "currency",
    "term",
    "source_path",
    "parties",
    "clauses",
    "payment_nodes",
    "meta",
    "created_at",
    "updated_at",
)
# JSON 编码的 TEXT 列：写入 json.dumps，读出 json.loads。meta 默认 {}，其余默认 []。
_JSON_LIST_FIELDS = ("parties", "clauses", "payment_nodes")
_JSON_OBJECT_FIELDS = ("meta",)


def new_contract_id() -> str:
    """合同库主键。用 UUID —— 合同编号不可靠/可重复，不作主键（同合同去重留 v2）。"""
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _initialize_schema() -> None:
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS contracts (
                contract_id TEXT PRIMARY KEY,
                tenant TEXT,
                title TEXT,
                contract_no TEXT,
                sign_date TEXT,
                amount REAL,
                currency TEXT,
                term TEXT,
                source_path TEXT,
                parties TEXT NOT NULL DEFAULT '[]',
                clauses TEXT NOT NULL DEFAULT '[]',
                payment_nodes TEXT NOT NULL DEFAULT '[]',
                meta TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_contracts_tenant
                ON contracts (tenant, created_at DESC);
            """
        )


_initialize_schema()


def _encode(record: dict[str, Any]) -> tuple[Any, ...]:
    values: list[Any] = []
    for column in _COLUMNS:
        value = record.get(column)
        if column in _JSON_LIST_FIELDS:
            values.append(json.dumps(value if value is not None else [], ensure_ascii=False))
        elif column in _JSON_OBJECT_FIELDS:
            values.append(json.dumps(value if value is not None else {}, ensure_ascii=False))
        else:
            values.append(value)
    return tuple(values)


def _decode(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    for column in _JSON_LIST_FIELDS:
        decoded[column] = _loads(decoded.get(column), default=[])
    for column in _JSON_OBJECT_FIELDS:
        decoded[column] = _loads(decoded.get(column), default={})
    return decoded


def _loads(raw: Any, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        # 坏 JSON 不应让整次查询炸；降级回默认，调用方按缺字段处理。
        return default


def upsert_contract(record: dict[str, Any]) -> str:
    """Insert or replace one contract; returns its contract_id (生成 if missing).

    created_at 在已存在行上保留原值（再审查/修订只刷新 updated_at 与内容）。
    """
    contract_id = record.get("contract_id") or new_contract_id()
    now = _now()
    # immediate=True：读 created_at→合并→写 在一个原子事务内，防并发丢更新。
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as connection:
        existing = connection.execute(
            "SELECT created_at FROM contracts WHERE contract_id = ?", (contract_id,)
        ).fetchone()
        created_at = (dict(existing)["created_at"] if existing else "") or now
        merged = {**record, "contract_id": contract_id, "created_at": created_at, "updated_at": now}
        columns = ", ".join(_COLUMNS)
        placeholders = ", ".join("?" for _ in _COLUMNS)
        connection.execute(
            f"INSERT OR REPLACE INTO contracts ({columns}) VALUES ({placeholders})",
            _encode(merged),
        )
    return contract_id


def get_contract(contract_id: str, tenant: str) -> dict[str, Any] | None:
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        row = connection.execute(
            "SELECT * FROM contracts WHERE contract_id = ? AND tenant = ?",
            (contract_id, tenant),
        ).fetchone()
        return _decode(dict(row)) if row else None


def get_contract_admin(contract_id: str) -> dict[str, Any] | None:
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        row = connection.execute(
            "SELECT * FROM contracts WHERE contract_id = ?", (contract_id,)
        ).fetchone()
        return _decode(dict(row)) if row else None


def list_contracts(
    tenant: str,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        rows = connection.execute(
            "SELECT * FROM contracts WHERE tenant = ? "
            "ORDER BY COALESCE(created_at, updated_at) DESC LIMIT ? OFFSET ?",
            (tenant, limit, offset),
        ).fetchall()
        return [_decode(dict(row)) for row in rows]
