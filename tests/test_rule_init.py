import json
from pathlib import Path

from server.rule_init import initialize_rules


def _bootstrap_project_root(project_root: Path) -> None:
    (project_root / "knowledge" / "external").mkdir(parents=True)
    (project_root / "knowledge" / "memory" / "2026" / "03").mkdir(parents=True)
    (project_root / "docs").mkdir(parents=True)
    (project_root / ".cunzhi-memory").mkdir(parents=True)
    (project_root / "docs" / "expense-control-design.md").write_text(
        "# expense design\n",
        encoding="utf-8",
    )
    (project_root / "docs" / "architecture-summary.md").write_text(
        "# architecture summary\n",
        encoding="utf-8",
    )
    (project_root / ".cunzhi-memory" / "preferences.md").write_text(
        "# preferences\n",
        encoding="utf-8",
    )
    (project_root / "knowledge" / "memory" / "2026" / "03" / "2026-03-20.md").write_text(
        "# Daily Memory\n",
        encoding="utf-8",
    )


def test_initialize_rules_bootstraps_schema_placeholders_and_report(tmp_path: Path) -> None:
    _bootstrap_project_root(tmp_path)

    summary = initialize_rules(tmp_path, domain="expense")

    assert summary.status == "pending_source_documents"
    assert (tmp_path / "knowledge" / "_schema" / "rule.schema.json").is_file()
    assert (tmp_path / "knowledge" / "expense" / "travel.rules.json").is_file()
    assert (tmp_path / "knowledge" / "expense" / "entertainment.rules.json").is_file()
    assert (tmp_path / "knowledge" / "expense" / "invoice.rules.json").is_file()
    assert (tmp_path / "knowledge" / "expense" / "general.rules.json").is_file()
    assert (tmp_path / "knowledge" / "expense" / "transport.rules.json").is_file()
    assert (tmp_path / "knowledge" / "expense" / "loan.rules.json").is_file()
    assert (tmp_path / "knowledge" / "expense" / "init-manifest.json").is_file()
    assert (tmp_path / "knowledge" / "expense" / "init-report.md").is_file()

    manifest = json.loads((tmp_path / "knowledge" / "expense" / "init-manifest.json").read_text())
    assert manifest["command"] == "/init"
    assert manifest["status"] == "pending_source_documents"
    assert manifest["external_sources"] == []
    assert "docs/expense-control-design.md" in manifest["memory_sources"]
    assert "knowledge/memory/2026/03/2026-03-20.md" in manifest["memory_sources"]
    assert "No external policy documents found" in manifest["warnings"][0]


def test_initialize_rules_discovers_daily_memory_before_legacy_memory(tmp_path: Path) -> None:
    _bootstrap_project_root(tmp_path)
    (tmp_path / "knowledge" / "memory" / "README.md").write_text("# memory readme\n", encoding="utf-8")

    initialize_rules(tmp_path, domain="expense")

    manifest = json.loads((tmp_path / "knowledge" / "expense" / "init-manifest.json").read_text())
    memory_sources = manifest["memory_sources"]
    knowledge_memory_index = memory_sources.index("knowledge/memory/2026/03/2026-03-20.md")
    legacy_memory_index = memory_sources.index(".cunzhi-memory/preferences.md")
    assert knowledge_memory_index < legacy_memory_index
    assert "knowledge/memory/README.md" not in memory_sources


def test_initialize_rules_reads_memory_root_from_env(tmp_path: Path, monkeypatch) -> None:
    _bootstrap_project_root(tmp_path)
    monkeypatch.setenv("APP_MEMORY_ROOT", "knowledge/runtime-memory")
    runtime_memory_path = tmp_path / "knowledge" / "runtime-memory" / "2026" / "03" / "2026-03-20.md"
    runtime_memory_path.parent.mkdir(parents=True)
    runtime_memory_path.write_text("# Runtime Memory\n", encoding="utf-8")

    initialize_rules(tmp_path, domain="expense")

    manifest = json.loads((tmp_path / "knowledge" / "expense" / "init-manifest.json").read_text())
    assert "knowledge/runtime-memory/2026/03/2026-03-20.md" in manifest["memory_sources"]
    assert "knowledge/memory/2026/03/2026-03-20.md" not in manifest["memory_sources"]


def test_initialize_rules_flags_advanced_sources_for_confirmation(tmp_path: Path) -> None:
    _bootstrap_project_root(tmp_path)
    (tmp_path / "knowledge" / "external" / "travel-policy.pdf").write_bytes(b"%PDF-1.4")

    summary = initialize_rules(tmp_path, domain="expense")

    manifest = json.loads((tmp_path / "knowledge" / "expense" / "init-manifest.json").read_text())
    assert summary.status == "awaiting_advanced_extraction_confirmation"
    assert manifest["advanced_sources"][0]["path"] == "knowledge/external/travel-policy.pdf"
    assert any("OCR/vector support" in warning for warning in manifest["warnings"])


def test_initialize_rules_treats_unknown_source_types_as_needing_confirmation(tmp_path: Path) -> None:
    _bootstrap_project_root(tmp_path)
    (tmp_path / "knowledge" / "external" / "travel-policy.xlsx").write_bytes(b"sheet")

    summary = initialize_rules(tmp_path, domain="expense")

    manifest = json.loads((tmp_path / "knowledge" / "expense" / "init-manifest.json").read_text())
    assert summary.status == "awaiting_advanced_extraction_confirmation"
    assert manifest["advanced_sources"][0]["kind"] == "advanced"


def test_initialize_rules_preserves_existing_rule_files(tmp_path: Path) -> None:
    _bootstrap_project_root(tmp_path)
    expense_dir = tmp_path / "knowledge" / "expense"
    expense_dir.mkdir(parents=True)
    travel_path = expense_dir / "travel.rules.json"
    original = {
        "domain": "expense",
        "category": "travel",
        "version": "2024.01",
        "effective_date": "2024-01-01",
        "rules": [{"rule_id": "expense.travel.001", "description": "existing", "conditions": {}, "action": "approve"}],
    }
    travel_path.write_text(json.dumps(original, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    initialize_rules(tmp_path, domain="expense")

    assert json.loads(travel_path.read_text(encoding="utf-8")) == original


def test_initialize_rules_merges_text_bootstrap_into_existing_rule_files(tmp_path: Path) -> None:
    _bootstrap_project_root(tmp_path)
    expense_dir = tmp_path / "knowledge" / "expense"
    expense_dir.mkdir(parents=True)
    travel_path = expense_dir / "travel.rules.json"
    original = {
        "domain": "expense",
        "category": "travel",
        "version": "2024.01",
        "effective_date": "2024-01-01",
        "rules": [{"rule_id": "expense.travel.001", "description": "existing", "conditions": {}, "action": "approve"}],
    }
    travel_path.write_text(json.dumps(original, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "knowledge" / "external" / "travel-policy.txt").write_text(
        "- 差旅住宿报销不超过500元\n",
        encoding="utf-8",
    )

    initialize_rules(tmp_path, domain="expense")

    merged = json.loads(travel_path.read_text(encoding="utf-8"))
    assert len(merged["rules"]) == 2
    assert merged["rules"][0]["rule_id"] == "expense.travel.001"
    assert merged["rules"][1]["original_text"] == "差旅住宿报销不超过500元"


def test_initialize_rules_creates_hr_rule_targets_instead_of_general_only(tmp_path: Path) -> None:
    _bootstrap_project_root(tmp_path)

    summary = initialize_rules(tmp_path, domain="hr")

    assert summary.domain == "hr"
    assert (tmp_path / "knowledge" / "hr" / "leave.rules.json").is_file()
    assert (tmp_path / "knowledge" / "hr" / "attendance.rules.json").is_file()
    assert not (tmp_path / "knowledge" / "hr" / "general.rules.json").exists()


def test_initialize_rules_ignores_generated_external_markdown_artifacts(tmp_path: Path) -> None:
    _bootstrap_project_root(tmp_path)
    (tmp_path / "knowledge" / "external" / "README.md").write_text("# external\n", encoding="utf-8")
    (tmp_path / "knowledge" / "external" / "policy.structured.md").write_text(
        "# structured copy\n- 差旅报销必须审批\n",
        encoding="utf-8",
    )

    summary = initialize_rules(tmp_path, domain="expense")

    manifest = json.loads((tmp_path / "knowledge" / "expense" / "init-manifest.json").read_text())
    assert summary.status == "pending_source_documents"
    assert manifest["external_sources"] == []
    assert manifest["text_sources"] == []


def test_initialize_rules_preserves_existing_schema_file(tmp_path: Path) -> None:
    _bootstrap_project_root(tmp_path)
    schema_dir = tmp_path / "knowledge" / "_schema"
    schema_dir.mkdir(parents=True, exist_ok=True)
    schema_path = schema_dir / "rule.schema.json"
    original_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["domain", "category", "rules"],
        "properties": {
            "domain": {"type": "string"},
            "category": {"type": "string"},
            "rules": {"type": "array"},
        },
    }
    schema_path.write_text(json.dumps(original_schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    initialize_rules(tmp_path, domain="expense")

    assert json.loads(schema_path.read_text(encoding="utf-8")) == original_schema
