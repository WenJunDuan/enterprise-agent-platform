"""结构校验：/review-contract 依赖的 legal 契约 schema 存在可载 + 枚举/结构一致。

镜像 test_tender_contracts：只断言已入库的 .claude/contracts/legal/*，经真实 loader 载入，
避开 gitignored 的 knowledge/。
"""

from __future__ import annotations

import pytest

from server.common.contract import DEFAULT_OUTPUT_SCHEMA_NAME, load_output_schema

# /review-contract 声明依赖的契约：最终结论复用 common/audit-result；
# S2 合同事实底稿 legal/extract-result；reviewer(默认关) legal/review-delta。
_LEGAL_CONTRACTS = [
    DEFAULT_OUTPUT_SCHEMA_NAME,
    "legal/extract-result.schema.json",
    "legal/review-delta.schema.json",
]

# 合同审查 manual_review 时会发出的 reason：规则缺失 rule_gap、条款/主体冲突 data_conflict。
_LEGAL_MANUAL_REVIEW_REASONS = {"rule_gap", "data_conflict"}


@pytest.mark.parametrize("schema_name", _LEGAL_CONTRACTS)
def test_legal_contract_schema_loads(schema_name):
    schema = load_output_schema(schema_name)
    assert isinstance(schema, dict) and schema, f"{schema_name} 不是非空 JSON 对象"


def test_legal_manual_review_reasons_subset_of_audit_result_enum():
    schema = load_output_schema(DEFAULT_OUTPUT_SCHEMA_NAME)
    enum = set(schema["properties"]["manual_review_reason"]["enum"])
    missing = _LEGAL_MANUAL_REVIEW_REASONS - enum
    assert not missing, (
        f"legal 用到的 manual_review_reason 不在 common/audit-result 枚举里：{missing}；枚举={sorted(enum)}"
    )


def test_legal_extract_result_has_contract_structure():
    # 合同库核心结构：条款 + 付款节点 + 合同元信息，必须在底稿 schema 里。
    schema = load_output_schema("legal/extract-result.schema.json")
    props = schema["properties"]
    for key in ("contract_meta", "clauses", "payment_nodes", "parties"):
        assert key in props, f"legal/extract-result 缺字段 {key}"
