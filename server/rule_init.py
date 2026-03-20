"""Rule initialization helpers for the CLI-only /init workflow."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import json
from pathlib import Path
import re
from typing import Iterable, Sequence

from server.config import load_memory_settings


ADVANCED_SOURCE_SUFFIXES = {
    ".pdf",
    ".doc",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
}
TEXT_SOURCE_SUFFIXES = {".txt", ".md"}
DOMAIN_CATEGORIES = {
    "expense": ("travel", "entertainment", "invoice", "general", "transport", "loan"),
    "hr": ("leave", "attendance"),
    "legal": ("general",),
}
GENERATED_EXTERNAL_MARKDOWN_SUFFIXES = (
    ".structured.md",
    ".extracted.md",
    ".vector.md",
    ".vectors.md",
    ".summary.md",
)
STATIC_MEMORY_SOURCE_CANDIDATES = (
    "docs/expense-control-design.md",
    "docs/architecture-summary.md",
    "docs/bootstrap-roadmap.md",
    ".cunzhi-memory/context.md",
    ".cunzhi-memory/patterns.md",
    ".cunzhi-memory/preferences.md",
    ".cunzhi-memory/rules.md",
)
DEFAULT_KNOWLEDGE_MEMORY_ROOT = "knowledge/memory"


@dataclass(frozen=True, slots=True)
class SourceInfo:
    path: str
    kind: str
    requires_advanced_extraction: bool


@dataclass(frozen=True, slots=True)
class RuleTarget:
    category: str
    path: str
    existed: bool


@dataclass(frozen=True, slots=True)
class InitPlan:
    project_root: Path
    domain: str
    schema_path: Path
    manifest_path: Path
    report_path: Path
    external_sources: tuple[SourceInfo, ...]
    text_sources: tuple[SourceInfo, ...]
    advanced_sources: tuple[SourceInfo, ...]
    memory_sources: tuple[str, ...]
    rule_targets: tuple[RuleTarget, ...]
    status: str
    warnings: tuple[str, ...]


def build_init_plan(
    project_root: Path, *, domain: str = "expense", explicit_sources: Sequence[str] | None = None
) -> InitPlan:
    knowledge_root = project_root / "knowledge"
    external_root = knowledge_root / "external"
    domain_root = knowledge_root / domain
    schema_path = knowledge_root / "_schema" / "rule.schema.json"
    manifest_path = domain_root / "init-manifest.json"
    report_path = domain_root / "init-report.md"

    external_sources = tuple(
        _describe_source(path, project_root) for path in _resolve_source_paths(project_root, explicit_sources)
    )
    text_sources = tuple(source for source in external_sources if not source.requires_advanced_extraction)
    advanced_sources = tuple(source for source in external_sources if source.requires_advanced_extraction)
    memory_sources = tuple(_discover_memory_sources(project_root))
    rule_targets = tuple(_build_rule_targets(project_root, domain))

    warnings: list[str] = []
    if not external_sources:
        warnings.append(f"No external policy documents found under {_rel_path(external_root, project_root)}.")
    if advanced_sources:
        warnings.append(
            "Detected source files that likely need OCR/vector support. Please confirm before enabling advanced extraction."
        )
    if not memory_sources:
        warnings.append(
            "No project memory sources were found under knowledge/memory/ or legacy paths; /init will bootstrap only the rule scaffold."
        )

    status = _resolve_plan_status(
        has_sources=bool(external_sources),
        has_text_sources=bool(text_sources),
        has_advanced_sources=bool(advanced_sources),
    )

    return InitPlan(
        project_root=project_root,
        domain=domain,
        schema_path=schema_path,
        manifest_path=manifest_path,
        report_path=report_path,
        external_sources=external_sources,
        text_sources=text_sources,
        advanced_sources=advanced_sources,
        memory_sources=memory_sources,
        rule_targets=rule_targets,
        status=status,
        warnings=tuple(warnings),
    )


def initialize_rules(
    project_root: Path, *, domain: str = "expense", explicit_sources: Sequence[str] | None = None
) -> InitPlan:
    plan = build_init_plan(project_root, domain=domain, explicit_sources=explicit_sources)

    plan.schema_path.parent.mkdir(parents=True, exist_ok=True)
    plan.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if not plan.schema_path.exists():
        _write_json(plan.schema_path, _rule_schema_template())

    extracted_by_category = _extract_text_rules(plan)
    for target in plan.rule_targets:
        target_path = plan.project_root / target.path
        extracted_rules = extracted_by_category.get(target.category, [])
        if target.existed:
            if not extracted_rules:
                continue
            existing_pack = json.loads(target_path.read_text(encoding="utf-8"))
            merged_pack = _merge_rule_pack(existing_pack, extracted_rules)
            _write_json(target_path, merged_pack)
            continue

        rule_pack = _empty_rule_pack(plan.domain, target.category)
        if extracted_rules:
            rule_pack["rules"] = extracted_rules
        _write_json(target_path, rule_pack)

    _write_json(plan.manifest_path, _manifest_payload(plan))
    plan.report_path.write_text(_render_report(plan), encoding="utf-8")
    return plan


def _resolve_plan_status(
    *, has_sources: bool, has_text_sources: bool, has_advanced_sources: bool
) -> str:
    if has_advanced_sources:
        return "awaiting_advanced_extraction_confirmation"
    if has_text_sources:
        return "ready_for_text_bootstrap"
    if has_sources:
        return "source_documents_detected"
    return "pending_source_documents"


def _resolve_source_paths(project_root: Path, explicit_sources: Sequence[str] | None) -> list[Path]:
    external_root = project_root / "knowledge" / "external"
    if not explicit_sources:
        if not external_root.exists():
            return []
        return sorted(path for path in external_root.rglob("*") if _is_bootstrap_source_document(path))

    resolved_paths: list[Path] = []
    for source in explicit_sources:
        candidate = Path(source)
        path = candidate if candidate.is_absolute() else (project_root / candidate)
        path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(f"Source document not found: {source}")
        try:
            path.relative_to(external_root.resolve())
        except ValueError as exc:
            raise ValueError("Source documents must be placed under knowledge/external.") from exc
        if path.is_file():
            resolved_paths.append(path)
    return sorted(resolved_paths)


def _describe_source(path: Path, project_root: Path) -> SourceInfo:
    suffix = path.suffix.lower()
    if suffix in TEXT_SOURCE_SUFFIXES:
        requires_advanced = False
        kind = "text"
    else:
        requires_advanced = True
        kind = "advanced"
    return SourceInfo(
        path=_rel_path(path, project_root),
        kind=kind,
        requires_advanced_extraction=requires_advanced,
    )


def _discover_memory_sources(project_root: Path) -> Iterable[str]:
    memory_root = _resolve_memory_root(project_root)
    if memory_root.exists():
        for path in sorted(
            candidate
            for candidate in memory_root.rglob("*.md")
            if candidate.is_file() and _is_daily_memory_file(candidate, memory_root)
        ):
            yield _display_path(path, project_root)

    for relative_path in STATIC_MEMORY_SOURCE_CANDIDATES:
        path = project_root / relative_path
        if path.is_file():
            yield relative_path


def _build_rule_targets(project_root: Path, domain: str) -> Iterable[RuleTarget]:
    domain_root = project_root / "knowledge" / domain
    categories = DOMAIN_CATEGORIES.get(domain, ("general",))
    for category in categories:
        path = domain_root / f"{category}.rules.json"
        yield RuleTarget(
            category=category,
            path=_rel_path(path, project_root),
            existed=path.exists(),
        )


def _resolve_memory_root(project_root: Path) -> Path:
    configured_root = load_memory_settings(project_root / ".env").root_dir
    if configured_root == Path(DEFAULT_KNOWLEDGE_MEMORY_ROOT):
        return project_root / configured_root
    return configured_root if configured_root.is_absolute() else project_root / configured_root


def _is_daily_memory_file(path: Path, memory_root: Path) -> bool:
    if path.name.lower() == "readme.md":
        return False

    relative_parts = path.relative_to(memory_root).parts
    if len(relative_parts) != 3:
        return False

    year, month, filename = relative_parts
    if not (year.isdigit() and len(year) == 4 and month.isdigit() and len(month) == 2):
        return False

    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", filename))


def _empty_rule_pack(domain: str, category: str) -> dict:
    return {
        "domain": domain,
        "category": category,
        "version": "draft",
        "effective_date": date.today().isoformat(),
        "rules": [],
    }


def _rule_schema_template() -> dict:
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["domain", "category", "version", "effective_date", "rules"],
        "properties": {
            "domain": {"type": "string", "enum": ["expense", "hr", "legal"]},
            "category": {"type": "string", "description": "Rule category such as travel or entertainment."},
            "version": {"type": "string"},
            "effective_date": {"type": "string", "format": "date"},
            "rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["rule_id", "description", "conditions", "action"],
                    "properties": {
                        "rule_id": {"type": "string"},
                        "description": {"type": "string"},
                        "conditions": {"type": "object"},
                        "action": {"type": "string", "enum": ["approve", "reject", "escalate"]},
                        "priority": {"type": "integer"},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "original_text": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                },
            },
        },
    }


def _extract_text_rules(plan: InitPlan) -> dict[str, list[dict]]:
    if not plan.text_sources:
        return {}

    extracted_by_category: dict[str, list[dict]] = {target.category: [] for target in plan.rule_targets}
    counters: dict[str, int] = {target.category: 1 for target in plan.rule_targets}

    for source in plan.text_sources:
        source_path = plan.project_root / source.path
        category = _infer_category(plan.domain, source_path)
        for line in _iter_rule_candidates(source_path.read_text(encoding="utf-8", errors="ignore")):
            rule_id = f"{plan.domain}.{category}.{counters[category]:03d}"
            counters[category] += 1
            extracted_by_category[category].append(
                {
                    "rule_id": rule_id,
                    "description": line,
                    "conditions": _infer_conditions(line),
                    "action": "escalate",
                    "priority": 100,
                    "confidence": "low",
                    "original_text": line,
                    "notes": f"Bootstrapped from {source.path}. Manual review required before production use.",
                }
            )

    return {category: rules for category, rules in extracted_by_category.items() if rules}


def _infer_category(domain: str, source_path: Path) -> str:
    stem = source_path.stem.lower()
    if domain == "expense":
        if any(token in stem for token in ("travel", "trip")) or "差旅" in source_path.stem:
            return "travel"
        if any(token in stem for token in ("entertainment", "hospitality")) or "招待" in source_path.stem:
            return "entertainment"
        if "invoice" in stem or "发票" in source_path.stem:
            return "invoice"
        if any(token in stem for token in ("transport", "traffic", "commute")) or "交通" in source_path.stem:
            return "transport"
        if "loan" in stem or "借款" in source_path.stem:
            return "loan"
        return "general"
    if domain == "hr":
        if any(token in stem for token in ("attendance", "overtime")) or any(
            keyword in source_path.stem for keyword in ("考勤", "加班")
        ):
            return "attendance"
        if any(token in stem for token in ("leave", "vacation")) or any(
            keyword in source_path.stem for keyword in ("请假", "休假", "病假", "事假", "婚假")
        ):
            return "leave"
        return "leave"
    return _default_category_for_domain(domain)


def _iter_rule_candidates(text: str) -> Iterable[str]:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[\-\*\u2022\d\.\)\(、\s]+", "", line).strip()
        if len(line) < 8:
            continue
        if not any(keyword in line for keyword in ("不得", "不允许", "必须", "需", "应", "报销", "审批", "发票")):
            continue
        yield line


def _infer_conditions(line: str) -> dict:
    conditions: dict[str, object] = {}
    amount_match = re.search(r"(?:不超过|上限为|上限)(\d+(?:\.\d+)?)\s*元", line)
    if amount_match:
        conditions["max_amount"] = float(amount_match.group(1))
    required_docs = [doc for doc in ("发票", "行程单", "申请单", "审批单") if doc in line]
    if required_docs:
        conditions["required_docs"] = required_docs
    return conditions


def _default_category_for_domain(domain: str) -> str:
    categories = DOMAIN_CATEGORIES.get(domain, ("general",))
    return categories[0]


def _is_bootstrap_source_document(path: Path) -> bool:
    if not path.is_file():
        return False

    lower_name = path.name.lower()
    if lower_name == "readme.md":
        return False

    lower_path = str(path).lower()
    if any(lower_path.endswith(suffix) for suffix in GENERATED_EXTERNAL_MARKDOWN_SUFFIXES):
        return False

    return True


def _manifest_payload(plan: InitPlan) -> dict:
    return {
        "command": "/init",
        "domain": plan.domain,
        "status": plan.status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_path": _rel_path(plan.schema_path, plan.project_root),
        "manifest_path": _rel_path(plan.manifest_path, plan.project_root),
        "report_path": _rel_path(plan.report_path, plan.project_root),
        "external_sources": [asdict(source) for source in plan.external_sources],
        "text_sources": [asdict(source) for source in plan.text_sources],
        "advanced_sources": [asdict(source) for source in plan.advanced_sources],
        "memory_sources": list(plan.memory_sources),
        "rule_targets": [asdict(target) for target in plan.rule_targets],
        "warnings": list(plan.warnings),
    }


def _render_report(plan: InitPlan) -> str:
    lines = [
        "# Init Report",
        "",
        "- command: `/init`",
        f"- domain: `{plan.domain}`",
        f"- status: `{plan.status}`",
        f"- schema: `{_rel_path(plan.schema_path, plan.project_root)}`",
        f"- manifest: `{_rel_path(plan.manifest_path, plan.project_root)}`",
        f"- report: `{_rel_path(plan.report_path, plan.project_root)}`",
        "",
        "## Rule Targets",
    ]
    for target in plan.rule_targets:
        state = "existing" if target.existed else "created_if_missing"
        lines.append(f"- `{target.path}` ({state})")

    lines.append("")
    lines.append("## External Sources")
    if plan.external_sources:
        for source in plan.external_sources:
            suffix = "requires confirmation" if source.requires_advanced_extraction else "ready"
            lines.append(f"- `{source.path}` ({source.kind}, {suffix})")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Memory Sources")
    if plan.memory_sources:
        for source in plan.memory_sources:
            lines.append(f"- `{source}`")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Warnings")
    if plan.warnings:
        for warning in plan.warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Next Actions")
    lines.append("- Place policy source files under `knowledge/external/` if they are not ready yet.")
    lines.append(
        "- Record confirmed business cases, manual decisions, and exception handling in `knowledge/memory/YYYY/MM/YYYY-MM-DD.md` so future `/init` runs can reuse them."
    )
    lines.append("- Re-run `init` after adding text policy files to bootstrap placeholder rules.")
    lines.append("- If the source set contains PDF/DOCX/images, confirm OCR/vector support before enabling advanced extraction.")
    return "\n".join(lines) + "\n"


def _merge_rule_pack(existing_pack: dict, extracted_rules: Sequence[dict]) -> dict:
    existing_rules = list(existing_pack.get("rules", []))
    existing_texts = {
        rule.get("original_text") or rule.get("description")
        for rule in existing_rules
        if isinstance(rule, dict)
    }
    next_index = len(existing_rules) + 1

    for rule in extracted_rules:
        rule_text = rule.get("original_text") or rule.get("description")
        if rule_text in existing_texts:
            continue

        merged_rule = dict(rule)
        merged_rule["rule_id"] = _next_rule_id(
            existing_pack.get("domain", "expense"),
            existing_pack.get("category", "general"),
            next_index,
        )
        next_index += 1
        existing_rules.append(merged_rule)
        existing_texts.add(rule_text)

    merged_pack = dict(existing_pack)
    merged_pack["rules"] = existing_rules
    return merged_pack


def _next_rule_id(domain: str, category: str, index: int) -> str:
    return f"{domain}.{category}.{index:03d}"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _rel_path(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _display_path(path: Path, root: Path) -> str:
    try:
        return _rel_path(path, root)
    except ValueError:
        return str(path)
