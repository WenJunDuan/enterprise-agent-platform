"""Architectural fitness tests: enforce one-directional layering under server/.

These scan import statements at the text level to stop layering regressions as
the package grows. Target layering + rationale:
``.ai_state/sprints/2026-06-18-server-layering/design.md``.

Layers (a module may only import from a strictly lower layer):

    app (api/app_server/cli) → routes → ops → features(audit|ocr) → core → common → stores → platform

``ops`` (diagnostics/maintenance) is a *service* layer consumed by both app and
routes; it depends only on core/stores/platform and never imports routes/app —
hence it sits BELOW routes (2026-06-19 T2.5 correction; the earlier docstring
mis-ordered ops above routes, which falsely flagged the legal health→ops import).
``core`` is the facade re-exporting common/*; importing it downward from
routes/ops is fine, but common/ must not import core (cycle).

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


def test_platform_is_a_leaf_layer():
    """platform/ is the foundation — it must not import from any higher layer.

    Cross-store orchestration (diagnostics, maintenance) lives in server.ops.
    """
    forbidden = ("server.stores", "server.ops", "server.routes", "server.api", "server.core")
    offenders = [
        (f, mod) for f, mod in _server_imports("platform") if mod.startswith(forbidden)
    ]
    assert not offenders, f"platform/ imports a higher layer (must stay a leaf): {offenders}"


def test_common_does_not_import_feature_or_upper_layers():
    """common/ is shared scaffolding — it must not depend on feature domains or above.

    Contract conformance (server.common.contract) is shared, not audit-owned, so
    nothing in common/ should import server.audit / server.ocr / routes / ops / api.
    """
    # server.core is the facade that re-exports common/* — importing it from within
    # common/ creates a core↔common cycle; import the source module directly instead.
    forbidden = (
        "server.audit",
        "server.ocr",
        "server.routes",
        "server.ops",
        "server.api",
        "server.core",
    )
    offenders = [(f, mod) for f, mod in _server_imports("common") if mod.startswith(forbidden)]
    assert not offenders, f"common/ imports a feature/upper layer: {offenders}"


def test_feature_domains_do_not_import_each_other():
    """Feature domains are siblings and must never import one another."""
    audit_to_ocr = [(f, mod) for f, mod in _server_imports("audit") if mod.startswith("server.ocr")]
    ocr_to_audit = [(f, mod) for f, mod in _server_imports("ocr") if mod.startswith("server.audit")]
    assert not audit_to_ocr, f"audit/ imports ocr/: {audit_to_ocr}"
    assert not ocr_to_audit, f"ocr/ imports audit/: {ocr_to_audit}"


def test_ops_does_not_import_routes_app_or_features():
    """ops/ is a service layer BELOW routes — it may use core/stores/platform but
    must never import routes, the app module, or feature domains. This is what lets
    routes (e.g. health) legally depend on ops without creating a cycle.
    """
    forbidden = ("server.routes", "server.api", "server.audit", "server.ocr")
    offenders = [(f, mod) for f, mod in _server_imports("ops") if mod.startswith(forbidden)]
    assert not offenders, f"ops/ imports routes/app/feature (must stay below routes): {offenders}"


def test_stores_only_import_platform():
    """stores/ sit just above platform — they may only import platform (and sibling
    stores). Importing common/core/ops/routes/api/features would invert the layering
    (common/ is already allowed to import stores, so stores→common would be a cycle).
    """
    forbidden = (
        "server.routes",
        "server.api",
        "server.ops",
        "server.audit",
        "server.ocr",
        "server.common",
        "server.core",
    )
    offenders = [(f, mod) for f, mod in _server_imports("stores") if mod.startswith(forbidden)]
    assert not offenders, f"stores/ imports an upper layer (only platform allowed): {offenders}"
