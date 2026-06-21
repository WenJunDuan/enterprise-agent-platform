"""Tender doc layer store (SQLite) — 招标层 + 投标层 OCR 文档数据。

三层数据结构中的文档层（P2 设计）：
- ``tender_project_docs``：招标文件 OCR 底稿 + criteria（评分项，首次评标后回填）。
- ``tender_bid_docs``：各投标人文件 OCR 底稿 + extracted（抓点，评标后回填）。

每层 upsert 落盘路径由上传端点触发，后台 OCR 异步写 ocr_text / ocr_status。
评标读层优先取已 ready 的 ocr_text，未 ready → 回落原串行 OCR（兜底不破现有路径）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from server.platform.paths import PLATFORM_DB_FILE, ensure_local_layout
from server.platform.sqlite_store import connect_sqlite

ensure_local_layout()

# OCR 状态合法值（不做运行时强制，仅文档约定）
# pending → running → ready | failed
OCR_STATUSES = {"pending", "running", "ready", "failed"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_bid_id() -> str:
    """Generate a unique bid document id."""
    return f"bd-{uuid.uuid4().hex[:16]}"


def _initialize_schema() -> None:
    """Create both doc tables idempotently; add missing columns for existing DBs.

    R1 migration: tender_project_docs gains two columns for the tender-info-extraction
    feature. Both are added idempotently via PRAGMA table_info + ALTER TABLE so
    pre-existing databases upgrade without data loss.
      - criteria_status: tracks the info-extraction pipeline state (pending→running→ready|failed),
        independent of ocr_status.
      - tender_info: JSON-encoded tender metadata extracted from the OCR text
        (tender_no, tenderee, control_price, method, funding_hint).
    """
    with connect_sqlite(PLATFORM_DB_FILE) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tender_project_docs (
                project_id      TEXT PRIMARY KEY,
                tenant          TEXT NOT NULL,
                tender_files    TEXT NOT NULL DEFAULT '[]',
                ocr_text        TEXT,
                ocr_clarity     TEXT,
                ocr_status      TEXT NOT NULL DEFAULT 'pending',
                criteria        TEXT,
                criteria_status TEXT NOT NULL DEFAULT 'pending',
                tender_info     TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tender_bid_docs (
                project_id  TEXT NOT NULL,
                bid_id      TEXT NOT NULL,
                tenant      TEXT NOT NULL,
                bidder_name TEXT,
                bid_files   TEXT NOT NULL DEFAULT '[]',
                ocr_text    TEXT,
                ocr_status  TEXT NOT NULL DEFAULT 'pending',
                extracted   TEXT,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                PRIMARY KEY (project_id, bid_id)
            );
            CREATE INDEX IF NOT EXISTS idx_tender_project_docs_tenant
                ON tender_project_docs (tenant, project_id);
            CREATE INDEX IF NOT EXISTS idx_tender_bid_docs_project
                ON tender_bid_docs (project_id, tenant);
            """
        )
        # Idempotent ALTER TABLE for existing DBs that pre-date the R1 migration.
        existing_cols = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(tender_project_docs)"
            ).fetchall()
        }
        if "criteria_status" not in existing_cols:
            conn.execute(
                "ALTER TABLE tender_project_docs "
                "ADD COLUMN criteria_status TEXT NOT NULL DEFAULT 'pending'"
            )
        if "tender_info" not in existing_cols:
            conn.execute(
                "ALTER TABLE tender_project_docs ADD COLUMN tender_info TEXT"
            )


_initialize_schema()


# ── tender_project_docs CRUD ──────────────────────────────────────────────────


def upsert_project_doc(
    *,
    project_id: str,
    tenant: str,
    tender_files: str,
    ocr_status: str = "pending",
    ocr_text: str | None = None,
    ocr_clarity: str | None = None,
    criteria: str | None = None,
    criteria_status: str = "pending",
    tender_info: str | None = None,
) -> None:
    """Insert or replace a tender project doc record.

    Args:
        project_id: Tender project identifier (PK).
        tenant: Tenant scope for isolation.
        tender_files: JSON-encoded list of file paths/names.
        ocr_status: One of pending/running/ready/failed.
        ocr_text: Full OCR text blob (None until OCR completes).
        ocr_clarity: Clarity signal from OCR pipeline (clear/low/unknown/failed).
        criteria: JSON-encoded evaluation criteria (None until first evaluation).
        criteria_status: R1 info-extraction state: pending/running/ready/failed.
        tender_info: R1 JSON-encoded tender metadata extracted from the OCR text.
    """
    now = _utc_now()
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as conn:
        existing = conn.execute(
            "SELECT created_at FROM tender_project_docs WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        created_at = existing["created_at"] if existing else now
        conn.execute(
            """
            INSERT OR REPLACE INTO tender_project_docs
                (project_id, tenant, tender_files, ocr_text, ocr_clarity,
                 ocr_status, criteria, criteria_status, tender_info,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id, tenant, tender_files, ocr_text, ocr_clarity,
                ocr_status, criteria, criteria_status, tender_info,
                created_at, now,
            ),
        )


def get_project_doc(project_id: str, tenant: str) -> dict[str, Any] | None:
    """Fetch a tender project doc by project_id scoped to tenant.

    Returns:
        Row dict or None if not found or tenant mismatch.
    """
    with connect_sqlite(PLATFORM_DB_FILE) as conn:
        row = conn.execute(
            "SELECT * FROM tender_project_docs WHERE project_id = ? AND tenant = ?",
            (project_id, tenant),
        ).fetchone()
        return dict(row) if row else None


def update_project_doc_ocr(
    project_id: str,
    *,
    tenant: str,
    ocr_text: str | None,
    ocr_clarity: str | None,
    status: str,
) -> None:
    """Update OCR result fields after background OCR completes.

    Args:
        project_id: Tender project identifier.
        tenant: Tenant scope — WHERE clause includes tenant to prevent cross-tenant writes.
        ocr_text: Full text extracted by OCR (None on failure).
        ocr_clarity: Clarity signal (None on failure).
        status: New ocr_status (ready or failed).
    """
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as conn:
        conn.execute(
            """
            UPDATE tender_project_docs
            SET ocr_text = ?, ocr_clarity = ?, ocr_status = ?, updated_at = ?
            WHERE project_id = ? AND tenant = ?
            """,
            (ocr_text, ocr_clarity, status, _utc_now(), project_id, tenant),
        )


def update_project_doc_criteria(project_id: str, tenant: str, criteria_json: str) -> None:
    """Back-fill evaluation criteria after first evaluation parses them.

    Args:
        project_id: Tender project identifier.
        tenant: Tenant scope — WHERE clause includes tenant to prevent cross-tenant writes.
        criteria_json: JSON-encoded list of scoring criteria items.
    """
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as conn:
        conn.execute(
            "UPDATE tender_project_docs SET criteria = ?, updated_at = ? "
            "WHERE project_id = ? AND tenant = ?",
            (criteria_json, _utc_now(), project_id, tenant),
        )


def update_project_doc_criteria_extracted(
    project_id: str,
    tenant: str,
    *,
    criteria_json: str | None,
    tender_info_json: str | None,
    status: str,
) -> None:
    """Write criteria + tender_info + criteria_status in one tenant-scoped UPDATE.

    Called after the R1 tender-extract-info command completes (or fails).  Does NOT
    touch ocr_status — extraction failure must never affect the OCR-ready signal.

    Args:
        project_id: Tender project identifier.
        tenant: Tenant scope — WHERE clause includes tenant to prevent cross-tenant writes.
        criteria_json: JSON-encoded criteria object, or None on failure.
        tender_info_json: JSON-encoded tender_info object, or None on failure.
        status: New criteria_status value (ready or failed).
    """
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as conn:
        conn.execute(
            """
            UPDATE tender_project_docs
            SET criteria = ?, tender_info = ?, criteria_status = ?, updated_at = ?
            WHERE project_id = ? AND tenant = ?
            """,
            (criteria_json, tender_info_json, status, _utc_now(), project_id, tenant),
        )


# ── tender_bid_docs CRUD ──────────────────────────────────────────────────────


def upsert_bid_doc(
    *,
    project_id: str,
    bid_id: str,
    tenant: str,
    bidder_name: str | None,
    bid_files: str,
    ocr_status: str = "pending",
    ocr_text: str | None = None,
    extracted: str | None = None,
) -> None:
    """Insert or replace a bid document record.

    Args:
        project_id: Parent tender project identifier.
        bid_id: Unique bid document identifier (composite PK with project_id).
        tenant: Tenant scope for isolation.
        bidder_name: Bidder display name.
        bid_files: JSON-encoded list of uploaded file paths/names.
        ocr_status: One of pending/running/ready/failed.
        ocr_text: Full OCR text blob (None until OCR completes).
        extracted: JSON-encoded extracted fields (None until evaluation).
    """
    now = _utc_now()
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as conn:
        existing = conn.execute(
            "SELECT created_at FROM tender_bid_docs WHERE project_id = ? AND bid_id = ?",
            (project_id, bid_id),
        ).fetchone()
        created_at = existing["created_at"] if existing else now
        conn.execute(
            """
            INSERT OR REPLACE INTO tender_bid_docs
                (project_id, bid_id, tenant, bidder_name, bid_files,
                 ocr_text, ocr_status, extracted, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id, bid_id, tenant, bidder_name, bid_files,
                ocr_text, ocr_status, extracted, created_at, now,
            ),
        )


def get_bid_doc(project_id: str, bid_id: str, tenant: str) -> dict[str, Any] | None:
    """Fetch a bid doc by (project_id, bid_id) scoped to tenant.

    Returns:
        Row dict or None if not found or tenant mismatch.
    """
    with connect_sqlite(PLATFORM_DB_FILE) as conn:
        row = conn.execute(
            "SELECT * FROM tender_bid_docs WHERE project_id = ? AND bid_id = ? AND tenant = ?",
            (project_id, bid_id, tenant),
        ).fetchone()
        return dict(row) if row else None


def list_bid_docs(project_id: str, tenant: str) -> list[dict[str, Any]]:
    """List all bid docs for a project scoped to tenant.

    Args:
        project_id: Parent tender project identifier.
        tenant: Tenant scope for isolation.

    Returns:
        List of row dicts ordered by created_at ascending.
    """
    with connect_sqlite(PLATFORM_DB_FILE) as conn:
        rows = conn.execute(
            "SELECT * FROM tender_bid_docs WHERE project_id = ? AND tenant = ? ORDER BY created_at",
            (project_id, tenant),
        ).fetchall()
        return [dict(r) for r in rows]


def update_bid_doc_ocr(
    project_id: str,
    bid_id: str,
    *,
    tenant: str,
    ocr_text: str | None,
    status: str,
) -> None:
    """Update OCR result fields for a bid doc after background OCR completes.

    Args:
        project_id: Parent tender project identifier.
        bid_id: Bid document identifier.
        tenant: Tenant scope — WHERE clause includes tenant to prevent cross-tenant writes.
        ocr_text: Full text extracted by OCR (None on failure).
        status: New ocr_status (ready or failed).
    """
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as conn:
        conn.execute(
            """
            UPDATE tender_bid_docs
            SET ocr_text = ?, ocr_status = ?, updated_at = ?
            WHERE project_id = ? AND bid_id = ? AND tenant = ?
            """,
            (ocr_text, status, _utc_now(), project_id, bid_id, tenant),
        )


def update_bid_doc_extracted(project_id: str, bid_id: str, tenant: str, extracted_json: str) -> None:
    """Back-fill extracted fields after evaluation.

    Args:
        project_id: Parent tender project identifier.
        bid_id: Bid document identifier.
        tenant: Tenant scope — WHERE clause includes tenant to prevent cross-tenant writes.
        extracted_json: JSON-encoded extracted fields (bidder/price/qualifications).
    """
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as conn:
        conn.execute(
            """
            UPDATE tender_bid_docs
            SET extracted = ?, updated_at = ?
            WHERE project_id = ? AND bid_id = ? AND tenant = ?
            """,
            (extracted_json, _utc_now(), project_id, bid_id, tenant),
        )
