"""Architectural fitness tests: enforce one-directional layering under server/.

These scan import statements at the text level to stop layering regressions as
the package grows. Target layering + rationale:
``.ai_state/sprints/2026-06-18-server-layering/design.md``.

Layers (a module may only import from a strictly lower layer):

    app (api/app_server/cli) → ops → routes → features(audit|ocr) → common → stores → platform

Feature domains (audit, ocr, …) are siblings and must never import each other.
"""

from __future__ import annotations

import re
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent / "server"
_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+(server\.[\w.]+)", re.MULTILINE)


def _server_imports(pkg_rel: str) -> list[tuple[str, str]]:
    """Yield (relative_file, imported_module) for every ``server.*`` import under server/<pkg_rel>."""
    base = SERVER_DIR / pkg_rel
    hits: list[tuple[str, str]] = []
    for path in base.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in _IMPORT_RE.finditer(text):
            hits.append((str(path.relative_to(SERVER_DIR)), match.group(1)))
    return hits


def test_routes_do_not_import_app_module():
    """routes/ must not import server.api — that recreates the api↔routes cycle.

    Shared dependencies (e.g. verify_tenant) belong in server.routes.deps.
    """
    offenders = [(f, mod) for f, mod in _server_imports("routes") if mod.startswith("server.api")]
    assert not offenders, (
        "routes/ imports server.api (use server.routes.deps for shared deps): " f"{offenders}"
    )
