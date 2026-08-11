"""H2 页锚溯源 · 回查闸升级（KD5，AC4/AC5）。

旧行为：``page_mismatch`` 只计数、不纠正、不降级 → 错页畅通进结论；无页锚文件（native word/excel
直读）里 prompt 硬要求"第N页"，模型只能臆造，而 ``page_status`` 把 key=0（无锚段）当第 0 页、
window=1 命中 → **第 1 页恒 confirmed**，臆造值被盖章为已核实。
"""

from __future__ import annotations

from server.common.corpus import (
    CorpusIndex,
    locate_quote_pages,
    normalize_text,
    page_status,
    parse_corpus,
    rewrite_source_page,
)
from server.tender.evidence import resolve_audit_evidence

_ANCHORED = (
    "### 文件: 投标文件.pdf (kind=pdf_text, route=native)\n"
    "【第 1 页】\n封面 投标人某某建设集团有限公司\n"
    "【第 6 页】\n拟派项目负责人张三 建造师注册编号A12345\n"
    "【第 9 页】\n业绩一览 某某高速公路路基工程 合同金额一亿元\n"
)

_NO_ANCHOR = (
    "### 文件: 技术方案.docx (kind=word, route=native)\n"
    "本方案采用双掺技术处理软基 施工组织设计说明如下\n"
)


def _index(corpus: str) -> CorpusIndex:
    return CorpusIndex(parse_corpus(corpus))


def _chain_output(source: str, finding: str) -> dict:
    return {
        "verdict": "approved",
        "evidence_chain": [{"source": source, "finding": finding, "conclusion": "核对一致"}],
        "extracted_data": {},
    }


# ── AC5：无页锚文件不再"第 1 页恒 confirmed" ──────────────────────────────────


def test_no_anchor_file_is_not_confirmed_by_a_fabricated_page_one():
    index = _index(_NO_ANCHOR)
    quote = normalize_text("本方案采用双掺技术处理软基")
    assert page_status(index, "whole", 1, quote) != "confirmed"


def test_no_anchor_file_quote_resolves_at_file_level():
    index = _index(_NO_ANCHOR)
    quote = normalize_text("本方案采用双掺技术处理软基")
    assert page_status(index, "whole", None, quote) == "no_page"
    assert page_status(index, "whole", 1, quote) == "file_level"


def test_anchored_file_keeps_strict_page_confirmation():
    index = _index(_ANCHORED)
    quote = normalize_text("拟派项目负责人张三")
    assert page_status(index, "bid", 6, quote) == "confirmed"


# ── AC4：page_mismatch 就地纠正 / 多处命中降级 ────────────────────────────────


def test_locate_quote_pages_returns_anchored_hits_only():
    index = _index(_ANCHORED + _NO_ANCHOR)
    quote = normalize_text("某某高速公路路基工程")
    assert locate_quote_pages(index, "bid", quote) == [("投标文件.pdf", 9)]


def test_rewrite_source_page_preserves_artifact_prefix():
    assert rewrite_source_page("投标文件.pdf 第 3 页", 9) == "投标文件.pdf 第 9 页"
    assert rewrite_source_page("投标文件.docx 转换稿第 3 页", 9) == "投标文件.docx 转换稿第 9 页"


def test_unique_hit_on_other_page_is_corrected_in_place():
    """AC4：quote 唯一命中他页 → source 页号就地纠正 + 记 page_corrected。"""
    out = _chain_output("投标文件.pdf 第 3 页", "业绩一览 某某高速公路路基工程 合同金额一亿元")
    resolve_audit_evidence(out, _ANCHORED)

    item = out["evidence_chain"][0]
    assert item["source"] == "投标文件.pdf 第 9 页"
    assert item["resolution"]["page"] == "page_corrected"
    assert item["resolution"]["page_corrected"] == {"from": 3, "to": 9}


def test_ambiguous_hits_are_marked_unverified_and_warned():
    """多处命中 → 不猜，降 page_unverified 并计入结论 warnings。"""
    corpus = (
        "### 文件: 投标A.pdf (kind=pdf_text)\n【第 2 页】\n共同的关键承诺原文内容一致\n"
        "### 文件: 投标B.pdf (kind=pdf_text)\n【第 2 页】\n共同的关键承诺原文内容一致\n"
    )
    out = _chain_output("投标文件 第 2 页", "共同的关键承诺原文内容一致")
    resolve_audit_evidence(out, corpus)

    item = out["evidence_chain"][0]
    assert item["resolution"]["page"] == "page_unverified"
    warnings = out["extracted_data"]["validation_warnings"]
    assert any(w["code"] == "evidence_page_unverified" for w in warnings)


def test_page_unreliable_file_downgrades_all_its_evidence_pages():
    """云页数守卫触发 → 该文件证据页号全部 page_unverified（页号本身不可信，纠正也无意义）。"""
    corpus = (
        "### 文件: 扫描件.pdf (kind=ocr, route=ocr)"
        " [⚠页号存疑：云 OCR 返回 1 页、文档 5 页，页码仅供参考]\n"
        "【第 1 页】\n资质证书 建筑工程施工总承包一级\n"
    )
    out = _chain_output("扫描件.pdf 第 1 页", "资质证书 建筑工程施工总承包一级")
    resolve_audit_evidence(out, corpus)

    item = out["evidence_chain"][0]
    assert item["resolution"]["status"] == "resolved"
    assert item["resolution"]["page"] == "page_unverified"
    assert any(
        w["code"] == "evidence_page_unverified"
        for w in out["extracted_data"]["validation_warnings"]
    )


def test_correct_page_citation_stays_confirmed_without_warning():
    out = _chain_output("投标文件.pdf 第 6 页", "拟派项目负责人张三 建造师注册编号A12345")
    resolve_audit_evidence(out, _ANCHORED)

    item = out["evidence_chain"][0]
    assert item["resolution"]["page"] == "confirmed"
    assert "page_corrected" not in item["resolution"]
    assert "validation_warnings" not in out["extracted_data"]


def test_no_anchor_file_evidence_without_page_is_accepted():
    """AC5：无页锚文件的出处只要文件名 + 逐字原文即可核实，不因缺页号被判 mismatch。"""
    out = _chain_output("技术方案.docx", "本方案采用双掺技术处理软基 施工组织设计说明如下")
    resolve_audit_evidence(out, _NO_ANCHOR)

    item = out["evidence_chain"][0]
    assert item["resolution"]["status"] == "resolved"
    assert item["resolution"]["page"] == "no_page"


def test_no_anchor_file_evidence_with_fabricated_page_is_flagged_not_confirmed():
    out = _chain_output("技术方案.docx 第 1 页", "本方案采用双掺技术处理软基 施工组织设计说明如下")
    resolve_audit_evidence(out, _NO_ANCHOR)

    item = out["evidence_chain"][0]
    assert item["resolution"]["page"] == "file_level"


def test_converted_source_matches_converted_anchor_coordinates():
    corpus = (
        "### 文件: 投标文件.docx (kind=pdf_text, route=convert, 已转换为PDF识别, 页号为转换稿页号)\n"
        "【转换稿第 4 页】\n拟派项目负责人李四 建造师注册编号B67890\n"
    )
    out = _chain_output("投标文件.docx 转换稿第 4 页", "拟派项目负责人李四 建造师注册编号B67890")
    resolve_audit_evidence(out, corpus)

    item = out["evidence_chain"][0]
    assert item["resolution"]["page"] == "confirmed"
    assert item["page_kind"] == "converted"


def test_scoring_hit_page_correction_is_recorded_too():
    """评分项 award_hits 的出处同样走纠正闸（承重证据，优先级更高）。"""
    out = {
        "verdict": "approved",
        "extracted_data": {
            "scoring": [
                {
                    "item": "类似业绩",
                    "max": 10,
                    "score": 10,
                    "status": "scored",
                    "basis": "有业绩",
                    "award_hits": [
                        {
                            "awarded": 10,
                            "evidence": {
                                "source": "投标文件.pdf 第 2 页",
                                "quote": "业绩一览 某某高速公路路基工程 合同金额一亿元",
                            },
                        }
                    ],
                }
            ]
        },
    }
    resolve_audit_evidence(out, _ANCHORED)

    ev = out["extracted_data"]["scoring"][0]["award_hits"][0]["evidence"]
    assert ev["source"] == "投标文件.pdf 第 9 页"
    assert ev["resolution"]["page_corrected"] == {"from": 2, "to": 9}
