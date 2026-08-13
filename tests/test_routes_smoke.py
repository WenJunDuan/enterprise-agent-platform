"""Smoke test: verify that the route table after the routes/ split is identical
to the baseline captured before the refactor.

This acts as a permanent regression lock — if any route is accidentally dropped,
renamed, or method-changed during future maintenance, this test will catch it.
"""

from __future__ import annotations

# ── baseline captured 2026-06-12 before refactor ──────────────────────────────
# Command (FastAPI ≥ 0.137, 与下方断言同一套收集口径): uv run python -c
#   "from fastapi.routing import iter_route_contexts; from server.api import app;
#    print(sorted((c.path, tuple(sorted(c.methods)))
#    for c in iter_route_contexts(app.routes) if c.methods))"
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
    # D9 页级流式 OCR（2026-07-20 新增：任务化提交 + 轮询 partial results）
    ("/ocr/jobs", ("POST",)),
    ("/ocr/jobs/{request_id}", ("GET",)),
    ("/openapi.json", ("GET", "HEAD")),
    ("/redoc", ("GET", "HEAD")),
    # tender 评标路由（2026-06-19 T2 新增；2026-06-20 补 list/retry/delete + 招标项目资源 + Phase2 compare）
    ("/tender/evaluate", ("POST",)),
    ("/tender/projects", ("GET",)),
    ("/tender/projects", ("POST",)),
    ("/tender/projects/{project_id}", ("DELETE",)),
    ("/tender/projects/{project_id}", ("GET",)),
    # P2 上传即 OCR 解耦（2026-06-21 新增：tender-doc / bids / docs-status）
    ("/tender/projects/{project_id}/bids", ("POST",)),
    ("/tender/projects/{project_id}/compare", ("GET",)),
    ("/tender/projects/{project_id}/compare", ("POST",)),
    ("/tender/projects/{project_id}/docs-status", ("GET",)),
    ("/tender/projects/{project_id}/evaluate", ("POST",)),
    ("/tender/projects/{project_id}/results", ("GET",)),
    ("/tender/projects/{project_id}/results/{request_id}", ("GET",)),
    # R1 招标信息抽取（2026-06-22 新增：GET 读招标层 OCR+criteria+tender_info）
    ("/tender/projects/{project_id}/tender-doc", ("GET",)),
    ("/tender/projects/{project_id}/tender-doc", ("POST",)),
    ("/tender/tasks", ("GET",)),
    ("/tender/tasks/{request_id}", ("DELETE",)),
    ("/tender/tasks/{request_id}", ("GET",)),
    ("/tender/tasks/{request_id}/result", ("GET",)),
    ("/tender/tasks/{request_id}/retry", ("POST",)),
]


# SPA 兜底路由依赖环境：仅当 agent-front/dist 构建产物存在时才注册（见 server/api.py
# `_ui_dist_dir`），开发机有 dist、CI/worktree 没有，故不纳入基线比对。
_ENV_DEPENDENT_PATHS = {"/{spa_path:path}"}


def test_route_table_matches_baseline():
    """(path, methods) set after routes/ split must be identical to the baseline."""
    from fastapi.routing import iter_route_contexts  # noqa: PLC0415

    from server.api import app  # noqa: PLC0415

    # FastAPI 0.137+ 的 include_router 不再把子路由摊平进 app.routes, 而是留
    # `_IncludedRouter` 包装节点(前缀在匹配时才合成)。iter_route_contexts 是官方
    # 的展平入口, 产出带完整 path/methods 的 RouteContext, 同时覆盖 app 自身的
    # /docs、/openapi.json 等 starlette 原生路由。
    actual = sorted(
        (context.path, tuple(sorted(context.methods)))
        for context in iter_route_contexts(app.routes)
        if context.methods and context.path not in _ENV_DEPENDENT_PATHS
    )
    assert actual == _BASELINE_ROUTES, (
        f"Route table diverged from baseline.\n"
        f"Expected: {_BASELINE_ROUTES}\n"
        f"  Actual: {actual}"
    )
