"""server.ocr.runner 归一化单测：模型自由输出 → form-fill 契约（schema 驱动）。

覆盖现场 502 的真实异形：fields 用对象索引、confidence 用文字、sub_tables 用对象、
顶层多 analysis_summary / low_confidence_fields、整体 None。归一化后必须过 form-fill 契约。
"""

from __future__ import annotations

import json

import jsonschema

from server.ocr.runner import (
    FORM_FILL_SCHEMA_PATH,
    _coerce_confidence,
    map_extraction_to_form,
    normalize_to_form_schema,
)

_SCHEMA = json.loads(FORM_FILL_SCHEMA_PATH.read_text(encoding="utf-8"))

_FORM_SCHEMA = {
    "form_id": "project_filing",
    "fields": [
        {"key": "项目名称", "component": "single_line"},
        {"key": "项目总投资(万元)", "component": "number"},
        {"key": "建设性质", "component": "select", "options": ["新建", "改建"]},
    ],
    "sub_tables": [
        {"key": "预测付款", "columns": ["付款节点", "比例", "金额"]},
    ],
}


def _validate(result: dict) -> None:
    jsonschema.validate(result, _SCHEMA)  # 不抛即合契约


def test_normalize_real_world_object_fields_case():
    # 现场 502 的真实结构：fields 对象索引 + confidence 文字 + reason + sub_tables 对象 + 额外键
    raw = {
        "form_id": "project_filing",
        "needs_review": True,
        "fields": {
            "项目名称": {"value": None, "confidence": "low", "reason": "底稿无实际值"},
            "项目总投资(万元)": {"value": 7500, "confidence": "high"},
        },
        "sub_tables": {"预测付款": {"rows": [], "note": "无合同条款"}},
        "low_confidence_fields": ["项目名称"],
        "analysis_summary": "底稿为功能清单，非项目实体数据",
    }
    result = normalize_to_form_schema(raw, _FORM_SCHEMA)
    _validate(result)

    by_key = {f["key"]: f for f in result["fields"]}
    assert set(by_key) == {"项目名称", "项目总投资(万元)", "建设性质"}  # schema 决定字段集
    assert by_key["项目名称"]["value"] is None
    assert by_key["项目名称"]["component"] == "single_line"  # component 从 schema 补
    assert isinstance(by_key["项目名称"]["confidence"], float)  # "low" → 数字
    assert by_key["项目总投资(万元)"]["value"] == 7500
    assert by_key["项目总投资(万元)"]["component"] == "number"
    assert result["sub_tables"] == [
        {"key": "预测付款", "columns": ["付款节点", "比例", "金额"], "rows": []}
    ]
    assert "项目名称" in result["low_confidence"]  # low_confidence_fields 被合并
    assert any("功能清单" in e["finding"] for e in result.get("evidence", []))  # summary 进 evidence
    assert "analysis_summary" not in result  # 契约不允许的顶层键被剔除
    assert "low_confidence_fields" not in result


def test_normalize_none_yields_empty_needs_review_form():
    # 模型输出 None（第二次重试的情况）→ 全字段 null + needs_review，而非崩
    result = normalize_to_form_schema(None, _FORM_SCHEMA)
    _validate(result)
    assert result["needs_review"] is True
    assert len(result["fields"]) == 3  # schema 字段全在
    assert all(f["value"] is None for f in result["fields"])
    assert result["sub_tables"] == [
        {"key": "预测付款", "columns": ["付款节点", "比例", "金额"], "rows": []}
    ]


def test_normalize_standard_list_fields_passthrough():
    # 模型已按契约输出（list fields）→ 正常保留
    raw = {
        "fields": [
            {"key": "项目名称", "component": "single_line", "value": "算力中心", "confidence": 0.95},
            {"key": "项目总投资(万元)", "component": "number", "value": 7500, "confidence": 0.9},
            {"key": "建设性质", "component": "select", "value": "新建", "confidence": 0.99},
        ],
        "sub_tables": [{"key": "预测付款", "rows": [{"付款节点": "首付", "比例": "30%"}]}],
        "needs_review": False,
    }
    result = normalize_to_form_schema(raw, _FORM_SCHEMA)
    _validate(result)
    by_key = {f["key"]: f for f in result["fields"]}
    assert by_key["项目名称"]["value"] == "算力中心"
    assert result["needs_review"] is False  # 全有值且高置信
    assert result["sub_tables"][0]["rows"] == [{"付款节点": "首付", "比例": "30%"}]


def test_normalize_missing_field_marked_low_confidence():
    # schema 有但模型没给的字段 → value null + low_confidence + needs_review
    raw = {"fields": [{"key": "项目名称", "component": "single_line", "value": "x", "confidence": 0.9}]}
    result = normalize_to_form_schema(raw, _FORM_SCHEMA)
    _validate(result)
    by_key = {f["key"]: f for f in result["fields"]}
    assert by_key["建设性质"]["value"] is None
    assert "建设性质" in result["low_confidence"]
    assert result["needs_review"] is True


def test_coerce_confidence_words_and_numbers():
    assert _coerce_confidence("low", default=0.5) == 0.3
    assert _coerce_confidence("HIGH", default=0.5) == 0.9
    assert _coerce_confidence(0.7, default=0.5) == 0.7
    assert _coerce_confidence(2.0, default=0.5) == 1.0  # clamp 到 1
    assert _coerce_confidence(None, default=0.5) == 0.5
    assert _coerce_confidence("garbage", default=0.5) == 0.5


async def test_map_extraction_recovers_malformed_output(monkeypatch):
    # 集成：模型吐现场那种异形 → map 第一次归一化即过，不重试、不 502
    import server.ocr.runner as runner_mod

    async def fake_agent(prompt, **kwargs):
        return (
            '{"fields": {"项目名称": {"value": null, "confidence": "low"}}, '
            '"sub_tables": {"预测付款": {"rows": []}}, '
            '"analysis_summary": "底稿无实体数据", "needs_review": true}'
        )

    monkeypatch.setattr(runner_mod, "run_agent_full", fake_agent)
    result = await map_extraction_to_form("底稿", _FORM_SCHEMA, request_id="t1")
    jsonschema.validate(result, _SCHEMA)  # 合约
    assert len(result["fields"]) == 3
