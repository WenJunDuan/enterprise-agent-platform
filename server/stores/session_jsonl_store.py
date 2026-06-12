"""JSONL file-backed session store implementation."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from server.platform.storage import (
    append_jsonl_record,
    describe_storage_target,
    load_jsonl_records_from_paths,
    warn_if_store_capacity_exceeded,
)
from server.stores.session_records import SessionRecord, _month_key


class JSONLSessionStore:
    """File-backed session repository used by the serve layer."""

    def __init__(self, shard_dir: Path) -> None:
        self.shard_dir = shard_dir

    def append_record(self, record: SessionRecord) -> None:
        timestamp = record.finished_at or record.started_at
        shard_path = self.shard_dir / f"sessions-{_month_key(timestamp)}.jsonl"
        append_jsonl_record(shard_path, asdict(record))
        warn_if_store_capacity_exceeded(
            store_name="session_store",
            shard_dir=self.shard_dir,
            shard_path=shard_path,
        )

    def load_records(
        self,
        *,
        tenant: str,
        conversation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        records = self._load_records_admin(conversation_id=conversation_id)
        filtered: list[dict[str, Any]] = []
        for record in records:
            if record.get("tenant") != tenant:
                continue
            filtered.append(record)
        return filtered

    def get_record_by_request_id(
        self,
        request_id: str,
        tenant: str,
    ) -> dict[str, Any] | None:
        records = self.load_records(tenant=tenant)
        for record in reversed(records):
            if record.get("request_id") == request_id:
                return record
        return None

    def get_record_by_session_id(
        self,
        session_id: str,
        tenant: str,
    ) -> dict[str, Any] | None:
        records = self.load_records(tenant=tenant)
        for record in reversed(records):
            if record.get("claude_session_id") == session_id:
                return record
        return None

    def resolve_latest_session_id(
        self,
        conversation_id: str,
        tenant: str,
    ) -> str | None:
        records = self.load_records(conversation_id=conversation_id, tenant=tenant)
        for record in reversed(records):
            claude_session_id = record.get("claude_session_id")
            if claude_session_id:
                return str(claude_session_id)
        return None

    def list_logged_sessions(
        self,
        *,
        tenant: str,
        conversation_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        records = list(reversed(self.load_records(conversation_id=conversation_id, tenant=tenant)))
        return records[offset : offset + limit]

    def list_conversation_summaries(
        self,
        tenant: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        summaries: dict[str, dict[str, Any]] = {}
        for record in self.load_records(tenant=tenant):
            conversation_id = str(record["conversation_id"])
            summary = summaries.setdefault(
                conversation_id,
                {
                    "conversation_id": conversation_id,
                    "tenant": record.get("tenant"),
                    "request_count": 0,
                    "total_cost_usd": 0.0,
                    "latest_request_id": None,
                    "latest_claude_session_id": None,
                    "latest_status": None,
                    "latest_result_subtype": None,
                    "latest_schema_name": None,
                    "latest_prompt_preview": None,
                    "latest_result_file": None,
                    "first_started_at": record.get("started_at"),
                    "last_activity_at": record.get("finished_at") or record.get("started_at"),
                    "request_modes": set(),
                },
            )
            summary["request_count"] += 1
            summary["total_cost_usd"] = round(
                float(summary["total_cost_usd"]) + float(record.get("cost_usd", 0.0) or 0.0),
                6,
            )
            summary["latest_request_id"] = record.get("request_id")
            summary["latest_claude_session_id"] = record.get("claude_session_id")
            summary["latest_status"] = record.get("status")
            summary["latest_result_subtype"] = record.get("result_subtype")
            summary["latest_schema_name"] = record.get("schema_name")
            summary["latest_prompt_preview"] = record.get("prompt_preview")
            summary["latest_result_file"] = record.get("result_file")
            summary["last_activity_at"] = record.get("finished_at") or record.get("started_at")
            summary["request_modes"].add(record.get("request_mode"))

            started_at = record.get("started_at")
            if started_at and summary["first_started_at"] and started_at < summary["first_started_at"]:
                summary["first_started_at"] = started_at

        ordered = sorted(
            summaries.values(),
            key=lambda item: item.get("last_activity_at") or "",
            reverse=True,
        )
        sliced = ordered[offset : offset + limit]
        for item in sliced:
            item["request_modes"] = sorted(mode for mode in item["request_modes"] if mode)
        return sliced

    def list_known_session_ids(self, tenant: str) -> set[str]:
        session_ids: set[str] = set()
        for record in self.load_records(tenant=tenant):
            session_id = record.get("claude_session_id")
            if session_id:
                session_ids.add(str(session_id))
        return session_ids

    def describe(self) -> dict[str, Any]:
        description = describe_storage_target(self.shard_dir)
        description["backend"] = "jsonl-sharded"
        return description

    def _shard_paths(self) -> list[Path]:
        return [item for item in sorted(self.shard_dir.glob("*.jsonl")) if item.is_file()]

    def _load_records_admin(self, conversation_id: str | None = None) -> list[dict[str, Any]]:
        records = load_jsonl_records_from_paths(self._shard_paths())
        if conversation_id is None:
            return records
        return [record for record in records if record.get("conversation_id") == conversation_id]

    def get_record_by_request_id_admin(self, request_id: str) -> dict[str, Any] | None:
        for record in reversed(self._load_records_admin()):
            if record.get("request_id") == request_id:
                return record
        return None

    def get_record_by_session_id_admin(self, session_id: str) -> dict[str, Any] | None:
        for record in reversed(self._load_records_admin()):
            if record.get("claude_session_id") == session_id:
                return record
        return None

    def resolve_latest_session_id_admin(self, conversation_id: str) -> str | None:
        for record in reversed(self._load_records_admin(conversation_id=conversation_id)):
            claude_session_id = record.get("claude_session_id")
            if claude_session_id:
                return str(claude_session_id)
        return None

    def list_logged_sessions_admin(
        self,
        conversation_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        records = list(reversed(self._load_records_admin(conversation_id=conversation_id)))
        return records[offset : offset + limit]

    def list_conversation_summaries_admin(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        summaries: dict[str, dict[str, Any]] = {}
        for record in self._load_records_admin():
            conversation_id = str(record["conversation_id"])
            summary = summaries.setdefault(
                conversation_id,
                {
                    "conversation_id": conversation_id,
                    "tenant": record.get("tenant"),
                    "request_count": 0,
                    "total_cost_usd": 0.0,
                    "latest_request_id": None,
                    "latest_claude_session_id": None,
                    "latest_status": None,
                    "latest_result_subtype": None,
                    "latest_schema_name": None,
                    "latest_prompt_preview": None,
                    "latest_result_file": None,
                    "first_started_at": record.get("started_at"),
                    "last_activity_at": record.get("finished_at") or record.get("started_at"),
                    "request_modes": set(),
                },
            )
            summary["request_count"] += 1
            summary["total_cost_usd"] = round(
                float(summary["total_cost_usd"]) + float(record.get("cost_usd", 0.0) or 0.0),
                6,
            )
            summary["latest_request_id"] = record.get("request_id")
            summary["latest_claude_session_id"] = record.get("claude_session_id")
            summary["latest_status"] = record.get("status")
            summary["latest_result_subtype"] = record.get("result_subtype")
            summary["latest_schema_name"] = record.get("schema_name")
            summary["latest_prompt_preview"] = record.get("prompt_preview")
            summary["latest_result_file"] = record.get("result_file")
            summary["last_activity_at"] = record.get("finished_at") or record.get("started_at")
            summary["request_modes"].add(record.get("request_mode"))

            started_at = record.get("started_at")
            if started_at and summary["first_started_at"] and started_at < summary["first_started_at"]:
                summary["first_started_at"] = started_at

        ordered = sorted(
            summaries.values(),
            key=lambda item: item.get("last_activity_at") or "",
            reverse=True,
        )
        sliced = ordered[offset : offset + limit]
        for item in sliced:
            item["request_modes"] = sorted(mode for mode in item["request_modes"] if mode)
        return sliced

    def list_known_session_ids_admin(self) -> set[str]:
        session_ids: set[str] = set()
        for record in self._load_records_admin():
            session_id = record.get("claude_session_id")
            if session_id:
                session_ids.add(str(session_id))
        return session_ids
