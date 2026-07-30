"""Canonical supported-document format manifest loader."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Final

PROJECT_ROOT: Final = Path(__file__).resolve().parents[2]
FORMAT_MANIFEST_PATH: Final = PROJECT_ROOT / "shared" / "supported-document-formats.json"
REQUIRED_GROUPS: Final = frozenset(
    {
        "text",
        "images",
        "word_native",
        "word_legacy",
        "excel_ooxml",
        "excel_xls",
        "excel_xlsb",
        "presentation_native",
        "office_convert",
        "pdf",
    }
)


def load_format_manifest(path: Path = FORMAT_MANIFEST_PATH) -> dict[str, object]:
    """Load and strictly validate the single format manifest."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot load document format manifest: {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise RuntimeError("document format manifest version must be integer 1")
    groups = payload.get("groups")
    if not isinstance(groups, dict):
        raise RuntimeError("document format manifest groups must be an object")
    missing = REQUIRED_GROUPS - groups.keys()
    extra = groups.keys() - REQUIRED_GROUPS
    if missing:
        raise RuntimeError(f"document format manifest missing groups: {sorted(missing)}")
    if extra:
        raise RuntimeError(f"document format manifest has unknown groups: {sorted(extra)}")
    seen: set[str] = set()
    normalized: dict[str, tuple[str, ...]] = {}
    for name in sorted(REQUIRED_GROUPS):
        values = groups[name]
        if not isinstance(values, list) or not values:
            raise RuntimeError(f"document format group {name} must be a non-empty array")
        if any(
            not isinstance(value, str)
            or not value.startswith(".")
            or value != value.lower()
            or value.strip() != value
            for value in values
        ):
            raise RuntimeError(f"document format group {name} contains an invalid suffix")
        duplicates = seen.intersection(values)
        if duplicates:
            raise RuntimeError(f"document format suffix appears in multiple groups: {sorted(duplicates)}")
        if len(values) != len(set(values)):
            raise RuntimeError(f"document format group {name} contains duplicate suffixes")
        seen.update(values)
        normalized[name] = tuple(values)
    return {"version": 1, "groups": MappingProxyType(normalized)}


FORMAT_MANIFEST = load_format_manifest()
FORMAT_GROUPS = FORMAT_MANIFEST["groups"]


def suffixes(group: str) -> frozenset[str]:
    """Return a validated group as an immutable suffix set."""
    return frozenset(FORMAT_GROUPS[group])


ALL_SUPPORTED_SUFFIXES = frozenset().union(*(suffixes(group) for group in REQUIRED_GROUPS))
