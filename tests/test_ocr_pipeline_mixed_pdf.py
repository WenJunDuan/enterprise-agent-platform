"""混合 PDF（数字页 + 扫描页）整份转云 OCR 触发单测。

背景：classify 以文件级 fonts>0 判 native，整份 PDF 只要有文本层就全判 native，其中扫描页经
pymupdf get_text 抽出空串被静默丢失（张謇 400 页投标含 ~59 页扫描资质/业绩证书 → 底稿缺据 →
评分只能 manual）。修复：检测混合 PDF 且空白页**计数**达阈值（比例兜底小份多扫描件）→ 整份转
云 OCR 补回。计数为主（59 页绝对量不该被 341 数字页稀释成 ratio 0.147）。
"""

from __future__ import annotations

import pytest

import server.ocr.pipeline as pipeline_mod
from server.ocr.pipeline import _blank_page_count, _should_cloud_ocr_mixed_pdf


@pytest.fixture(autouse=True)
def _disable_ocr_cache(monkeypatch):
    import server.ocr.cache as cache

    monkeypatch.setattr(cache, "OCR_CACHE_ENABLED", False)


# ── 纯函数：空白页计数 / 触发判据 ───────────────────────────────────────────


def test_blank_page_count_counts_empty_and_near_empty():
    blocks = ["正文很长的一页内容" * 5, "", "   ", "x", "另一页正文内容很多" * 5]
    # 空串 + 纯空格 + 极短(<20字符) 都算空白页 → 3
    assert _blank_page_count(blocks) == 3


def test_should_cloud_ocr_triggers_by_count_zhangjian_profile():
    """张謇画像：59 空白 / 400 页（ratio 0.147）→ 计数 59≥10 触发（比例本身够不着）。"""
    blocks = [""] * 59 + ["数字页正文内容很多很多" * 3] * 341
    assert _should_cloud_ocr_mixed_pdf(blocks) is True


def test_should_cloud_ocr_triggers_by_ratio_fallback_small_doc():
    """小份多扫描件：4 空 / 6 页（count 4<10 但 ratio 0.67>0.5）→ 比例兜底触发。"""
    blocks = [""] * 4 + ["数字页正文内容很多" * 3] * 2
    assert _should_cloud_ocr_mixed_pdf(blocks) is True


def test_should_not_cloud_ocr_few_scattered_blanks():
    """大份数字 PDF 个别空白页：2 空 / 400（count<10 且 ratio<0.5）→ 不触发。"""
    blocks = [""] * 2 + ["数字页正文内容很多" * 3] * 398
    assert _should_cloud_ocr_mixed_pdf(blocks) is False


def test_should_not_cloud_ocr_empty_blocks():
    assert _should_cloud_ocr_mixed_pdf([]) is False


def test_thresholds_are_env_tunable(monkeypatch):
    """阈值 env 可灰度：调高计数阈值后张謇画像（59 空）应改为不触发。"""
    monkeypatch.setattr(pipeline_mod, "OCR_BLANK_PAGE_MIN_COUNT", 100)
    monkeypatch.setattr(pipeline_mod, "OCR_BLANK_PAGE_RATIO", 0.9)
    blocks = [""] * 59 + ["数字页正文内容很多" * 3] * 341
    assert _should_cloud_ocr_mixed_pdf(blocks) is False


# ── 集成：_extract_one_raw 分支 ──────────────────────────────────────────────


def _patch_route_and_native(monkeypatch, *, mixed_pdf: bool, blocks: list[str]):
    """让 classify 返回指定 mixed_pdf 的 native pdf_text 路由，native_read 返回指定 blocks。"""
    monkeypatch.setattr(
        pipeline_mod,
        "classify",
        lambda path: {
            "container": "pdf",
            "route": "native",
            "handler": "pdf_text",
            "has_text_layer": True,
            "page_count": len(blocks),
            "mixed_pdf": mixed_pdf,
            "reason": "PDF 含文本层，直抽",
            "path": str(path),
        },
    )
    monkeypatch.setattr(
        pipeline_mod, "native_read", lambda path: {"kind": "pdf_text", "blocks": blocks, "tables": []}
    )
    captured: dict = {}
    monkeypatch.setattr(
        pipeline_mod,
        "_recognize_with_seal",
        lambda path, route, *, run_seal, purpose=None: captured.update(route=route)
        or {**route, "kind": "ocr", "pages": [{"markdown": "云识别内容"}]},
    )
    return captured


def test_mixed_pdf_with_many_blanks_routes_whole_doc_to_cloud_ocr(monkeypatch, tmp_path):
    """混合 PDF + 空白页达阈值 → 整份走云 OCR（fallback handler=pdf_scan）。"""
    captured = _patch_route_and_native(
        monkeypatch, mixed_pdf=True, blocks=[""] * 12 + ["数字页正文" * 5] * 8
    )
    result = pipeline_mod._extract_one_raw(tmp_path / "bid.pdf")
    assert captured["route"]["route"] == "ocr"
    assert captured["route"]["handler"] == "pdf_scan"
    assert result["kind"] == "ocr"


def test_pure_digital_pdf_blank_pages_not_routed_to_cloud(monkeypatch, tmp_path):
    """纯数字 PDF（mixed_pdf=False）即便有很多空白页（真空页/章节分隔）也不转云 OCR。"""
    captured = _patch_route_and_native(
        monkeypatch, mixed_pdf=False, blocks=[""] * 12 + ["数字页正文" * 5] * 8
    )
    result = pipeline_mod._extract_one_raw(tmp_path / "digital.pdf")
    assert captured == {}  # _recognize_with_seal 未被调用
    assert result["kind"] == "pdf_text"


def test_mixed_pdf_below_threshold_stays_native(monkeypatch, tmp_path):
    """混合 PDF 但扫描页很少（count<10 且 ratio<0.5）→ 保持 native 直读，不转云。"""
    captured = _patch_route_and_native(
        monkeypatch, mixed_pdf=True, blocks=[""] * 2 + ["数字页正文" * 5] * 398
    )
    result = pipeline_mod._extract_one_raw(tmp_path / "mostly-digital.pdf")
    assert captured == {}
    assert result["kind"] == "pdf_text"
