"""SDK-backed session transcript and summary helpers."""

from __future__ import annotations

from typing import Any

from claude_agent_sdk import get_session_messages, list_sessions

from server.platform.paths import PROJECT_ROOT


def list_sdk_session_summaries(
    limit: int = 20,
    session_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    probe_limit = max(limit * 10, 100) if session_ids is not None else limit
    sessions = list_sessions(directory=str(PROJECT_ROOT), limit=probe_limit, include_worktrees=True)
    summaries = [
        {
            "session_id": session.session_id,
            "summary": session.summary,
            "created_at": session.created_at,
            "last_modified": session.last_modified,
            "cwd": session.cwd,
            "git_branch": session.git_branch,
        }
        for session in sessions
        if session_ids is None or session.session_id in session_ids
    ]
    return summaries[:limit]


def get_sdk_session_transcript(
    session_id: str,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    messages = get_session_messages(
        session_id=session_id,
        directory=str(PROJECT_ROOT),
        limit=limit,
        offset=offset,
    )
    return [
        {
            "type": message.type,
            "uuid": message.uuid,
            "session_id": message.session_id,
            "message": message.message,
        }
        for message in messages
    ]
