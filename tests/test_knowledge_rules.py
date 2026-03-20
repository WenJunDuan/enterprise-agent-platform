import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_json(relative_path: str) -> dict:
    return json.loads((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))


def test_rule_schema_and_domain_model_schema_exist() -> None:
    rule_schema = _read_json("knowledge/_schema/rule.schema.json")
    domain_models_schema = _read_json("knowledge/_schema/domain-models.schema.json")

    assert rule_schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert "rules" in rule_schema["properties"]
    assert "employee_context" in domain_models_schema["properties"]
    assert "travel_request" in domain_models_schema["properties"]
    assert "expense_claim" in domain_models_schema["properties"]
    assert "policy_rule" in domain_models_schema["properties"]


def test_expense_rule_packs_exist_with_expected_categories() -> None:
    expected_paths = {
        "knowledge/expense/travel.rules.json": "travel",
        "knowledge/expense/entertainment.rules.json": "entertainment",
        "knowledge/expense/general.rules.json": "general",
        "knowledge/expense/invoice.rules.json": "invoice",
        "knowledge/expense/transport.rules.json": "transport",
        "knowledge/expense/loan.rules.json": "loan",
    }

    for relative_path, category in expected_paths.items():
        payload = _read_json(relative_path)
        assert payload["domain"] == "expense"
        assert payload["category"] == category
        assert payload["rules"], relative_path


def test_expense_thresholds_exist_with_expected_sections() -> None:
    payload = _read_json("knowledge/expense/thresholds.json")

    assert "travel" in payload
    assert "entertainment" in payload
    assert "invoice" in payload
    assert payload["travel"]["allowance_per_day"] == 200


def test_hr_rule_packs_exist_with_expected_categories() -> None:
    expected_paths = {
        "knowledge/hr/leave.rules.json": "leave",
        "knowledge/hr/attendance.rules.json": "attendance",
    }

    for relative_path, category in expected_paths.items():
        payload = _read_json(relative_path)
        assert payload["domain"] == "hr"
        assert payload["category"] == category
        assert payload["rules"], relative_path


def test_representative_rules_capture_handbook_constraints() -> None:
    travel_rules = _read_json("knowledge/expense/travel.rules.json")["rules"]
    entertainment_rules = _read_json("knowledge/expense/entertainment.rules.json")["rules"]
    invoice_rules = _read_json("knowledge/expense/invoice.rules.json")["rules"]
    leave_rules = _read_json("knowledge/hr/leave.rules.json")["rules"]

    assert any(rule["conditions"].get("approval_level") == "department_manager" for rule in travel_rules)
    assert any(rule["conditions"].get("max_amount") == 500 for rule in travel_rules)
    assert any("招待申请单" in rule["conditions"].get("required_docs", []) for rule in entertainment_rules)
    assert any(rule["conditions"].get("max_amount") == 1000 for rule in entertainment_rules)
    assert any(rule["conditions"].get("invoice_required") is True for rule in invoice_rules)
    assert any(rule["conditions"].get("max_days_per_request") == 3 for rule in leave_rules)
    assert any("三甲医院诊断书" in rule["conditions"].get("required_docs", []) for rule in leave_rules)
