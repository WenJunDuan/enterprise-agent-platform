"""Structured result archiving for JSON schema responses."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Protocol

from server.platform.paths import RESULT_INDEX_DB_FILE, ensure_local_layout
from server.platform.sqlite_store import connect_sqlite, describe_sqlite_target, row_to_dict

ensure_local_layout()

StructuredJSON = dict[str, Any] | list[Any]


@dataclass(slots=True)
class ResultRecord:
    request_id: str
    created_at: str
    conversation_id: str
    request_mode: str
    schema_name: str | None
    result_file: str
    tenant: str | None = None
    project_id: str | None = None  # 招标项目分组键（tender）；非 tender 域留空
    bid_id: str | None = None  # results↔bids join key（tender）；非 tender 域留空
    bidder_name: str | None = None  # agent 识别的投标单位名称（tender）；非 tender 域留空
    claude_session_id: str | None = None
    session_id: str | None = None
    resume_session_id: str | None = None
    fork_from_session_id: str | None = None
    result_subtype: str | None = None
    claim_id: str | None = None
    verdict: str | None = None
    manual_review_reason: str | None = None
    cost_usd: float = 0.0
    prompt_preview: str | None = None


class ResultStore(Protocol):
    """Persistence boundary for archived structured outputs."""

    def archive_result(self, record: ResultRecord, payload: dict[str, Any]) -> None: ...

    def list_records(
        self,
        tenant: str,
        conversation_id: str | None = None,
        claim_id: str | None = None,
        verdict: str | None = None,
        manual_review_reason: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def get_record_by_request_id(
        self,
        request_id: str,
        tenant: str,
    ) -> dict[str, Any] | None: ...

    def get_payload_by_request_id(
        self,
        request_id: str,
        tenant: str,
    ) -> dict[str, Any] | None: ...

    def update_payload(
        self,
        request_id: str,
        tenant: str,
        payload: dict[str, Any],
    ) -> None: ...

    def list_results_by_project(
        self,
        tenant: str,
        project_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def list_records_admin(
        self,
        conversation_id: str | None = None,
        claim_id: str | None = None,
        verdict: str | None = None,
        manual_review_reason: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]: ...

    def get_record_by_request_id_admin(self, request_id: str) -> dict[str, Any] | None: ...

    def get_payload_by_request_id_admin(self, request_id: str) -> dict[str, Any] | None: ...

    def describe(self) -> dict[str, Any]: ...


class SQLiteResultStore:
    """SQLite-backed structured result index with JSON archive payloads."""

    COLUMNS: ClassVar[list[str]] = [
        "request_id",
        "created_at",
        "conversation_id",
        "request_mode",
        "schema_name",
        "result_file",
        "tenant",
        "project_id",
        "bid_id",
        "bidder_name",
        "claude_session_id",
        "session_id",
        "resume_session_id",
        "fork_from_session_id",
        "result_subtype",
        "claim_id",
        "verdict",
        "manual_review_reason",
        "cost_usd",
        "prompt_preview",
    ]

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._initialize_schema()

    def archive_result(self, record: ResultRecord, payload: dict[str, Any]) -> None:
        # B1: 完整 payload 折叠进 payload TEXT 列（不再写 by-request 文件树）。
        columns = [*self.COLUMNS, "payload"]
        placeholders = ", ".join("?" for _ in columns)
        values = (*self._record_values(asdict(record)), json.dumps(payload, ensure_ascii=False))
        with connect_sqlite(self.db_path) as connection:
            connection.execute(
                f"INSERT OR REPLACE INTO results ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )

    def list_records(
        self,
        tenant: str,
        conversation_id: str | None = None,
        claim_id: str | None = None,
        verdict: str | None = None,
        manual_review_reason: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM results WHERE tenant = ?"
        params: list[Any] = [tenant]
        if conversation_id:
            query += " AND conversation_id = ?"
            params.append(conversation_id)
        if claim_id:
            query += " AND claim_id = ?"
            params.append(claim_id)
        if verdict:
            query += " AND verdict = ?"
            params.append(verdict)
        if manual_review_reason:
            query += " AND manual_review_reason = ?"
            params.append(manual_review_reason)
        query += " ORDER BY created_at DESC, request_id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_record_by_request_id(
        self,
        request_id: str,
        tenant: str,
    ) -> dict[str, Any] | None:
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM results WHERE request_id = ? AND tenant = ?",
                (request_id, tenant),
            ).fetchone()
        return row_to_dict(row)

    def get_payload_by_request_id(
        self,
        request_id: str,
        tenant: str,
    ) -> dict[str, Any] | None:
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT payload FROM results WHERE request_id = ? AND tenant = ?",
                (request_id, tenant),
            ).fetchone()
        if row is None or row["payload"] is None:
            return None
        return json.loads(row["payload"])

    def update_payload(
        self,
        request_id: str,
        tenant: str,
        payload: dict[str, Any],
    ) -> None:
        with connect_sqlite(self.db_path) as connection:
            connection.execute(
                "UPDATE results SET payload = ? WHERE request_id = ? AND tenant = ?",
                (json.dumps(payload, ensure_ascii=False), request_id, tenant),
            )

    def list_results_by_project(
        self,
        tenant: str,
        project_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        # 招标项目下所有结论回看：走 results.project_id，独立于任务删除（codex P1.1）。
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM results WHERE tenant = ? AND project_id = ? "
                "ORDER BY created_at DESC, request_id DESC LIMIT ? OFFSET ?",
                (tenant, project_id, limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_records_admin(
        self,
        conversation_id: str | None = None,
        claim_id: str | None = None,
        verdict: str | None = None,
        manual_review_reason: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM results"
        clauses: list[str] = []
        params: list[Any] = []
        if conversation_id:
            clauses.append("conversation_id = ?")
            params.append(conversation_id)
        if claim_id:
            clauses.append("claim_id = ?")
            params.append(claim_id)
        if verdict:
            clauses.append("verdict = ?")
            params.append(verdict)
        if manual_review_reason:
            clauses.append("manual_review_reason = ?")
            params.append(manual_review_reason)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC, request_id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with connect_sqlite(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_record_by_request_id_admin(self, request_id: str) -> dict[str, Any] | None:
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM results WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return row_to_dict(row)

    def get_payload_by_request_id_admin(self, request_id: str) -> dict[str, Any] | None:
        with connect_sqlite(self.db_path) as connection:
            row = connection.execute(
                "SELECT payload FROM results WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        if row is None or row["payload"] is None:
            return None
        return json.loads(row["payload"])

    def describe(self) -> dict[str, Any]:
        return describe_sqlite_target(self.db_path, backend="sqlite")

    def _initialize_schema(self) -> None:
        with connect_sqlite(self.db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS results (
                    request_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    request_mode TEXT NOT NULL,
                    schema_name TEXT,
                    result_file TEXT NOT NULL,
                    tenant TEXT,
                    project_id TEXT,
                    bid_id TEXT,
                    bidder_name TEXT,
                    claude_session_id TEXT,
                    session_id TEXT,
                    resume_session_id TEXT,
                    fork_from_session_id TEXT,
                    result_subtype TEXT,
                    claim_id TEXT,
                    verdict TEXT,
                    manual_review_reason TEXT,
                    cost_usd REAL NOT NULL DEFAULT 0,
                    prompt_preview TEXT,
                    payload TEXT
                );
                """
            )
            existing_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(results)").fetchall()
            }
            if "manual_review_reason" not in existing_columns:
                connection.execute(
                    "ALTER TABLE results ADD COLUMN manual_review_reason TEXT"
                )
            if "payload" not in existing_columns:
                connection.execute("ALTER TABLE results ADD COLUMN payload TEXT")
            if "project_id" not in existing_columns:
                connection.execute("ALTER TABLE results ADD COLUMN project_id TEXT")
            if "bid_id" not in existing_columns:
                connection.execute("ALTER TABLE results ADD COLUMN bid_id TEXT")
            if "bidder_name" not in existing_columns:
                connection.execute("ALTER TABLE results ADD COLUMN bidder_name TEXT")
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_results_tenant_created
                    ON results (tenant, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_results_conversation
                    ON results (tenant, conversation_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_results_claim
                    ON results (tenant, claim_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_results_verdict_reason
                    ON results (tenant, verdict, manual_review_reason, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_results_project
                    ON results (tenant, project_id, created_at DESC);
                """
            )

    def _record_values(self, record: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(record.get(column) for column in self.COLUMNS)


RESULT_STORE: ResultStore = SQLiteResultStore(RESULT_INDEX_DB_FILE)


def archive_result_payload(
    *,
    request_id: str,
    tenant: str | None,
    conversation_id: str,
    claude_session_id: str | None,
    resume_session_id: str | None,
    fork_from_session_id: str | None,
    schema_name: str | None,
    request_mode: str,
    result_subtype: str | None,
    cost_usd: float,
    prompt_preview: str | None,
    response: StructuredJSON,
    created_at: str | None = None,
    project_id: str | None = None,
    bid_id: str | None = None,
) -> ResultRecord:
    """Persist a structured result and return its metadata record.

    ``project_id`` 是 tender 招标项目分组键，由调用链显式透传（codex P1.3：显式参数，
    不走 ``**opts`` 以免被当成 SDK 选项）；非 tender 域留 None。

    ``bid_id``（X2）是 results↔``tender_bid_docs`` 的 join key，同样显式透传、非 tender
    域留 None。``bidder_name`` 从 ``response.extracted_data.bidder_info.bidder_name``
    拍平（agent 识别的投标单位名称；识别不到则留 None，不编造）。
    """
    created_at = created_at or datetime.now(UTC).isoformat()
    claim_id = response.get("claim_id") if isinstance(response, dict) else None
    verdict = response.get("verdict") if isinstance(response, dict) else None
    manual_review_reason = response.get("manual_review_reason") if isinstance(response, dict) else None
    extracted_data = response.get("extracted_data") if isinstance(response, dict) else None
    bidder_info = extracted_data.get("bidder_info") if isinstance(extracted_data, dict) else None
    bidder_name = bidder_info.get("bidder_name") if isinstance(bidder_info, dict) else None
    payload = {
        "request_id": request_id,
        "tenant": tenant,
        "project_id": project_id,
        "bid_id": bid_id,
        "conversation_id": conversation_id,
        "claude_session_id": claude_session_id,
        "resume_session_id": resume_session_id,
        "fork_from_session_id": fork_from_session_id,
        "schema_name": schema_name,
        "request_mode": request_mode,
        "result_subtype": result_subtype,
        "cost_usd": cost_usd,
        "prompt_preview": prompt_preview,
        "created_at": created_at,
        "response": response,
    }
    record = ResultRecord(
        request_id=request_id,
        tenant=tenant,
        project_id=project_id,
        bid_id=bid_id,
        bidder_name=str(bidder_name) if bidder_name else None,
        conversation_id=conversation_id,
        claude_session_id=claude_session_id,
        session_id=claude_session_id,
        resume_session_id=resume_session_id,
        fork_from_session_id=fork_from_session_id,
        schema_name=schema_name,
        request_mode=request_mode,
        result_subtype=result_subtype,
        claim_id=str(claim_id) if claim_id else None,
        verdict=str(verdict) if verdict else None,
        manual_review_reason=str(manual_review_reason) if manual_review_reason else None,
        cost_usd=cost_usd,
        prompt_preview=prompt_preview,
        created_at=created_at,
        result_file=f"{request_id}.json",
    )
    RESULT_STORE.archive_result(record, payload)
    return record


def list_result_records(
    tenant: str,
    conversation_id: str | None = None,
    claim_id: str | None = None,
    verdict: str | None = None,
    manual_review_reason: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return RESULT_STORE.list_records(
        tenant=tenant,
        conversation_id=conversation_id,
        claim_id=claim_id,
        verdict=verdict,
        manual_review_reason=manual_review_reason,
        limit=limit,
        offset=offset,
    )


def get_result_record_by_request_id(
    request_id: str,
    tenant: str,
) -> dict[str, Any] | None:
    return RESULT_STORE.get_record_by_request_id(request_id=request_id, tenant=tenant)


def get_result_payload_by_request_id(
    request_id: str,
    tenant: str,
) -> dict[str, Any] | None:
    return RESULT_STORE.get_payload_by_request_id(request_id=request_id, tenant=tenant)


def update_result_criteria_ref(
    request_id: str,
    tenant: str,
    criteria_ref: dict[str, str],
) -> None:
    """把服务端权威判定的 ``criteria_ref`` 补写进已归档结论（KD1）。

    结论归档发生在 ``json_bridge.run_agent_json`` 内部，而 ref 由 runner 在拿到 payload 之后
    才确定性打上（不依赖模型回声），故需要这一次补写；否则横比读到的行永远没有 ref。

    Args:
        request_id: 结论 ID。
        tenant: 租户作用域（WHERE 带租户，杜绝跨租户改写）。
        criteria_ref: ``{"version", "source"}``。
    """
    stored = RESULT_STORE.get_payload_by_request_id(request_id=request_id, tenant=tenant)
    if not isinstance(stored, dict):
        return
    response = stored.get("response")
    if not isinstance(response, dict):
        return
    extracted = response.get("extracted_data")
    if not isinstance(extracted, dict):
        extracted = {}
        response["extracted_data"] = extracted
    extracted["criteria_ref"] = criteria_ref
    RESULT_STORE.update_payload(request_id=request_id, tenant=tenant, payload=stored)


def list_results_by_project(
    tenant: str,
    project_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """招标项目下所有结论回看（走 results.project_id，独立于任务删除）。"""
    return RESULT_STORE.list_results_by_project(
        tenant=tenant, project_id=project_id, limit=limit, offset=offset
    )


def list_latest_results_by_project(
    tenant: str,
    project_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """招标项目下**每个投标人最新一条**结论（KD4：同家重评不双行入横比池）。

    去重键优先 ``bid_id``（投标文档标识，最稳定），无 bid_id 的散单退 ``claim_id``，
    再退 ``request_id``（等于不去重）。底层查询已按 ``created_at DESC`` 排序，
    故每个键**首次**出现的即最新一条。

    Args:
        tenant: 租户作用域。
        project_id: 招标项目 ID。
        limit: 底层取行上限（去重前）。
    """
    seen: set[str] = set()
    latest: list[dict[str, Any]] = []
    for row in list_results_by_project(tenant, project_id, limit=limit):
        key = str(row.get("bid_id") or row.get("claim_id") or row.get("request_id"))
        if key in seen:
            continue
        seen.add(key)
        latest.append(row)
    return latest


def list_result_records_admin(
    conversation_id: str | None = None,
    claim_id: str | None = None,
    verdict: str | None = None,
    manual_review_reason: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return RESULT_STORE.list_records_admin(
        conversation_id=conversation_id,
        claim_id=claim_id,
        verdict=verdict,
        manual_review_reason=manual_review_reason,
        limit=limit,
        offset=offset,
    )


def get_result_record_by_request_id_admin(request_id: str) -> dict[str, Any] | None:
    return RESULT_STORE.get_record_by_request_id_admin(request_id)


def get_result_payload_by_request_id_admin(request_id: str) -> dict[str, Any] | None:
    return RESULT_STORE.get_payload_by_request_id_admin(request_id)


def describe_result_store() -> dict[str, Any]:
    return RESULT_STORE.describe()
