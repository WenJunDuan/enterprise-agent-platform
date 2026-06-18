"""Smoke test: verify that the route table after the routes/ split is identical
to the baseline captured before the refactor.

This acts as a permanent regression lock — if any route is accidentally dropped,
renamed, or method-changed during future maintenance, this test will catch it.
"""

from __future__ import annotations

# ── baseline captured 2026-06-12 before refactor ──────────────────────────────
# Command: uv run python -c
#   "from server.api import app;
#    print(sorted((r.path, tuple(sorted(r.methods)))
#    for r in app.routes if hasattr(r,'methods')))"
_BASELINE_ROUTES: list[tuple[str, tuple[str, ...]]] = [
    ("/audit/submit", ("POST",)),
    ("/audit/tasks", ("GET",)),
    ("/audit/tasks/{request_id}", ("DELETE",)),
    ("/audit/tasks/{request_id}", ("GET",)),
    ("/audit/tasks/{request_id}/result", ("GET",)),
    ("/audit/tasks/{request_id}/retry", ("POST",)),
    ("/docs", ("GET", "HEAD")),
    ("/docs/oauth2-redirect", ("GET", "HEAD")),
    ("/health", ("GET",)),
    ("/ocr/extract", ("POST",)),
    ("/ocr/fill", ("POST",)),
    ("/openapi.json", ("GET", "HEAD")),
    ("/redoc", ("GET", "HEAD")),
]


# SPA 兜底路由依赖环境：仅当 agent-front/dist 构建产物存在时才注册（见 server/api.py
# `_ui_dist_dir`），开发机有 dist、CI/worktree 没有，故不纳入基线比对。
_ENV_DEPENDENT_PATHS = {"/{spa_path:path}"}


def test_route_table_matches_baseline():
    """(path, methods) set after routes/ split must be identical to the baseline."""
    from server.api import app  # noqa: PLC0415

    actual = sorted(
        (r.path, tuple(sorted(r.methods)))
        for r in app.routes
        if hasattr(r, "methods") and r.path not in _ENV_DEPENDENT_PATHS
    )
    assert actual == _BASELINE_ROUTES, (
        f"Route table diverged from baseline.\n"
        f"Expected: {_BASELINE_ROUTES}\n"
        f"  Actual: {actual}"
    )
