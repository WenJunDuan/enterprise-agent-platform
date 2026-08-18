"""旧版 .doc 兜底档：按 BEL 还原 Word 表格结构（2026-08-17 实跑发现）。

演练发现：本机无 LibreOffice/catdoc/antiword 时，`read_legacy_word` 走二进制兜底档，
返回 `tables: []` —— 但表格数据其实**没丢**，Word 用 `\x07`（BEL）作单元格分隔符，
原文里长这样：

    提供有效期内的证书扫描件。\x076\x070\x07客观分\x07\x072\x07类似业绩\x07投标人自2022年…
                              ↑最高分 ↑最低分 ↑类型      ↑序号 ↑评分点名称

`_clean_extracted_text` 把 BEL 当普通字符留着，模型看到的是黏连乱码，只能从流式文本
里反推列边界——而评标最需要的评分表恰恰全在表格里。实测真实标书按 BEL 切分可完整
重建 19 个字段。
"""

from __future__ import annotations

BEL = "\x07"


def test_bel_separated_cells_become_table_rows():
    """兜底档必须把 BEL 分隔的单元格还原成 tables，而不是留在正文里当乱码。"""
    from server.ocr.native import recover_bel_tables

    raw = (
        "六、评审评分项\n"
        f"1{BEL}企业综合实力{BEL}具有二级及以上资质证书得2分{BEL}6{BEL}0{BEL}客观分{BEL}"
        f"{BEL}2{BEL}类似业绩{BEL}每有1个得3分，最多得9分{BEL}9{BEL}0{BEL}客观分\n"
    )
    blocks, tables = recover_bel_tables(raw)

    assert tables, "BEL 单元格必须被还原为表格"
    cells = [cell for row in tables[0]["rows"] for cell in row]
    assert "企业综合实力" in cells
    assert "类似业绩" in cells
    assert "6" in cells and "9" in cells, "分值列必须保留（评标据此判分）"
    assert BEL not in "\n".join(blocks), "正文里不得残留 BEL 控制字符"


def test_text_without_bel_is_left_alone():
    """无表格的纯文本原样返回——兜底档不能因为这次改动改变既有行为。"""
    from server.ocr.native import recover_bel_tables

    # 编号与金额为合成值（真实值 2026-08-18 已清除）：DEMO 前缀明示虚构，保住
    # 「字母段-6位数字段」结构且故意落在 test_no_real_corpus 编号守卫网内（已加白）。
    raw = "第一章 投标邀请\n项目编号：DEMO-100001\n预算金额：888万元"
    blocks, tables = recover_bel_tables(raw)

    assert tables == []
    assert "\n".join(blocks) == raw


def test_read_legacy_word_surfaces_recovered_tables(monkeypatch, tmp_path):
    """端到端：兜底档产出的 tables 不再恒为空。"""
    from server.ocr import native

    monkeypatch.setattr(native, "_legacy_word_via_libreoffice", lambda _p: None)
    monkeypatch.setattr(native, "_run_text_converter", lambda _argv: None)
    monkeypatch.setattr(
        native,
        "_read_legacy_word_utf16_fallback",
        lambda _p: f"评分表\n1{BEL}企业综合实力{BEL}6{BEL}客观分\n",
    )

    doc = tmp_path / "招标文件.doc"
    doc.write_bytes(b"\xd0\xcf\x11\xe0legacy")
    result = native.read_legacy_word(doc)

    assert result["tables"], "兜底档必须带出表格（修复前恒为 []）"


def test_line_per_cell_form_is_deliberately_left_as_text():
    """同表混用两种形态时，只治 BEL 黏连档，逐行档保持原样。

    真实标书实测：项 1-3 用 BEL 分隔（黏连不可读），项 4-8 每单元格独立成行（换行即分列）。
    后者本来就是模型能顺序读懂的文本；强行按空行重组会把正文段落误判成表格，得不偿失。
    """
    from server.ocr.native import recover_bel_tables

    raw = "技术参数指标\n根据采购文件技术要求打分\n25\n0\n客观分\n"
    blocks, tables = recover_bel_tables(raw)

    assert tables == [], "无 BEL 的逐行形态不该被当成表格重组"
    assert "技术参数指标" in blocks and "25" in blocks, "内容必须原样保留在正文里"
