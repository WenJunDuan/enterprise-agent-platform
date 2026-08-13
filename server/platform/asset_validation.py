"""Validation helpers for knowledge rule and memory assets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import ValidationError, validate

from server.platform.paths import PROJECT_ROOT

RULE_SCHEMA_PATH = PROJECT_ROOT / "knowledge" / "_schema" / "rule.schema.json"
MEMORY_SCHEMA_PATH = PROJECT_ROOT / "knowledge" / "_schema" / "case-memory.schema.json"
KNOWLEDGE_ROOT = PROJECT_ROOT / "knowledge"
MEMORY_ROOT = KNOWLEDGE_ROOT / "memory"


def validate_knowledge_assets() -> dict[str, Any]:
    rules_report = validate_rule_assets()
    memory_report = validate_memory_assets()
    status = (
        "ok"
        if rules_report["status"] == "ok" and memory_report["status"] == "ok"
        else "degraded"
    )
    return {
        "status": status,
        "rules": rules_report,
        "memory": memory_report,
    }


def validate_rule_assets(root: Path | None = None) -> dict[str, Any]:
    knowledge_root = root or KNOWLEDGE_ROOT
    schema_path = RULE_SCHEMA_PATH if root is None else knowledge_root / "_schema" / "rule.schema.json"
    if not schema_path.exists():
        return {
            "status": "degraded",
            "checked_files": 0,
            "errors": [f"Rule schema not found: {schema_path}"],
        }
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    checked_files = 0

    for path in sorted((knowledge_root).glob("*/*.rules.json")):
        checked_files += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            validate(payload, schema)
        except (json.JSONDecodeError, ValidationError, UnicodeDecodeError) as exc:
            errors.append(f"{path}: {exc}")
            continue

        expected_domain = path.parent.name
        expected_category = path.name.removesuffix(".rules.json")
        if payload.get("domain") != expected_domain:
            errors.append(f"{path}: domain does not match parent directory")
        if payload.get("category") != expected_category:
            errors.append(f"{path}: category does not match filename")

        for rule in payload.get("rules", []):
            rule_id = str(rule.get("rule_id") or "")
            expected_prefix = f"{expected_domain}_{expected_category}_"
            if not rule_id.startswith(expected_prefix):
                errors.append(f"{path}: rule_id {rule_id} does not match {expected_prefix}*")

    return {
        "status": "ok" if not errors else "degraded",
        "checked_files": checked_files,
        "errors": errors,
    }


def validate_memory_assets(root: Path | None = None) -> dict[str, Any]:
    knowledge_root = root or KNOWLEDGE_ROOT
    memory_root = knowledge_root / "memory"
    errors: list[str] = []
    checked_files = 0

    schema_path = MEMORY_SCHEMA_PATH if root is None else knowledge_root / "_schema" / "case-memory.schema.json"
    if not schema_path.exists():
        return {
            "status": "degraded",
            "checked_files": 0,
            "errors": [f"Memory schema not found: {schema_path}"],
        }
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    if not memory_root.exists():
        return {"status": "ok", "checked_files": 0, "errors": []}

    for path in sorted(memory_root.rglob("*.json")):
        checked_files += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            validate(payload, schema)
        except (json.JSONDecodeError, ValidationError, UnicodeDecodeError) as exc:
            errors.append(f"{path}: {exc}")
            continue

        expected_domain = path.parent.name
        if payload.get("domain") != expected_domain:
            errors.append(f"{path}: domain does not match parent directory")
        if payload.get("memory_id") != path.stem:
            errors.append(f"{path}: memory_id does not match filename")

    return {
        "status": "ok" if not errors else "degraded",
        "checked_files": checked_files,
        "errors": errors,
    }
