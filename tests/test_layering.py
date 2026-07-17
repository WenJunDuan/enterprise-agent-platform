"""Architectural fitness tests: enforce one-directional layering under server/.

These scan import statements at the text level to stop layering regressions as
the package grows. Target layering + rationale:
``.ai_state/sprints/2026-06-18-server-layering/design.md``;
ocr's demotion to a service layer: ``.ai_state/sprints/2026-07-02-eval-tender-scaffold/design.md``
Round 2 决议 + ``compound/2026-07-15-decision-ocr-service-layer.md``.

Layers (a module may only import from a strictly lower layer):

    app (api/app_server/cli) → routes → ops → features(audit|tender) → ocr → core → common → stores → platform

``ops`` (diagnostics/maintenance) is a *service* layer consumed by both app and
routes; it depends only on core/stores/platform and never imports routes/app —
hence it sits BELOW routes (2026-06-19 T2.5 correction; the earlier docstring
mis-ordered ops above routes, which falsely flagged the legal health→ops import).
``core`` is the facade re-exporting common/*; importing it downward from
routes/ops is fine, but common/ must not import core (cycle).

Business feature domains (audit, tender) are siblings and must never import each
other. ``ocr`` is **not** a sibling — 2026-07-15 方案 i 拍板它降为a service layer
sitting just below audit/tender (audit_worker / tender_worker /
tender_doc_pipeline all consume it as a service). The guard is therefore
**unidirectional**: audit/tender → ocr is legal; ocr → audit/tender is forbidden
(a service layer must never depend back on its consumers).
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
    nothing in common/ should import server.audit / server.tender / server.ocr /
    routes / ops / api. (d) 方案 i 守卫：新建 server.tender/ 同样禁止被 common/ 反向依赖。
    """
    # server.core is the facade that re-exports common/* — importing it from within
    # common/ creates a core↔common cycle; import the source module directly instead.
    forbidden = (
        "server.audit",
        "server.tender",
        "server.ocr",
        "server.routes",
        "server.ops",
        "server.api",
        "server.core",
    )
    offenders = [(f, mod) for f, mod in _server_imports("common") if mod.startswith(forbidden)]
    assert not offenders, f"common/ imports a feature/upper layer: {offenders}"


def test_feature_domains_do_not_import_each_other():
    """(a) 方案 i 守卫：tender↔audit 互斥——两个业务 feature 域互不 import。

    ocr 不在本对称集合内：见 test_ocr_does_not_import_tender_or_audit（守卫改单向）。
    """
    audit_to_tender = [
        (f, mod) for f, mod in _server_imports("audit") if mod.startswith("server.tender")
    ]
    tender_to_audit = [
        (f, mod) for f, mod in _server_imports("tender") if mod.startswith("server.audit")
    ]
    assert not audit_to_tender, f"audit/ imports tender/: {audit_to_tender}"
    assert not tender_to_audit, f"tender/ imports audit/: {tender_to_audit}"


def test_features_do_not_import_routes_ops_or_app():
    """(e) D2 守卫：feature 域(audit/tender)不得向上 import routes/ops/api。

    这正是 D2 把 tender_worker/compare_worker/doc_pipeline 从 routes/ 迁进
    server/tender/ 的意义——worker 归位 feature 层后只依赖下层
    (common/ocr/core/stores/platform),绝不反向 import 回 routes(否则 features→routes
    上行边,破坏单向分层)。既有守卫只锁"下层不 import features",本条补"features 不上行"。
    """
    forbidden = ("server.routes", "server.ops", "server.api")
    offenders = [
        (f, mod)
        for pkg in ("audit", "tender")
        for f, mod in _server_imports(pkg)
        if mod.startswith(forbidden)
    ]
    assert not offenders, f"feature 域 import 了 routes/ops/api 上行层: {offenders}"


def test_ocr_does_not_import_tender_or_audit():
    """(b) 方案 i 守卫（单向，2026-07-15 拍板）：ocr 降为 audit/tender 之下的服务层——
    audit/tender → ocr 合法（audit_worker / tender_worker / tender_doc_pipeline 三处已按
    服务消费，server/tender/runner.py 的 ocr_preprocess_block 调用同理合法），但反向
    ocr → audit/tender 禁止（服务层不得依赖回它的消费者）。

    既有 audit↔ocr 互斥断言（round1 教义）已被本条单向断言取代——`audit/ imports ocr/`
    不再是 offender。
    """
    ocr_to_audit = [(f, mod) for f, mod in _server_imports("ocr") if mod.startswith("server.audit")]
    ocr_to_tender = [
        (f, mod) for f, mod in _server_imports("ocr") if mod.startswith("server.tender")
    ]
    assert not ocr_to_audit, f"ocr/ imports audit/ (service layer must not depend on consumer): {ocr_to_audit}"
    assert not ocr_to_tender, f"ocr/ imports tender/ (service layer must not depend on consumer): {ocr_to_tender}"


def test_ops_does_not_import_routes_app_or_features():
    """ops/ is a service layer BELOW routes — it may use core/stores/platform but
    must never import routes, the app module, or feature domains. This is what lets
    routes (e.g. health) legally depend on ops without creating a cycle.

    (c) 方案 i 守卫：forbidden 加 server.tender（新建 feature 域同样禁止被 ops/ 反向依赖）。
    """
    forbidden = ("server.routes", "server.api", "server.audit", "server.tender", "server.ocr")
    offenders = [(f, mod) for f, mod in _server_imports("ops") if mod.startswith(forbidden)]
    assert not offenders, f"ops/ imports routes/app/feature (must stay below routes): {offenders}"


def test_stores_only_import_platform():
    """stores/ sit just above platform — they may only import platform (and sibling
    stores). Importing common/core/ops/routes/api/features would invert the layering
    (common/ is already allowed to import stores, so stores→common would be a cycle).

    (d) 方案 i 守卫：forbidden 加 server.tender。
    """
    forbidden = (
        "server.routes",
        "server.api",
        "server.ops",
        "server.audit",
        "server.tender",
        "server.ocr",
        "server.common",
        "server.core",
    )
    offenders = [(f, mod) for f, mod in _server_imports("stores") if mod.startswith(forbidden)]
    assert not offenders, f"stores/ imports an upper layer (only platform allowed): {offenders}"
