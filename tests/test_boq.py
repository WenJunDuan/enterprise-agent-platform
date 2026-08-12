"""BOQ 感知抽取（R2）：超大已标价工程量清单 → 结构化关键金额紧凑摘要。

锁定：is_boq(名/内容/pages排除) / 金额两档(排编码+整数总价) / 投标总价候选打分 /
table段无页号 / 合计降序+计数 / TopN排总价 / 摘要超限 / 回落 / R1 parse_corpus 协同。
"""

from __future__ import annotations

from server.ocr.boq import (
    extract_boq_summary,
    is_boq,
    normalize_amount,
)

# 合成扉页 + 多单位工程片段（页锚点独占行，模拟 draft_render.render_body 产物）
COVER = """### 文件: 1.05 已标价工程量清单.pdf (kind=pdf_text, route=native)
【第 2 页】
投标总价(小写): ______________
381574199.97
(大写): ______________
叁亿捌仟壹佰伍拾柒万肆仟壹佰玖拾玖元玖角柒分
投  标  人:
江苏通州二建建设工程集团有限公司
【第 3527 页】
单位工程 电梯工程(075)
投标总价
851886.14
【第 3528 页】
序号
项目编码
040501004012
分部分项合计
3012424.9
单价措施合计
17765.51
合计
3030190.41
【第 8388 页】
税金
合计
851886.14
"""


# ── normalize_amount ──────────────────────────────────────────────────────────


def test_normalize_amount():
    assert normalize_amount("381,574,199.97") == 381574199.97
    assert normalize_amount("3012424.9") == 3012424.9


# ── is_boq ────────────────────────────────────────────────────────────────────


def test_is_boq_by_filename():
    assert is_boq("1.05 已标价工程量清单.pdf", "") is True
    assert is_boq("xx分部分项yy.pdf", "") is True


def test_is_boq_by_content():
    body = "项目编码 综合单价 合价 ... 分部分项合计 ... 合计"
    assert is_boq("某清单.pdf", body) is True


def test_is_boq_negative_normal_file():
    assert is_boq("投标函.pdf", "我公司愿意承包本工程") is False


def test_is_boq_pages_path_excluded():
    # 扫描件 OCR pages 路径（非 native kind）→ 即便文件名像 BOQ 也不处理（留 R3）
    assert is_boq("已标价工程量清单.pdf", "项目编码 综合单价 合价 合计", kind="pdf_scan") is False
    assert is_boq("已标价工程量清单.pdf", "x", kind="pdf_text") is True


# ── 投标总价候选打分（扉页真总价 vs 后部局部小计）──────────────────────────────


def test_bidtotal_picks_cover_not_local_subtotal():
    s = extract_boq_summary("1.05 已标价工程量清单.pdf", COVER)
    assert s is not None
    # 选中扉页 381574199.97（grand total），非 p3527 的 851886.14（电梯工程局部）
    assert "投标总价: 381574199.97" in s
    # 大写校验并列
    assert "叁亿捌仟壹佰伍拾柒万肆仟壹佰玖拾玖元玖角柒分" in s
    # 全部候选列出供人核
    assert "投标总价全部候选" in s


def test_bidtotal_picks_max_not_sequence_number():
    # reviewer F1：投标总价邻近窗口混入序号(6位整数)，应取最大金额(总价)非首个(序号)
    body = (
        "### 文件: x.pdf\n【第 1 页】\n投标总价(小写):\n040501\n381574199.97\n大写\n叁亿元整\n"
    )
    s = extract_boq_summary("已标价工程量清单.pdf", body)
    assert s is not None
    assert "投标总价: 381574199.97" in s
    assert "投标总价: 040501" not in s


def test_bidtotal_integer_total_extracted():
    # 整数投标总价（无小数无逗号）也要抽出（宽松档，critic F1）
    body = "### 文件: x.pdf\n【第 1 页】\n投标总价(小写):\n4950000\n大写\n肆佰玖拾伍万元整\n"
    s = extract_boq_summary("已标价工程量清单.pdf", body)
    assert s is not None and "4950000" in s


# ── 金额排除项目编码 ──────────────────────────────────────────────────────────


def test_project_code_not_in_topn():
    # 12 位项目编码 040501004012 是纯整数 → 严格档排除，不进 Top-N / 合计
    s = extract_boq_summary("1.05 已标价工程量清单.pdf", COVER)
    assert "040501004012" not in s


# ── 各类合计降序 + 计数 ───────────────────────────────────────────────────────


def test_subtotals_listed_with_count():
    s = extract_boq_summary("1.05 已标价工程量清单.pdf", COVER)
    assert "各类合计(共" in s
    assert "3012424.9" in s  # 分部分项合计
    assert "3030190.41" in s  # 合计


# ── table 段无页号不继承末页（codex P1#4）──────────────────────────────────────


def test_table_tail_amount_gets_unknown_page():
    # blocks 段(p1 锚点) + 远超 carry 行距的无锚点 tables 尾段含金额 → 该金额页号 = 页未知
    head = "### 文件: 已标价工程量清单.pdf\n【第 1 页】\n投标总价(小写):\n100000.00\n大写\n壹拾万元整\n"
    tail = "\n".join(f"行{i}\t数据" for i in range(400)) + "\n表尾合计\t9999999.00\n"
    s = extract_boq_summary("已标价工程量清单.pdf", head + tail)
    assert s is not None
    # 9999999.00 出现在超 carry 行距的尾段 → 标【页未知】（不继承 p1）
    assert "9999999.00" in s
    lines = s.splitlines()
    idx = next(i for i, ln in enumerate(lines) if "9999999.00" in ln)
    # 其上方最近的页标签应为【页未知】
    page_label = next(lines[j] for j in range(idx, -1, -1) if lines[j].startswith("【"))
    assert page_label == "【页未知】"


# ── 摘要长度上限 ──────────────────────────────────────────────────────────────


def test_summary_respects_max_chars():
    s = extract_boq_summary("已标价工程量清单.pdf", COVER, max_chars=120)
    assert s is not None and len(s) <= 160  # 上限 + 裁减标注
    assert "投标总价" in s  # 优先保总价段


# ── 回落 ──────────────────────────────────────────────────────────────────────


def test_no_key_amounts_returns_none():
    # 无投标总价、无合计 → None（回落截断）
    body = "### 文件: 普通.pdf\n【第 1 页】\n这是一段普通正文没有任何金额结构\n"
    assert extract_boq_summary("普通.pdf", body) is None


# ── R1 协同：摘要可被 R1 parse_corpus 解析、总价页 confirmed ────────────────────


def test_summary_parsable_by_r1_and_total_resolved():
    from server.common.corpus import (
        CorpusIndex,
        existence_ratio,
        normalize_text,
        parse_corpus,
    )

    s = extract_boq_summary("1.05 已标价工程量清单.pdf", COVER)
    assert s is not None
    # 模拟 build_extraction_block 包裹：### 文件: 头 + 摘要 body（R1 据文件头建 segment）
    wrapped = f"### 文件: 1.05 已标价工程量清单.pdf (kind=pdf_text, route=native)\n{s}"
    segs = parse_corpus(wrapped)
    # 页锚点独占行 → R1 能解析出页号（含 p2）
    pages = {seg["page"] for seg in segs}
    assert 2 in pages
    # 模型引「投标总价381,574,199.97」(带逗号) → 规范化后在摘要里逐字命中（resolved）
    idx = CorpusIndex(segs)
    q = normalize_text("投标总价381,574,199.97")
    assert existence_ratio(q, idx.corpus_for("bid")) == 1.0 or existence_ratio(
        q, idx.whole_corpus
    ) == 1.0
