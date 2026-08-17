"""章节解析必须区分目录条目与正文章节（2026-08-17 实跑发现）。

演练发现：真实标书开头有一段目录（第二章…第七章连续罗列），`parse_chapters` 把目录条目
和正文章节一视同仁，于是：

1. 章节树里同一章出现两次（目录一次、正文一次）；
2. 「第四章 评审方法和程序」**只在目录里被识别**——正文那个因紧跟内容未被切出；
3. 检索 `evaluation_method` 标签时命中的是一句正文（"按照招标文件规定的评标办法…"），
   而不是真正的评审方法章节。

后果：模型定位评分标准要试错——先命中目录、发现不对、再找一次，纯烧轮次。这属于服务端
能确定性解决却甩给模型的活。
"""

from __future__ import annotations


def _toc_then_body() -> list[str]:
    """真实标书形态：连续目录块在前，正文章节在后。"""
    return [
        "第一章 投标邀请",
        "第二章 投标人须知",
        "第三章 项目需求",
        "第四章 评审方法和程序",
        "第五章 合同授予",
        "第一章 投标邀请",
        "项目概况",
        "本项目预算金额 133 万元。",
        "第四章 评审方法和程序",
        "一、开标模式",
        "不见面远程开标。",
        "六、评审评分项",
        "企业综合实力 6 分。",
    ]


def test_toc_entries_are_not_emitted_as_chapters():
    """目录块不该产出章节节点——否则同一章在树里出现两次。"""
    from server.ocr.docstructure import parse_chapters

    chapters = parse_chapters(_toc_then_body())
    titles = [c["title"] for c in chapters]

    assert titles.count("第四章 评审方法和程序") == 1, f"目录与正文重复：{titles}"
    assert titles.count("第一章 投标邀请") == 1


def test_body_chapter_survives_and_keeps_position():
    """留下的必须是**正文**那一个（能带出后续内容），不是目录条目。"""
    from server.ocr.docstructure import parse_chapters

    chapters = parse_chapters(_toc_then_body())
    review = next(c for c in chapters if "评审方法" in c["title"])

    assert review["line_start"] is not None
    assert review["line_start"] >= 8, "必须指向正文位置，不是开头的目录条目"


def test_document_without_toc_is_unchanged():
    """无目录的文档行为不变——本改动不能影响既有解析。"""
    from server.ocr.docstructure import parse_chapters

    lines = ["第一章 总则", "正文内容一", "第二章 罚则", "正文内容二"]
    titles = [c["title"] for c in parse_chapters(lines)]

    assert titles == ["第一章 总则", "第二章 罚则"]


def test_structure_and_rag_skip_the_same_toc_lines():
    """docstructure 与 rag 必须用同一套目录跳过规则，否则每份带目录的文档都误判不匹配。

    实测（2026-08-17）：parse_chapters 跳目录后产出 98 个节点，而 rag 的
    _flatten_heading_lines 仍数 133 个标题行，差的 35 正是目录条目 →
    StructureBodyMismatchError → 招标层退化成 10 个粗 chunk（应为 105 个章节级）。
    """
    from server.ocr.docstructure import build_doc_structure, normalize_body
    from server.ocr.rag import _flatten_heading_lines, _flatten_tree

    body = normalize_body("\n".join(_toc_then_body()))
    structure = build_doc_structure(body)

    assert len(_flatten_tree(structure["chapters"])) == len(_flatten_heading_lines(body.splitlines()))


def test_normalize_body_is_idempotent_and_structure_aligned():
    """规范化必须幂等，且 structure 只能基于规范化后的文本构建（否则行号错位）。"""
    from server.ocr.docstructure import normalize_body

    raw = "正文结束。 第四章 评审方法和程序\n一、开标模式\n内容"
    once = normalize_body(raw)

    assert normalize_body(once) == once
    assert "第四章 评审方法和程序" in once.splitlines()
