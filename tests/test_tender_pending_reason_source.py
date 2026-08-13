"""KD2 语义单源：``pending_reason`` 枚举必须**读自** audit-result.schema.json，而非在服务端复写。

复写的代价是实测过的：该枚举曾同时活在 prompt / schema / output.py / 前端 types 四处，一次判分
纪律修订要同步 5 个位置，任一处漏改就是"校验与契约悄悄分叉"。本组测试用「篡改 schema 副本 →
直调 loader」证明取值确实来自文件内容，常量复写会立刻红。
"""

from __future__ import annotations

import json
from pathlib import Path

from server.common.contract import DEFAULT_OUTPUT_SCHEMA_NAME, resolve_output_schema_path
from server.tender.output import _load_pending_reasons

SCORING_ITEM_PATH = ("extracted_data", "scoring")


def _schema_copy(tmp_path: Path, mutate) -> Path:
    schema = json.loads(resolve_output_schema_path(DEFAULT_OUTPUT_SCHEMA_NAME).read_text("utf-8"))
    props = schema["properties"]
    item_props = props["extracted_data"]["properties"]["scoring"]["items"]["properties"]
    mutate(item_props["pending_reason"])
    target = tmp_path / "audit-result.schema.json"
    target.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
    return target


def test_loader_reads_live_schema_enum():
    """真实 schema 里声明的六个取值，loader 一个不多一个不少地读出来。"""
    loaded = _load_pending_reasons(resolve_output_schema_path(DEFAULT_OUTPUT_SCHEMA_NAME))
    assert loaded == {
        "cross_bid",
        "external_data",
        "live_event",
        "evidence_unresolved",
        "manual_mode",
        "non_responsive",
    }


def test_loader_follows_tampered_schema_copy(tmp_path: Path):
    """篡改副本里加一个取值 → loader 必须跟着变；不变即证明枚举是硬编码的。"""
    tampered = _schema_copy(tmp_path, lambda node: node["enum"].append("tampered_reason"))
    assert "tampered_reason" in _load_pending_reasons(tampered)


def test_loader_follows_schema_removal(tmp_path: Path):
    """副本里删掉一个取值 → loader 也必须跟着少，方向两侧都锁死。"""
    shrunk = _schema_copy(tmp_path, lambda node: node["enum"].remove("cross_bid"))
    loaded = _load_pending_reasons(shrunk)
    assert "cross_bid" not in loaded
    assert "external_data" in loaded
