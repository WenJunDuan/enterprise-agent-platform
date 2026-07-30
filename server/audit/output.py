"""Expense-audit output contract alias with mandatory five-dimensional risk scores."""

from __future__ import annotations

from server.common.contract import (
    DEFAULT_OUTPUT_SCHEMA_NAME,
    StructuredJSON,
    register_schema_processor,
)
from server.common.output_contracts import (
    _validate_audit_result,
    _validate_risk_dimensions,
    enrich_audit_decision,
    normalize_audit_result,
)


EXPENSE_OUTPUT_SCHEMA_NAME = "expense/audit-result.schema.json"


def validate_expense_audit_result(structured_output: StructuredJSON) -> None:
    """Apply the shared audit gates, then require all five expense risk dimensions."""
    _validate_audit_result(structured_output)
    if isinstance(structured_output, dict):
        _validate_risk_dimensions(structured_output)


register_schema_processor(
    EXPENSE_OUTPUT_SCHEMA_NAME,
    normalize=normalize_audit_result,
    validate=validate_expense_audit_result,
    enrich=enrich_audit_decision,
    schema_path=DEFAULT_OUTPUT_SCHEMA_NAME,
)
