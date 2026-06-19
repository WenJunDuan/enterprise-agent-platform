"""结构校验：/evaluate-bid 依赖的契约 schema 存在可载 + manual_review_reason 枚举一致。

只断言已入库的 .claude/contracts/* 契约；knowledge/tender/* 规则被 gitignore，
不在此断言（否则 clean checkout / CI 会误挂）。经真实 loader（load_output_schema）
载入，同时覆盖契约路径解析。
"""

from __future__ import annotations

import pytest

from server.common.contract import DEFAULT_OUTPUT_SCHEMA_NAME, load_output_schema

# evaluate-bid 五步 harness 声明依赖的契约（均已入库）：
# - 最终结论复用 common/audit-result（= DEFAULT_OUTPUT_SCHEMA_NAME）
# - S2 事实底稿语义 tender/extract-result；reviewer(默认关) tender/review-delta
_TENDER_CONTRACTS = [
    DEFAULT_OUTPUT_SCHEMA_NAME,
    "tender/extract-result.schema.json",
    "tender/review-delta.schema.json",
]

# tender 域在 manual_review 时会发出的 reason（CLAUDE.md tender 段 + design）：
# 规则缺失 rule_gap、一致性冲突(拟派 PM≠业绩 PM / 姓名不一致) data_conflict。
_TENDER_MANUAL_REVIEW_REASONS = {"rule_gap", "data_conflict"}


@pytest.mark.parametrize("schema_name", _TENDER_CONTRACTS)
def test_tender_contract_schema_loads(schema_name):
    schema = load_output_schema(schema_name)
    assert isinstance(schema, dict) and schema, f"{schema_name} 不是非空 JSON 对象"


def test_tender_manual_review_reasons_subset_of_audit_result_enum():
    schema = load_output_schema(DEFAULT_OUTPUT_SCHEMA_NAME)
    enum = set(schema["properties"]["manual_review_reason"]["enum"])
    missing = _TENDER_MANUAL_REVIEW_REASONS - enum
    assert not missing, (
        f"tender 用到的 manual_review_reason 不在 common/audit-result 枚举里：{missing}；"
        f"枚举={sorted(enum)}"
    )


def test_audit_result_verdict_enum_covers_tender_outcomes():
    # tender 评判会产出 approved / rejected(废标) / manual_review(不可判定)，三者都须在枚举内。
    schema = load_output_schema(DEFAULT_OUTPUT_SCHEMA_NAME)
    verdict_enum = set(schema["properties"]["verdict"]["enum"])
    assert {"approved", "rejected", "manual_review"} <= verdict_enum
