"""Tender price-comparison result store (SQLite) — 招标项目级横比结论。

compare 结果**不进 ``results`` 表**（codex P1.1：避免被 ``_project_bid_roster`` 当成伪投标人），
独立存 ``tender_compare_results``（project_id 主键，一招标一份最新横比）。

存输入签名（``input_result_ids`` + ``criteria_hash``）以支持 stale 检测（codex P2.6）：
追加投标 / 重评后参与集变化，旧 compare 结果应标记 stale，不展示陈旧推荐。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from server.platform.paths import PLATFORM_DB_FILE, ensure_local_layout
from server.platform.sqlite_store import connect_sqlite

ensure_local_layout()


@dataclass(slots=True)
class CompareSignature:
    """参与横比的输入快照：completed 结论集 + criteria 指纹。"""

    input_result_ids: list[str]  # 参与的 completed request_id（排序）
    criteria_hash: str  # 各家 criteria 一致性指纹


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_criteria_hash(criteria: Any) -> str:
    """规范化 JSON 后 hash，作 criteria 一致性指纹（顺序无关）。"""
    normalized = json.dumps(criteria, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def compute_input_signature(request_ids: list[str], criteria_hash: str) -> str:
    """参与集 + criteria 的整体签名，用于 stale 比对。"""
    joined = ",".join(sorted(request_ids)) + "|" + criteria_hash
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def _initialize_schema() -> None:
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS tender_compare_results (
                project_id TEXT PRIMARY KEY,
                tenant TEXT NOT NULL,
                payload TEXT NOT NULL,
                input_result_ids TEXT NOT NULL,
                criteria_hash TEXT,
                input_signature TEXT,
                computed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tender_compare_tenant
                ON tender_compare_results (tenant, computed_at DESC);
            """
        )


_initialize_schema()


def upsert_compare_result(
    *,
    project_id: str,
    tenant: str,
    payload: dict[str, Any],
    signature: CompareSignature,
) -> None:
    """写入/覆盖某招标项目的最新横比结果（一招标一份）。"""
    input_signature = compute_input_signature(
        signature.input_result_ids, signature.criteria_hash
    )
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO tender_compare_results "
            "(project_id, tenant, payload, input_result_ids, criteria_hash, "
            " input_signature, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                project_id,
                tenant,
                json.dumps(payload, ensure_ascii=False),
                json.dumps(sorted(signature.input_result_ids), ensure_ascii=False),
                signature.criteria_hash,
                input_signature,
                _utc_now(),
            ),
        )


def get_compare_result(project_id: str, tenant: str) -> dict[str, Any] | None:
    """取某招标项目的最新横比结果（含输入签名，供 stale 比对）。

    返回 ``{payload, input_result_ids, criteria_hash, input_signature, computed_at}``，
    无则 None。stale 判定由调用方用当前 completed 集签名比对 ``input_signature``。
    """
    with connect_sqlite(PLATFORM_DB_FILE) as connection:
        row = connection.execute(
            "SELECT * FROM tender_compare_results WHERE project_id = ? AND tenant = ?",
            (project_id, tenant),
        ).fetchone()
    if row is None:
        return None
    record = dict(row)
    record["payload"] = json.loads(record["payload"])
    record["input_result_ids"] = json.loads(record["input_result_ids"])
    return record


def is_stale(stored_signature: str | None, current_signature: str) -> bool:
    """当前参与集签名与存储不一致 → 旧 compare 结果过时（追加/重评后）。"""
    return stored_signature != current_signature
