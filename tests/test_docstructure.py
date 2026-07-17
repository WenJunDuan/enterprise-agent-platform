"""Synthetic tests for deterministic document-level OCR structure extraction."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from server.ocr.docstructure import build_doc_structure, find_chapters_by_tag, tag_chapter

SCHEMA = Path(__file__).parents[1] / ".claude/contracts/ocr/doc-structure.schema.json"


def _body(text: str) -> str:
    return "### 文件: 招标文件.pdf (kind=pdf_text, route=native)\n" + text.strip()


def _entity(structure: dict, entity_type: str) -> dict:
    return next(entity for entity in structure["entities"] if entity["type"] == entity_type)


def test_chapter_tree_nests_by_heading_level():
    structure = build_doc_structure(
        _body(
            """
            【第 1 页】
            # 第一章 总则
            ## 一、项目说明
            ### （一）适用范围
            """
        )
    )

    root = structure["chapters"][0]
    assert root["title"] == "第一章 总则"
    assert root["level"] == 1
    assert root["children"][0]["title"] == "一、项目说明"
    assert root["children"][0]["children"][0]["level"] == 3


def test_semantic_tags_cover_evaluation_and_qualification():
    structure = build_doc_structure(
        _body(
            """
            【第 2 页】
            # 第一章 资格审查
            # 第二章 评标办法与评分标准
            """
        )
    )

    assert [chapter["tag"] for chapter in structure["chapters"]] == [
        "qualification_review",
        "evaluation_method",
    ]


def test_other_chapters_get_general_tag():
    assert tag_chapter("第三章 其他说明") == "general"
    assert tag_chapter("") is None


def test_entities_have_correct_page_anchors_and_normalized_values():
    structure = build_doc_structure(
        _body(
            """
            【第 12 页】
            投标总价：12,345,678.00
            开标时间：2026年5月20日
            资质证书编号：苏B2-20240xxx
            项目负责人：张三
            """
        )
    )

    assert _entity(structure, "amount") == {
        "type": "amount",
        "value": "12345678.00",
        "page": 12,
        "source": "投标总价：12,345,678.00",
    }
    assert _entity(structure, "date")["value"] == "2026-05-20"
    assert _entity(structure, "date")["page"] == 12
    assert _entity(structure, "cert_no")["value"] == "苏B2-20240xxx"
    assert _entity(structure, "cert_no")["page"] == 12
    assert _entity(structure, "person")["value"] == "张三"
    assert _entity(structure, "person")["page"] == 12


def test_entities_deduplicate_same_type_value_and_page():
    structure = build_doc_structure(
        _body(
            """
            【第 3 页】
            项目负责人：李四
            项目负责人：李四
            """
        )
    )

    assert [entity for entity in structure["entities"] if entity["type"] == "person"] == [
        {"type": "person", "value": "李四", "page": 3, "source": "项目负责人：李四"}
    ]


def test_page_anchor_fidelity_and_long_tail_null_semantics():
    long_tail = "\n".join(f"无锚正文行 {index}" for index in range(301))
    structure = build_doc_structure(
        _body(
            "\n".join(
                [
                    "【第 7 页】",
                    "# 第一章 有锚章节",
                    long_tail,
                    "# 第二章 长尾章节",
                    "项目负责人：王五",
                ]
            )
        )
    )

    assert structure["page_count"] == 7
    assert structure["chapters"][0]["page"] == 7
    assert structure["chapters"][1]["page"] is None
    assert _entity(structure, "person")["page"] is None
    assert {
        chapter["page"] for chapter in structure["chapters"] if chapter["page"] is not None
    } <= {7}


def test_cross_page_tables_merge_rows_and_real_pages():
    structure = build_doc_structure(
        _body(
            """
            【第 5 页】
            [表: 分部分项工程量清单]
            序号	名称	金额
            1	土建	100.00
            【第 6 页】
            2	安装	200.00
            """
        )
    )

    assert structure["tables"] == [
        {
            "name": "分部分项工程量清单",
            "start_page": 5,
            "end_page": 6,
            "columns": ["序号", "名称", "金额"],
            "row_count": 2,
            "merged_from_pages": [5, 6],
        }
    ]


def test_tables_with_intervening_body_do_not_merge():
    structure = build_doc_structure(
        _body(
            """
            【第 1 页】
            [表: 第一张表]
            序号	名称
            1	甲
            【第 2 页】
            # 表格之间的正文
            【第 3 页】
            [表: 第二张表]
            序号	名称
            2	乙
            """
        )
    )

    assert len(structure["tables"]) == 2
    assert [table["merged_from_pages"] for table in structure["tables"]] == [[1], [3]]


def test_markdown_table_is_structured():
    structure = build_doc_structure(
        _body(
            """
            【第 4 页】
            | 序号 | 名称 |
            | --- | --- |
            | 1 | 甲 |
            """
        )
    )

    assert structure["tables"][0]["columns"] == ["序号", "名称"]
    assert structure["tables"][0]["row_count"] == 1
    assert structure["tables"][0]["start_page"] == structure["tables"][0]["end_page"] == 4


def test_find_chapters_by_tag_traverses_nested_tree():
    structure = build_doc_structure(
        _body(
            """
            【第 8 页】
            # 第一章 总则
            ## 一、资格审查要求
            ### （一）资格条件
            """
        )
    )

    matches = find_chapters_by_tag(structure, "qualification_review")
    assert [chapter["title"] for chapter in matches] == ["一、资格审查要求"]
    assert matches[0]["page"] == 8


def test_no_page_anchor_means_null_not_a_guessed_page():
    structure = build_doc_structure("### 文件: 无页锚.txt\n项目负责人：赵六\n金额：99.00")

    assert structure["page_count"] is None
    assert structure["chapters"] == []
    assert {entity["page"] for entity in structure["entities"]} == {None}
    assert structure["tables"] == []


def test_output_matches_draft07_contract():
    structure = build_doc_structure(_body("【第 1 页】\n# 第一章 评标办法\n投标总价：10,000.00"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    jsonschema.validate(structure, schema)
