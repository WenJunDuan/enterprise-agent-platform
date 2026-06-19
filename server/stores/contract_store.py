"""Contract repository store (SQLite) for legal 合同审查 / 合同库.

一行一份合同（``contract_id`` PK）入统一库 ``platform.sqlite3``。结构化字段
（parties / clauses / payment_nodes / meta）以 JSON TEXT 列存储；合同原件大 blob 留文件
``data/contracts/<contract_id>/source/``，本 store 只记 ``source_path`` 指针。

分层：只依赖 platform（受 ``tests/test_layering.py::test_stores_only_import_platform`` 约束）。
"""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from server.platform.paths import CONTRACTS_DATA_DIR, PLATFORM_DB_FILE, ensure_local_layout
from server.platform.sqlite_store import connect_sqlite

ensure_local_layout()

# 列顺序（contract_id 为 PK；request_id 回链产生本合同的审查 run，便于 result↔contract 互查）。
_COLUMNS = (
    "contract_id",
    "tenant",
    "request_id",
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
                request_id TEXT,
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
        # request_id 为后加列：先对早于本版建好的库幂等补列（新库 CREATE 已含），
        # 再建依赖该列的索引——顺序不能反，否则老表上建索引会因缺列报错。
        _ensure_column(connection, "contracts", "request_id", "TEXT")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_contracts_request_id ON contracts (request_id)"
        )


def _ensure_column(connection: Any, table: str, column: str, decl: str) -> None:
    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


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


def get_contract_by_request_id_admin(request_id: str) -> dict[str, Any] | None:
    """回链：由审查 run 的 request_id 找到落库的合同（admin，跨租户）。"""
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        row = connection.execute(
            "SELECT * FROM contracts WHERE request_id = ? ORDER BY created_at DESC LIMIT 1",
            (request_id,),
        ).fetchone()
        return _decode(dict(row)) if row else None


def persist_contract_from_result(
    result_payload: dict[str, Any],
    *,
    request_id: str,
    tenant: str | None,
    source_path: str,
    copy_source: bool = True,
) -> str | None:
    """从 /review-contract 的 audit-result 落库合同结构 + 留原件。

    读取 ``extracted_data.contract``（命令侧产出的合同结构），生成 contract_id 入库，
    并把原件 copy 到 ``data/contracts/<contract_id>/source/``。无合同结构时返回 None（不落库）。

    Args:
        result_payload: 符合 common/audit-result 的结论 JSON。
        request_id: 产生本结论的审查 run id（用于 result↔contract 回链）。
        tenant: 租户；CLI 本地审查可为 None。
        source_path: 原始合同目录或文件路径。
        copy_source: 是否把原件复制进合同库目录（测试可关）。

    Returns:
        生成的 contract_id；若结论未带 ``extracted_data.contract`` 则 None。
    """
    extracted = result_payload.get("extracted_data")
    contract = extracted.get("contract") if isinstance(extracted, dict) else None
    if not isinstance(contract, dict) or not contract:
        return None

    contract_id = new_contract_id()
    contract_meta = contract.get("contract_meta") if isinstance(contract.get("contract_meta"), dict) else {}
    stored_source_path = source_path
    if copy_source:
        stored_source_path = str(_copy_source(source_path, CONTRACTS_DATA_DIR / contract_id / "source"))

    upsert_contract(
        {
            "contract_id": contract_id,
            "tenant": tenant,
            "request_id": request_id,
            "title": contract_meta.get("title"),
            "contract_no": contract_meta.get("contract_no"),
            "sign_date": contract_meta.get("sign_date"),
            "amount": contract_meta.get("amount"),
            "currency": contract_meta.get("currency"),
            "term": contract_meta.get("term"),
            "source_path": stored_source_path,
            "parties": contract.get("parties") or [],
            "clauses": contract.get("clauses") or [],
            "payment_nodes": contract.get("payment_nodes") or [],
            "meta": {"attachments": contract.get("attachments") or []},
        }
    )
    return contract_id


def _copy_source(source_path: str, dest_dir: Path) -> Path:
    """Copy 原始合同文件/目录到合同库 source 目录，返回库内路径。"""
    src = Path(source_path)
    dest_dir.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dest_dir, dirs_exist_ok=True)
        return dest_dir
    target = dest_dir / src.name
    shutil.copy2(src, target)
    return target
