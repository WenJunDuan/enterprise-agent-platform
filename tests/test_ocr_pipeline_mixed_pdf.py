"""混合 PDF（数字页 + 扫描页）整份转云 OCR 触发单测。

背景：classify 以文件级 fonts>0 判 native，整份 PDF 只要有文本层就全判 native，其中扫描页经
pymupdf get_text 抽出空串被静默丢失（张謇 400 页投标含 ~59 页扫描资质/业绩证书 → 底稿缺据 →
评分只能 manual）。修复：检测混合 PDF 且空白页**计数**达阈值（比例兜底小份多扫描件）→ 整份转
云 OCR 补回。计数为主（59 页绝对量不该被 341 数字页稀释成 ratio 0.147）。
"""

from __future__ import annotations

import pytest

import server.ocr.pipeline as pipeline_mod
from server.ocr import OcrError
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
        pipeline_mod,
        "native_read",
        lambda path: {"kind": "pdf_text", "blocks": blocks, "tables": []},
    )
    captured: dict = {}
    monkeypatch.setattr(
        pipeline_mod,
        "_recognize_with_seal",
        lambda path, route, *, run_seal, purpose=None: (
            captured.update(route=route)
            or {**route, "kind": "ocr", "pages": [{"markdown": "云识别内容"}]}
        ),
    )
    return captured


def test_mixed_pdf_primary_path_subset_ocr_keeps_digital_native(monkeypatch, tmp_path):
    """主路径：混合 PDF 只对扫描页子集云 OCR 回填，数字页保原生直读，不走整份云 OCR。"""
    captured = _patch_route_and_native(
        monkeypatch, mixed_pdf=True, blocks=[""] * 12 + ["数字页正文内容很多" * 3] * 8
    )
    fake_subset = tmp_path / "subset.pdf"
    fake_subset.write_bytes(b"%PDF-fake")
    monkeypatch.setattr(pipeline_mod, "extract_pdf_subset", lambda p, idx: fake_subset)
    seen: dict = {}
    monkeypatch.setattr(
        pipeline_mod,
        "recognize",
        lambda p, *, purpose=None: (
            seen.update(path=p)
            or {"kind": "ocr", "pages": [{"markdown": f"扫描页{i}"} for i in range(12)]}
        ),
    )
    result = pipeline_mod._extract_one_raw(tmp_path / "bid.pdf")
    assert result["kind"] == "pdf_text"  # 仍是 native 产物（数字页保原生）
    assert captured == {}  # 整份云 OCR（_recognize_with_seal）未被调用
    assert seen["path"] == fake_subset  # 只送扫描页子集，不送整份
    assert result["blocks"][0] == "扫描页0"  # 扫描页回填到真实页位
    assert "数字页正文内容很多" in result["blocks"][12]  # 数字页保原生直读
    assert not fake_subset.exists()  # 临时子集文件已删


def test_mixed_pdf_subset_failure_falls_back_to_whole_doc_cloud(monkeypatch, tmp_path):
    """回退：本地抽页失败（extract_pdf_subset→None）→ 整份云 OCR（_recognize_with_seal, pdf_scan）。"""
    captured = _patch_route_and_native(
        monkeypatch, mixed_pdf=True, blocks=[""] * 12 + ["数字页正文" * 5] * 8
    )
    monkeypatch.setattr(pipeline_mod, "extract_pdf_subset", lambda p, idx: None)
    result = pipeline_mod._extract_one_raw(tmp_path / "bid.pdf")
    assert captured["route"]["route"] == "ocr"
    assert captured["route"]["handler"] == "pdf_scan"
    assert result["kind"] == "ocr"


def test_augment_merges_ocr_into_blank_pages_only(monkeypatch, tmp_path):
    """_augment_mixed_pdf_blocks 纯逻辑：OCR 文本按提交顺序回填到空白页真实位，数字页不动。"""
    # 数字页文本须 ≥ MAX_BLANK_CHARS(20) 才不被当空白页；否则会进 blank_indices 触发页数不匹配。
    digital_3 = "数字第三页正文内容" * 3  # 27 字符 ≥ 20
    digital_4 = "数字第四页正文内容" * 3
    native = {"kind": "pdf_text", "blocks": ["", "", digital_3, digital_4], "tables": []}
    route = {"container": "pdf", "route": "native", "handler": "pdf_text", "mixed_pdf": True}
    fake_subset = tmp_path / "s.pdf"
    fake_subset.write_bytes(b"%PDF")
    monkeypatch.setattr(pipeline_mod, "extract_pdf_subset", lambda p, idx: fake_subset)
    monkeypatch.setattr(
        pipeline_mod,
        "recognize",
        lambda p, *, purpose=None: {
            "kind": "ocr",
            "pages": [{"markdown": "扫A"}, {"markdown": "扫B"}],
        },
    )
    result = pipeline_mod._augment_mixed_pdf_blocks(
        tmp_path / "bid.pdf", route, native, purpose="评标"
    )
    assert result["kind"] == "pdf_text"
    assert result["blocks"] == ["扫A", "扫B", digital_3, digital_4]  # 扫描页回填，数字页不动
    assert "扫描页" in result["note"] or "回填" in result["note"]


def test_mixed_pdf_subset_cloud_failure_falls_back_to_whole_doc(monkeypatch, tmp_path):
    """子集云 OCR 失败（OcrError）→ 回退整份云 OCR（与本地抽页失败对称），不归 error。"""
    captured = _patch_route_and_native(
        monkeypatch, mixed_pdf=True, blocks=[""] * 12 + ["数字页正文" * 5] * 8
    )
    fake_subset = tmp_path / "subset.pdf"
    fake_subset.write_bytes(b"%PDF")
    monkeypatch.setattr(pipeline_mod, "extract_pdf_subset", lambda p, idx: fake_subset)

    def boom(p, *, purpose=None):
        raise OcrError("云 job 失败")

    monkeypatch.setattr(pipeline_mod, "recognize", boom)
    result = pipeline_mod._extract_one_raw(tmp_path / "bid.pdf")
    assert captured["route"]["handler"] == "pdf_scan"  # 回退整份云 OCR
    assert result["kind"] == "ocr"
    assert not fake_subset.exists()  # 临时子集已删（finally）


def test_augment_returns_none_on_page_count_mismatch(monkeypatch, tmp_path):
    """云返回页数 ≠ 提交扫描页数 → 放弃按 offset 回填（会错位），返回 None 让调用方回退整份云。"""
    digital = "数字页正文内容很多很多很多很多很多"  # ≥20 字符，不计入空白页
    native = {"kind": "pdf_text", "blocks": ["", "", digital, digital], "tables": []}
    route = {"container": "pdf", "route": "native", "handler": "pdf_text", "mixed_pdf": True}
    fake_subset = tmp_path / "s.pdf"
    fake_subset.write_bytes(b"%PDF")
    monkeypatch.setattr(pipeline_mod, "extract_pdf_subset", lambda p, idx: fake_subset)
    # 提交 2 个空白页，但云只返回 1 页 → 不匹配
    monkeypatch.setattr(
        pipeline_mod,
        "recognize",
        lambda p, *, purpose=None: {"kind": "ocr", "pages": [{"markdown": "只有一页"}]},
    )
    result = pipeline_mod._augment_mixed_pdf_blocks(
        tmp_path / "bid.pdf", route, native, purpose=None
    )
    assert result is None


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
