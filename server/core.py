"""Public facade for the Claude SDK bridge.

All names that were previously defined here are now implemented in sub-modules
and re-exported for backwards compatibility:

  server.audit_contract  — JSON contract helpers (schema, normalisation, validation)
  server.session_logging — SessionLogger, _log_cli_stderr, _log_bridge_failure
  server.agent_bridge    — build_options, run_agent, run_agent_full, run_agent_json,
                           ClaudeRuntimeError, AgentRunMeta

Import paths through server.core remain stable — do not change callers.
"""

from __future__ import annotations

# ── audit contract helpers ────────────────────────────────────────────────────
from server.audit_contract import (
    AUDIT_DECISION_DERIVATION,
    CONTRACTS_DIR,
    DEFAULT_OUTPUT_SCHEMA_NAME,
    INIT_RULES_REPORT_SCHEMA_NAME,
    JSONContractError,
    StructuredJSON,
    _coerce_reason_to_str,
    _coerce_risk_dimensions,
    _extract_json_object,
    _scale_risk_dimension_score,
    build_output_format,
    enrich_audit_decision,
    load_output_schema,
    resolve_output_schema_path,
    validate_structured_output_semantics,
)

# ── session logging helpers ───────────────────────────────────────────────────
from server.session_logging import (
    SessionLogger,
    _log_bridge_failure,
    _log_cli_stderr,
)

# ── SDK bridge ────────────────────────────────────────────────────────────────
from server.agent_bridge import (
    AgentRunMeta,
    ClaudeRuntimeError,
    build_options,
    run_agent,
    run_agent_full,
)
from server.json_bridge import run_agent_json

__all__ = [
    # constants & types
    "AUDIT_DECISION_DERIVATION",
    "CONTRACTS_DIR",
    "DEFAULT_OUTPUT_SCHEMA_NAME",
    "INIT_RULES_REPORT_SCHEMA_NAME",
    "StructuredJSON",
    # exception classes
    "ClaudeRuntimeError",
    "JSONContractError",
    # private helpers (tests import these)
    "_coerce_reason_to_str",
    "_coerce_risk_dimensions",
    "_extract_json_object",
    "_log_bridge_failure",
    "_log_cli_stderr",
    "_scale_risk_dimension_score",
    # contract helpers
    "build_output_format",
    "enrich_audit_decision",
    "load_output_schema",
    "resolve_output_schema_path",
    "validate_structured_output_semantics",
    # session logger
    "SessionLogger",
    # dataclass
    "AgentRunMeta",
    # public API
    "build_options",
    "run_agent",
    "run_agent_full",
    "run_agent_json",
]
