"""契约后处理注册表：apply_schema_semantics 的 validate+enrich 分发 (OCP)。

锁定：内置 audit schema 仍校验+派生；未注册 schema 原样返回不报错；
新 schema 注册即生效，无需改分发器。
"""

from __future__ import annotations

import pytest

from server.common.contract import (
    DEFAULT_OUTPUT_SCHEMA_NAME,
    JSONContractError,
    SchemaProcessor,
    _SCHEMA_PROCESSORS,
    apply_schema_semantics,
    register_schema_processor,
)


def test_unregistered_schema_is_passthrough():
    payload = {"anything": 1}
    assert apply_schema_semantics("other/unknown.schema.json", payload) is payload


def test_builtin_audit_schema_validates_and_enriches():
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME,
        {"verdict": "approved", "explanation": "ok"},
    )
    # enrich 从 verdict 派生 result/conclusion
    assert out["result"] is True
    assert out["conclusion"] == "合规"


def test_builtin_audit_schema_rejects_bad_verdict():
    with pytest.raises(JSONContractError):
        apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, {"verdict": "??", "explanation": "x"})


def test_register_new_schema_takes_effect_without_editing_dispatcher():
    schema = "test/widget.schema.json"
    calls: list[str] = []

    def _validate(out):
        calls.append("validate")
        if "name" not in out:
            raise JSONContractError("widget needs name")

    def _enrich(out):
        out["enriched"] = True
        return out

    register_schema_processor(schema, validate=_validate, enrich=_enrich)
    try:
        result = apply_schema_semantics(schema, {"name": "w"})
        assert calls == ["validate"]
        assert result["enriched"] is True
        with pytest.raises(JSONContractError):
            apply_schema_semantics(schema, {})  # 缺 name → validate 抛错
    finally:
        _SCHEMA_PROCESSORS.pop(schema, None)  # 不污染全局注册表


def test_processor_dataclass_defaults_are_none():
    proc = SchemaProcessor()
    assert proc.validate is None
    assert proc.enrich is None
