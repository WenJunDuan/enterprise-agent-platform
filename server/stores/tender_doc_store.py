"""Tender doc layer store (SQLite) — 招标层 + 投标层 OCR 文档数据。

三层数据结构中的文档层（P2 设计）：
- ``tender_project_docs``：招标文件 OCR 底稿 + criteria（评分项，首次评标后回填）。
- ``tender_bid_docs``：各投标人文件 OCR 底稿 + extracted（抓点，评标后回填）。

每层 upsert 落盘路径由上传端点触发，后台 OCR 异步写 ocr_text / ocr_status。
评标读层优先取已 ready 的 ocr_text，未 ready → 回落原串行 OCR（兜底不破现有路径）。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import Any

from server.platform.paths import PLATFORM_DB_FILE, ensure_local_layout
from server.platform.sqlite_store import connect_sqlite, utc_now

ensure_local_layout()

# OCR 状态合法值。pending → running → ready | degraded | partial | failed。
# H3 KD2 扩两档并改为**写入时强制校验**（见 _validate_ocr_status）：
#   degraded — 底稿完整但含 Tesseract 降级段（低质，不得当 ready 永久落库、之后永不重跑 VLM）；
#   partial  — 部分文件失败或某文件渲染中途失败只出了部分页。
# 未知值一律 fail-fast：静默落库后读侧只能猜，最坏被当成 ready 直接拿去评标。
OCR_STATUSES = {"pending", "running", "ready", "degraded", "partial", "failed"}


def _validate_ocr_status(status: str) -> str:
    """校验 ocr_status 取值；未知值抛错（绝不静默写入）。"""
    if status not in OCR_STATUSES:
        raise ValueError(
            f"unknown ocr_status {status!r}; expected one of {sorted(OCR_STATUSES)}"
        )
    return status


def _encode_failed_files(failed_files: Sequence[str] | None) -> str | None:
    """把"有问题的文件"清单（识别失败 + Tesseract 降级，见 OcrDocReport.problem_files）编码为
    JSON 文本列；None → 不记（与"没有问题"的区分靠 status）。"""
    if failed_files is None:
        return None
    return json.dumps(list(failed_files), ensure_ascii=False)


def decode_failed_files(raw: Any) -> list[str] | None:
    """``_encode_failed_files`` 的逆：JSON 文本列 → 文件名列表。

    与编码端对称、同处一个模块：列的编码格式只此一家知道，读侧（评标 warning 渲染、补跑回滚）
    各自 ``json.loads`` 会让"格式住在 store、解析散在调用方"（review F6）。

    Args:
        raw: doc 行的 ``ocr_failed_files`` 列原值（JSON 文本 / None）。

    Returns:
        文件名列表；缺失 / 非 JSON / 非列表 → ``None``（沿用编码端 ``None`` = "不记"的语义，
        与"记了个空清单"区分开）。
    """
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return [str(item) for item in parsed] if isinstance(parsed, list) else None


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
        # X2 migration: tender_bid_docs 加 bidder_name_source，区分手填(NULL)/
        # agent 回填(agent_extracted)，供只填空回填判优先级（手填任何情况下不被覆盖）。
        existing_bid_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(tender_bid_docs)").fetchall()
        }
        if "bidder_name_source" not in existing_bid_cols:
            conn.execute(
                "ALTER TABLE tender_bid_docs ADD COLUMN bidder_name_source TEXT"
            )
        # H3 KD2 migration（沿用同一幂等 PRAGMA + ALTER 先例，无迁移框架/无 downgrade）：
        #   ocr_failed_files — JSON 文件名列表，partial/degraded 时点名是哪些文件出的问题；
        #   case_path        — 上传落盘目录，供评标入口对非 ready 底稿自动重跑一次预热 OCR。
        for table, columns in (
            ("tender_project_docs", existing_cols),
            ("tender_bid_docs", existing_bid_cols),
        ):
            for column in ("ocr_failed_files", "case_path"):
                if column not in columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")


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
    case_path: str | None = None,
) -> None:
    """Insert or replace a tender project doc record.

    Args:
        project_id: Tender project identifier (PK).
        tenant: Tenant scope for isolation.
        tender_files: JSON-encoded list of file paths/names.
        ocr_status: One of ``OCR_STATUSES``.
        ocr_text: Full OCR text blob (None until OCR completes).
        ocr_clarity: Clarity signal from OCR pipeline (clear/low/unknown/failed).
        criteria: JSON-encoded evaluation criteria (None until first evaluation).
        criteria_status: R1 info-extraction state: pending/running/ready/failed.
        tender_info: R1 JSON-encoded tender metadata extracted from the OCR text.
        case_path: 上传落盘目录（H3 KD2：评标入口据此重跑预热 OCR）。
    """
    _validate_ocr_status(ocr_status)
    now = utc_now()
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
                 case_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id, tenant, tender_files, ocr_text, ocr_clarity,
                ocr_status, criteria, criteria_status, tender_info,
                case_path, created_at, now,
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
    failed_files: Sequence[str] | None = None,
) -> None:
    """Update OCR result fields after background OCR completes.

    Args:
        project_id: Tender project identifier.
        tenant: Tenant scope — WHERE clause includes tenant to prevent cross-tenant writes.
        ocr_text: Full text extracted by OCR (None on failure).
        ocr_clarity: Clarity signal (None on failure).
        status: New ocr_status；须属 ``OCR_STATUSES``，未知值抛 ValueError。
        failed_files: partial/degraded 时的失败文件名清单（H3 KD2）。

    Raises:
        ValueError: status 不在 ``OCR_STATUSES`` 内。
    """
    _validate_ocr_status(status)
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as conn:
        conn.execute(
            """
            UPDATE tender_project_docs
            SET ocr_text = ?, ocr_clarity = ?, ocr_status = ?, ocr_failed_files = ?,
                updated_at = ?
            WHERE project_id = ? AND tenant = ?
            """,
            (
                ocr_text,
                ocr_clarity,
                status,
                _encode_failed_files(failed_files),
                utc_now(),
                project_id,
                tenant,
            ),
        )


def set_doc_ocr_status(
    project_id: str, bid_id: str | None, *, tenant: str, status: str
) -> None:
    """只改 ``ocr_status``（保留既有 ocr_text / failed_files）。

    用于评标入口的补底稿重跑（H3 KD2/F3）：重跑期间把行置回 ``running``，让并发评标经
    in-flight oracle 判"已经有人在补"从而不重复触发；重跑超时则把状态放回原值，
    读层继续用手上那份降级底稿，绝不因为一次补跑失败就把可用底稿弄丢。

    Args:
        project_id: 招标项目标识。
        bid_id: 投标文档标识；``None`` 表示改招标层行。
        tenant: 租户作用域。
        status: 目标状态，须属 ``OCR_STATUSES``。

    Raises:
        ValueError: status 不在 ``OCR_STATUSES`` 内。
    """
    _validate_ocr_status(status)
    now = utc_now()
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as conn:
        if bid_id is None:
            conn.execute(
                "UPDATE tender_project_docs SET ocr_status = ?, updated_at = ? "
                "WHERE project_id = ? AND tenant = ?",
                (status, now, project_id, tenant),
            )
        else:
            conn.execute(
                "UPDATE tender_bid_docs SET ocr_status = ?, updated_at = ? "
                "WHERE project_id = ? AND bid_id = ? AND tenant = ?",
                (status, now, project_id, bid_id, tenant),
            )


def touch_project_doc_ocr(project_id: str, *, tenant: str) -> None:
    """预热心跳：刷新仍在 ``running`` 的招标层行的 ``updated_at``（H3 KD5）。

    评标侧的 in-flight oracle = ``ocr_status=running`` 且 ``updated_at`` 新鲜。没有心跳时，
    单个大文件跑过阈值就会被误判为"僵尸 running" → 评标另起 inline OCR → 双跑正反馈。
    ``WHERE ocr_status='running'`` 是硬约束：终态行绝不能被心跳"复活"。
    """
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as conn:
        conn.execute(
            "UPDATE tender_project_docs SET updated_at = ? "
            "WHERE project_id = ? AND tenant = ? AND ocr_status = 'running'",
            (utc_now(), project_id, tenant),
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
            "UPDATE tender_project_docs SET criteria = ?, criteria_status = 'ready', updated_at = ? "
            "WHERE project_id = ? AND tenant = ?",
            (criteria_json, utc_now(), project_id, tenant),
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
            (criteria_json, tender_info_json, status, utc_now(), project_id, tenant),
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
    case_path: str | None = None,
) -> None:
    """Insert or replace a bid document record.

    Args:
        project_id: Parent tender project identifier.
        bid_id: Unique bid document identifier (composite PK with project_id).
        tenant: Tenant scope for isolation.
        bidder_name: Bidder display name.
        bid_files: JSON-encoded list of uploaded file paths/names.
        ocr_status: One of ``OCR_STATUSES``.
        ocr_text: Full OCR text blob (None until OCR completes).
        extracted: JSON-encoded extracted fields (None until evaluation).
        case_path: 上传落盘目录（H3 KD2：评标入口据此重跑预热 OCR）。
    """
    _validate_ocr_status(ocr_status)
    now = utc_now()
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
                 ocr_text, ocr_status, extracted, case_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id, bid_id, tenant, bidder_name, bid_files,
                ocr_text, ocr_status, extracted, case_path, created_at, now,
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
    failed_files: Sequence[str] | None = None,
) -> None:
    """Update OCR result fields for a bid doc after background OCR completes.

    Args:
        project_id: Parent tender project identifier.
        bid_id: Bid document identifier.
        tenant: Tenant scope — WHERE clause includes tenant to prevent cross-tenant writes.
        ocr_text: Full text extracted by OCR (None on failure).
        status: New ocr_status；须属 ``OCR_STATUSES``，未知值抛 ValueError。
        failed_files: partial/degraded 时的失败文件名清单（H3 KD2）。

    Raises:
        ValueError: status 不在 ``OCR_STATUSES`` 内。
    """
    _validate_ocr_status(status)
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as conn:
        conn.execute(
            """
            UPDATE tender_bid_docs
            SET ocr_text = ?, ocr_status = ?, ocr_failed_files = ?, updated_at = ?
            WHERE project_id = ? AND bid_id = ? AND tenant = ?
            """,
            (
                ocr_text,
                status,
                _encode_failed_files(failed_files),
                utc_now(),
                project_id,
                bid_id,
                tenant,
            ),
        )


def touch_bid_doc_ocr(project_id: str, bid_id: str, *, tenant: str) -> None:
    """预热心跳：刷新仍在 ``running`` 的投标层行的 ``updated_at``（H3 KD5，理由见
    :func:`touch_project_doc_ocr`）。"""
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as conn:
        conn.execute(
            "UPDATE tender_bid_docs SET updated_at = ? "
            "WHERE project_id = ? AND bid_id = ? AND tenant = ? AND ocr_status = 'running'",
            (utc_now(), project_id, bid_id, tenant),
        )


def backfill_bid_doc_bidder_name(
    project_id: str, bid_id: str, tenant: str, bidder_name: str | None
) -> None:
    """只填空回填投标单位名称（X2：手填优先，任何情况下不覆盖非空手填）。

    评标 completed 后，若 agent 从结论 ``extracted_data.bidder_info.bidder_name`` 识别到
    投标单位名称，调本函数尝试回填 ``tender_bid_docs.bidder_name``。三键 WHERE
    （project_id + bid_id + tenant）对齐 :class:`update_bid_doc_extracted` 既有跨租户隔离
    纪律；且仅当现有 ``bidder_name`` 为空（NULL 或空串）才写入，写入同时打
    ``bidder_name_source='agent_extracted'`` 标记（手填=NULL，永不覆盖）。

    Args:
        project_id: Parent tender project identifier.
        bid_id: Bid document identifier.
        tenant: Tenant scope — WHERE clause includes tenant to prevent cross-tenant writes.
        bidder_name: Agent 识别到的投标单位名称；None/空串时不做任何写入（不编造）。
    """
    if not bidder_name:
        return
    with connect_sqlite(PLATFORM_DB_FILE, immediate=True) as conn:
        conn.execute(
            """
            UPDATE tender_bid_docs
            SET bidder_name = ?, bidder_name_source = 'agent_extracted', updated_at = ?
            WHERE project_id = ? AND bid_id = ? AND tenant = ?
                AND (bidder_name IS NULL OR bidder_name = '')
            """,
            (bidder_name, utc_now(), project_id, bid_id, tenant),
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
            (extracted_json, utc_now(), project_id, bid_id, tenant),
        )
