"""Tender price-comparison result store (SQLite) — 招标项目级横比结论。

compare 结果**不进 ``results`` 表**（codex P1.1：避免被 ``_project_bid_roster`` 当成伪投标人），
独立存 ``tender_compare_results``（project_id 主键，一招标一份最新横比）。

存输入签名（``input_result_ids`` + ``criteria_hash``）以支持 stale 检测（codex P2.6）：
追加投标 / 重评后参与集变化，旧 compare 结果应标记 stale，不展示陈旧推荐。
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from server.platform.paths import PLATFORM_DB_FILE, ensure_local_layout
from server.platform.sqlite_store import connect_sqlite, utc_now

ensure_local_layout()


@dataclass(slots=True)
class CompareSignature:
    """参与横比的输入快照：completed 结论集 + criteria 指纹。"""

    input_result_ids: list[str]  # 参与的 completed request_id（排序）
    criteria_hash: str  # 各家 criteria 一致性指纹


# criteria 字段的已知默认值：显式写默认值与省略应得同一指纹（codex P2-6）。
_HASH_DEFAULT_FIELDS: dict[str, Any] = {"evaluator_type": "objective", "score_mode": "deduction"}


def _normalize_for_hash(value: Any) -> Any:
    """递归剔空值键 + 归一已知默认值，使"可选字段有无/空容器/显式默认值"不影响 criteria 指纹。

    多家投标人评同一招标应得一致 criteria（tender-evaluate S1 要求）；但模型可能一家输出
    ``deductions:[]`` / ``evaluator_type:"objective"`` 一家省略，语义相同却 JSON 不同 → 横比误判
    stale。v2 加 score_mode/deductions/bands/awards 等可选字段后漂移风险放大，故 hash 前规范化：
    剔空值键，并把等于已知默认值的字段（evaluator_type=objective / score_mode=deduction）视同未声明。
    """
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, val in value.items():
            normalized_val = _normalize_for_hash(val)
            if normalized_val in (None, [], {}, ""):
                continue
            if _HASH_DEFAULT_FIELDS.get(key) == normalized_val:  # 显式默认值 == 未声明
                continue
            cleaned[key] = normalized_val
        return cleaned
    if isinstance(value, list):
        return [_normalize_for_hash(item) for item in value]
    return value


def _strip_volatile_formula_data(criteria: Any) -> Any:
    """深拷贝 criteria 并剥 formula_spec.variables[].value/ref（评标时回填的数据侧，每家不同：本家
    报价、本家页码），保留 expression/rounding/cap/name/source/unit（招标标准侧，同标应一致）。防本家
    报价让同一招标各家 criteria 指纹漂移、横比误判 stale（codex P1-2：不能排整个 formula_spec）。"""
    if not isinstance(criteria, dict):
        return criteria
    crit = copy.deepcopy(criteria)
    for item in crit.get("items") or []:
        spec = item.get("formula_spec") if isinstance(item, dict) else None
        if not isinstance(spec, dict):
            continue
        for var in spec.get("variables") or []:
            if isinstance(var, dict):
                var.pop("value", None)
                var.pop("ref", None)
    return crit


def compute_criteria_hash(criteria: Any) -> str:
    """规范化 JSON 后 hash，作 criteria 一致性指纹（顺序无关、空可选字段/本家公式数据无关）。"""
    stripped = _strip_volatile_formula_data(criteria)
    normalized = json.dumps(_normalize_for_hash(stripped), ensure_ascii=False, sort_keys=True)
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
                utc_now(),
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
