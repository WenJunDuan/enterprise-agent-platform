"""JSON contract helpers: schema loading, normalisation, and semantic validation.

Shared platform scaffolding for *model-output conformance* — validating and
normalising what Claude returns against the declared output schema. This is not
business logic (the audit/tender/… decisions are made on the Claude side); it
only enforces the output contract, so it lives in ``common`` and is depended on
by feature domains, never the other way around. Pure functions, no SDK import.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import jsonschema

from server.platform.paths import PROJECT_ROOT

CONTRACTS_DIR = PROJECT_ROOT / ".claude" / "contracts"
DEFAULT_OUTPUT_SCHEMA_NAME = "common/audit-result.schema.json"
INIT_RULES_REPORT_SCHEMA_NAME = "system/init-rules-report.schema.json"
StructuredJSON = dict[str, Any] | list[Any]

class JSONContractError(ValueError):
    """Raised when a Claude response does not satisfy the JSON contract."""


def resolve_output_schema_path(schema_name: str) -> Path:
    """Resolve a schema path under `.claude/contracts` without allowing path escape."""
    schema_path = (CONTRACTS_DIR / schema_name).resolve()
    contracts_root = CONTRACTS_DIR.resolve()
    if contracts_root not in schema_path.parents:
        raise JSONContractError(f"Schema path escapes contracts root: {schema_name}")
    if not schema_path.is_file():
        raise JSONContractError(f"Structured output schema not found: {schema_name}")
    return schema_path


def load_output_schema(schema_name: str = DEFAULT_OUTPUT_SCHEMA_NAME) -> dict[str, Any]:
    """Load a JSON schema from `.claude/contracts`."""
    schema_path = resolve_output_schema_path(schema_name)
    try:
        loaded = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - exact error text is incidental
        raise JSONContractError(f"Structured output schema is invalid JSON: {schema_name}") from exc

    if not isinstance(loaded, dict):
        raise JSONContractError(f"Structured output schema must be a JSON object: {schema_name}")
    return loaded


def build_output_format(schema_name: str = DEFAULT_OUTPUT_SCHEMA_NAME) -> dict[str, Any]:
    """Build the SDK `output_format` payload for structured outputs."""
    return {"type": "json_schema", "schema": load_output_schema(schema_name)}


@dataclass(frozen=True)
class SchemaProcessor:
    """Per-schema output-conformance hooks (registry entry).

    validate: raise JSONContractError when model output violates the contract.
    enrich:   return a normalised/derived output (e.g. derive result from verdict).
    """

    validate: Callable[[StructuredJSON], None] | None = None
    enrich: Callable[[StructuredJSON], StructuredJSON] | None = None


_SCHEMA_PROCESSORS: dict[str, SchemaProcessor] = {}


def register_schema_processor(
    schema_name: str,
    *,
    validate: Callable[[StructuredJSON], None] | None = None,
    enrich: Callable[[StructuredJSON], StructuredJSON] | None = None,
) -> None:
    """Register conformance hooks for a schema.

    New schemas register here (from the owning module) instead of editing a central
    if/elif — open for extension, closed for modification.
    """
    _SCHEMA_PROCESSORS[schema_name] = SchemaProcessor(validate=validate, enrich=enrich)


def _validate_against_json_schema(schema_name: str, structured_output: StructuredJSON) -> None:
    """G1 验证闸（round4 F1 修复）：按声明的 JSON Schema 硬校验模型输出的『形』。

    默认文本路径此前只在 enrich 阶段查 verdict/explanation，schema 的 required /
    additionalProperties / 类型 全不验——伪造审批、缺 policy_refs/evidence_chain 都静默通过。
    这里在 enrich **之前**对原始输出跑 jsonschema.validate（enrich 会派生 result/conclusion，
    而 schema 是 additionalProperties:false 不含这两字段，故必须先于 enrich 校验原始输出）。
    失败抛 JSONContractError，被 ``server/audit/runner.py`` 的重试环接住（文本/结构化两路都经此）。

    无对应 schema 文件的 schema_name（如测试用未注册 schema）跳过，保持向后兼容。
    """
    try:
        schema = load_output_schema(schema_name)
    except JSONContractError:
        return  # 无对应 schema 文件 → 不强加校验
    try:
        jsonschema.validate(structured_output, schema)
    except jsonschema.ValidationError as exc:
        location = "/".join(str(p) for p in exc.absolute_path) or "(root)"
        raise JSONContractError(
            f"模型输出不满足 schema {schema_name} 于 `{location}`: {exc.message}"
        ) from exc


def apply_schema_semantics(schema_name: str, structured_output: StructuredJSON) -> StructuredJSON:
    """Run the registered validate + enrich for schema_name; unregistered ⇒ returned as-is.

    This is the single entry the SDK bridge calls — it stays schema-name agnostic.
    G1 验证闸：先按 JSON Schema 硬校验『形』(enrich 前、原始输出须自洽)，再跑语义 validate + enrich。
    """
    # G1（round4 F1）：JSON Schema 形校验先于一切语义处理。
    _validate_against_json_schema(schema_name, structured_output)
    processor = _SCHEMA_PROCESSORS.get(schema_name)
    if processor is None:
        return structured_output
    if processor.validate is not None:
        processor.validate(structured_output)
    if processor.enrich is not None:
        structured_output = processor.enrich(structured_output)
    return structured_output


def validate_structured_output_semantics(
    schema_name: str,
    structured_output: StructuredJSON,
) -> None:
    """Run only the registered validator for schema_name.

    Semantic rules JSON Schema alone cannot express. Stable entry point for callers
    and tests; unregistered schemas are a no-op.
    """
    processor = _SCHEMA_PROCESSORS.get(schema_name)
    if processor is not None and processor.validate is not None:
        processor.validate(structured_output)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """从模型文本里抽取**最终**的 JSON 对象。

    针对 reasoning 模型：思考/草稿（常含一段草稿 JSON）在 </think> 之前，真正答案在
    之后；所以先截到最后一个 </think> 之后，去掉 ```json 围栏，扫出所有平衡的 {...}，
    返回**最后一个**能解析成 dict 的（最终答案通常在最后）。这样不会误抓推理里的草稿。
    用于"文本模式"：网关模型（如 qwen）直接输出 JSON 文本，由服务端解析。
    """
    if not text:
        return None
    # reasoning 模型把草稿放 </think> 之前，真正答案在最后一个 </think> 之后
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1]
    cleaned = text.replace("```json", "").replace("```", "")
    # 扫出所有平衡的顶层 {...}
    objects: list[str] = []
    i = 0
    n = len(cleaned)
    while i < n:
        if cleaned[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        closed_at = -1
        for j in range(i, n):
            ch = cleaned[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    objects.append(cleaned[i : j + 1])
                    closed_at = j
                    break
        i = closed_at + 1 if closed_at != -1 else n
    # 最终答案在最后：从后往前返回第一个能解析成 dict 的
    for candidate in reversed(objects):
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


# 末尾装载内置输出契约（policy），确保它们随本注册表(mechanism)一起就绪。
from server.common import output_contracts as _output_contracts  # noqa: E402,F401
