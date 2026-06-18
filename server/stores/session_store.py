"""Application-level session index and transcript helpers.

Facade module: re-exports all public names from the split sub-modules so that
existing importers (server/, tests/) need no changes.

Sub-modules:
  session_records    — SessionRecord dataclass, SessionStore protocol, utc_now / new_* helpers
  session_sqlite_store — SQLiteSessionStore (the session index in platform.sqlite3)
  session_queries    — SESSION_STORE singleton + module-level delegating functions
  session_sdk        — SDK transcript / summary helpers
"""

from __future__ import annotations

from server.platform.paths import ensure_local_layout

ensure_local_layout()

# ── dataclass, protocol, primitives ──────────────────────────────────────────
from server.stores.session_records import (  # noqa: E402
    SessionRecord,
    SessionStore,
    _month_key,
    new_conversation_id,
    new_request_id,
    utc_now,
)

# ── store implementation ──────────────────────────────────────────────────────
from server.stores.session_sqlite_store import SQLiteSessionStore  # noqa: E402

# ── singleton + delegating query functions ────────────────────────────────────
from server.stores.session_queries import (  # noqa: E402
    SESSION_STORE,
    append_session_record,
    describe_session_store,
    get_session_record_by_request_id,
    get_session_record_by_request_id_admin,
    get_session_record_by_session_id,
    get_session_record_by_session_id_admin,
    list_conversation_summaries,
    list_conversation_summaries_admin,
    list_known_session_ids,
    list_known_session_ids_admin,
    list_logged_sessions,
    list_logged_sessions_admin,
    load_session_records,
    resolve_latest_session_id,
    resolve_latest_session_id_admin,
)

# ── SDK helpers ───────────────────────────────────────────────────────────────
from server.stores.session_sdk import (  # noqa: E402
    get_sdk_session_transcript,
    list_sdk_session_summaries,
)

__all__ = [
    # records / protocol
    "SessionRecord",
    "SessionStore",
    "_month_key",
    "new_request_id",
    "new_conversation_id",
    "utc_now",
    # store implementation
    "SQLiteSessionStore",
    # singleton
    "SESSION_STORE",
    # delegating query functions
    "append_session_record",
    "load_session_records",
    "get_session_record_by_request_id",
    "get_session_record_by_session_id",
    "resolve_latest_session_id",
    "list_logged_sessions",
    "list_conversation_summaries",
    "list_known_session_ids",
    "get_session_record_by_request_id_admin",
    "get_session_record_by_session_id_admin",
    "resolve_latest_session_id_admin",
    "list_logged_sessions_admin",
    "list_conversation_summaries_admin",
    "list_known_session_ids_admin",
    "describe_session_store",
    # SDK helpers
    "list_sdk_session_summaries",
    "get_sdk_session_transcript",
]
