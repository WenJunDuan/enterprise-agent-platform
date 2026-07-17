"""JSON contract helpers: schema loading, normalisation, and semantic validation.

Shared platform scaffolding for *model-output conformance* — validating and
normalising what Claude returns against the declared output schema. This is not
business logic (the audit/tender/… decisions are made on the Claude side); it
only enforces the output contract, so it lives in ``common`` and is depended on
by feature domains, never the other way around. Pure functions, no SDK import.
"""

from __future__ import annotations

import json
import re
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
    return {"type": "json_schema", "schema": load_output_schema(_resolve_physical_schema_name(schema_name))}


@dataclass(frozen=True)
class SchemaProcessor:
    """Per-schema output-conformance hooks (registry entry).

    normalize: stamp server-authoritative metadata (claim_id/reviewed_by/timestamp) +
               coerce envelope format, **before** the hard JSON Schema check — so the
               gate never forces the model to fabricate server-owned fields. Receives
               the task ``request_id`` (claim_id falls back to it when the model omits it).
    validate:  raise JSONContractError when model output violates the contract.
    enrich:    return a normalised/derived output (e.g. derive result from verdict).
    """

    normalize: Callable[[StructuredJSON, str | None], StructuredJSON] | None = None
    validate: Callable[[StructuredJSON], None] | None = None
    enrich: Callable[[StructuredJSON], StructuredJSON] | None = None
    # resolve: enrich 之后、拿到本案底稿(evidence_source)时跑的确定性回查（如 evidence-resolution
    # 闸：校验模型引用的出处是否真在底稿）。仅当调用方透传 evidence_source 才触发；不传则跳过
    # （向后兼容，audit/旧路径零影响）。签名 (output, evidence_source) → output。
    resolve: Callable[[StructuredJSON, str], StructuredJSON] | None = None
    # schema_path: 物理 .claude/contracts 文件名覆盖（可选）。None（默认）＝物理文件与注册表 key
    # 同名（现状，audit/expense 零变化）；设置时，本 key 的处理器链挂在 schema_name 下，但硬 schema
    # 校验 / SDK output_format 复用 schema_path 指向的另一物理文件——供 tender 专属处理器链复用
    # 共享 audit-result.json，不必产出 byte-identical 副本。
    schema_path: str | None = None


_SCHEMA_PROCESSORS: dict[str, SchemaProcessor] = {}


def register_schema_processor(
    schema_name: str,
    *,
    normalize: Callable[[StructuredJSON, str | None], StructuredJSON] | None = None,
    validate: Callable[[StructuredJSON], None] | None = None,
    enrich: Callable[[StructuredJSON], StructuredJSON] | None = None,
    resolve: Callable[[StructuredJSON, str], StructuredJSON] | None = None,
    schema_path: str | None = None,
) -> None:
    """Register conformance hooks for a schema.

    New schemas register here (from the owning module) instead of editing a central
    if/elif — open for extension, closed for modification.
    """
    _SCHEMA_PROCESSORS[schema_name] = SchemaProcessor(
        normalize=normalize, validate=validate, enrich=enrich, resolve=resolve, schema_path=schema_path
    )


def _resolve_physical_schema_name(schema_name: str) -> str:
    """Resolve the physical `.claude/contracts/` file for a registry key.

    A registered processor may declare `schema_path` to reuse a different physical
    schema file than its own registry key (tender's key reuses the shared
    audit-result.json without a byte-duplicate file). Unregistered keys, or
    processors without schema_path, resolve to themselves — audit/expense unchanged.
    """
    processor = _SCHEMA_PROCESSORS.get(schema_name)
    if processor is not None and processor.schema_path:
        return processor.schema_path
    return schema_name


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
    except jsonschema.SchemaError as exc:
        # 契约 schema 文件本身非法 = 平台 bug（非模型 bug）。仍转 JSONContractError，
        # 避免未捕获异常穿透重试环→500 暴露内部 schema 路径。
        raise JSONContractError(f"契约 schema {schema_name} 自身非法: {exc.message}") from exc


def apply_schema_semantics(
    schema_name: str | None,
    structured_output: StructuredJSON,
    *,
    request_id: str | None = None,
    evidence_source: str | None = None,
) -> StructuredJSON:
    """Run the registered normalize + validate + enrich + resolve for schema_name; unregistered ⇒ as-is.

    This is the single entry the SDK bridge calls — it stays schema-name agnostic.

    ``schema_name`` 为空（None/""）= 「无命名 schema」：仅取模型 JSON 原样返回，不做形/语义校验。
    用于 enrichment 类调用（如 tender-extract-info，输出 {criteria, tender_info} 不对应单一承重
    契约，best-effort 取用、宁缺毋崩）；否则 ``CONTRACTS_DIR / None`` 会抛 TypeError 致整次调用失败。

    ``evidence_source``（可选）= 本案底稿文本（带 ``### 文件:`` + ``【第 N 页】`` 锚点）。非空且该
    schema 注册了 ``resolve`` hook 时，在 enrich 之后跑确定性回查（evidence-resolution 闸）。不传 →
    跳过 resolve（向后兼容：audit/旧路径不透传底稿，行为零变化）。
    顺序（round4 F1 G1 闸 + metadata 加固 + R1 evidence-resolution）：
      1. normalize：盖 server 权威元数据（claim_id/reviewed_by/timestamp）+ 拍平 envelope 格式，
         **先于**硬 schema 校验——这些是服务端职责，不该逼模型产出（否则模型漏一个就反复重试至失败）。
      2. _validate_against_json_schema：硬『形』校验（normalize 后、enrich 前；enrich 会派生 schema 外
         的 result/conclusion，故仍须先校验原始输出的形）。
      3. processor.validate：语义承重闸（verdict/policy_refs/评分一致性，**不放松**）。
      4. processor.enrich：派生 result/conclusion。
      5. processor.resolve：拿到底稿时回查出处真伪（**最后一步**——其写的额外标注键不再过 schema
         硬校验，返回值直接归档；resolve 内若升 verdict 会重跑 enrich 保持一致）。
    """
    if not schema_name:
        return structured_output
    processor = _SCHEMA_PROCESSORS.get(schema_name)
    if processor is not None and processor.normalize is not None:
        structured_output = processor.normalize(structured_output, request_id)
    # G1（round4 F1）：JSON Schema 形校验先于语义处理（normalize 后、enrich 前）。
    # T1 schema_path 别名：物理『形』校验解析到 schema_path 指向的文件（未设 → 原样 schema_name）。
    _validate_against_json_schema(_resolve_physical_schema_name(schema_name), structured_output)
    if processor is None:
        return structured_output
    if processor.validate is not None:
        processor.validate(structured_output)
    if processor.enrich is not None:
        structured_output = processor.enrich(structured_output)
    # R1 evidence-resolution：仅当调用方透传底稿且 schema 注册了 resolve hook。
    if evidence_source and processor.resolve is not None:
        structured_output = processor.resolve(structured_output, evidence_source)
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

    针对 reasoning 模型：思考/草稿（常含一段草稿 JSON）在成对 <think>…</think> 内，真正
    答案在块外；所以**剥离成对思考块**后去掉 ```json 围栏，扫出所有平衡的 {...}，返回
    **最后一个**能解析成 dict 的（最终答案通常在最后）。这样不会误抓推理里的草稿。
    用于"文本模式"：网关模型（如 qwen）直接输出 JSON 文本，由服务端解析。
    """
    if not text:
        return None
    # 剥离**成对** <think>…</think> 草稿块（非贪婪，DOTALL 跨行）。旧实现 `rsplit("</think>")`
    # 取最后一个 </think> 之后的文本——当模型把答案输出后又跟一个**游离尾随 </think>**
    # （glm/deepseek 文本模式偶发）时会截成空串、误返 None → 整单 JSONContractError 重试。
    # 剥离成对块既去草稿、又不丢答案；游离的单个 </think>（无配对 <think>）保留但不含 `{` 无害。
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
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
