"""Phase A.1 语料落盘：底稿 → 每源文件一份带页锚 .txt + manifest.json，PDF 入管线前 qpdf 修复。

为什么要落盘（纠偏令 v2 纠偏令一）：会话前检索永远在"不知道什么重要"时决定模型能看什么，
6 项 `evidence_unresolved` 的材料"投标文件里明明有"。落盘的 corpus 是补证工具面（A.2 的
Grep/Read）唯一能访问的语料——没有它，工具面开了也无处可查。

三条不变量，每条都对应一次实跑教训：

1. **底稿原样**：corpus 是底稿的**切片**，不是二次加工。任何再渲染都会让模型引到一份
   服务端从未注入、页锚也对不上的文本。
2. **派生物不得回流成源文件**：``pipeline._iter_files`` 递归扫 case 目录，而 corpus 就落在
   case 目录内 —— 不清就会让下一轮 OCR 把上一轮的 .txt 当成待识别文件（底稿自我复制 +
   文件清单失真）。故每次 OCR 前先清 corpus。
3. **外部工具缺席不击穿管线**：qpdf 不在镜像里时记 warning 继续，而不是抛错。
"""

from __future__ import annotations

import asyncio
import json
import os
import stat
import uuid
from pathlib import Path

import pytest

from server.common.corpus import file_head_line, page_anchor_text
from server.ocr import pipeline
from server.ocr.pipeline import OcrDocReport
from server.stores import tender_doc_store as store
from server.tender import corpus_materialize as cm
from server.tender import doc_pipeline

# ── 底稿夹具 ──────────────────────────────────────────────────────────────────


def _draft_file(head: str, *pages: tuple[int, str]) -> str:
    """渲染一个文件段：``### 文件: <head>`` + 逐页锚点正文（与 build_extraction_block 同形）。"""
    body = "\n\n".join(f"{page_anchor_text(no)}\n{text}" for no, text in pages)
    return f"{file_head_line(head)}\n{body}"


TENDER_HEAD = "招标文件.pdf (kind=pdf_text, route=native)"
BID_HEAD = "投标文件.pdf (kind=pdf_scan, route=ocr)"
# 页正文必须比 ``pipeline.MAX_BLANK_CHARS`` 长，否则按既有判定它们本身就是空白页
# （这条阈值是复用来的，不为夹具让路）。
TENDER_PAGE_1 = "第一章 评标办法：本项目采用综合评估法，由评标委员会依本章标准逐项打分。"
TENDER_PAGE_2 = "评分表：技术方案 40 分、商务报价 30 分、类似业绩 30 分，合计 100 分。"
BID_PAGE_7 = "营业执照（副本）：统一社会信用代码见正本，经营范围为信息系统集成服务与运维保障。"


@pytest.fixture
def draft() -> str:
    return "\n\n".join(
        [
            _draft_file(TENDER_HEAD, (1, TENDER_PAGE_1), (2, TENDER_PAGE_2)),
            _draft_file(BID_HEAD, (7, BID_PAGE_7), (8, " ")),
        ]
    )


@pytest.fixture
def case_dir(tmp_path: Path) -> Path:
    path = tmp_path / "case-a"
    path.mkdir()
    return path


def _manifest(case_dir: Path) -> dict:
    return json.loads((cm.corpus_dir(case_dir) / cm.MANIFEST_NAME).read_text(encoding="utf-8"))


def _pages_of(manifest: dict, source: str) -> list[dict]:
    return next(entry["pages"] for entry in manifest["files"] if entry["source"] == source)


# ── 落盘形态 ──────────────────────────────────────────────────────────────────


class TestCorpusFiles:
    def test_one_text_file_per_source_document(self, case_dir: Path, draft: str) -> None:
        cm.materialize_corpus(case_dir, draft)

        written = sorted(p.name for p in cm.corpus_dir(case_dir).glob("*.txt"))
        assert written == ["投标文件.pdf.txt", "招标文件.pdf.txt"]
        text = (cm.corpus_dir(case_dir) / "招标文件.pdf.txt").read_text(encoding="utf-8")
        assert page_anchor_text(1) in text and page_anchor_text(2) in text

    def test_body_is_a_verbatim_slice_of_the_draft(self, case_dir: Path, draft: str) -> None:
        """corpus 每一份都必须逐字出现在底稿里——重排/重渲染会让页锚与注入对不上。"""
        cm.materialize_corpus(case_dir, draft)

        for path in cm.corpus_dir(case_dir).glob("*.txt"):
            assert path.read_text(encoding="utf-8") in draft

    def test_file_header_is_kept_with_the_body(self, case_dir: Path, draft: str) -> None:
        """grep 命中后模型要知道这是哪份文件的第几页，文件头是唯一的归属声明。"""
        cm.materialize_corpus(case_dir, draft)

        text = (cm.corpus_dir(case_dir) / "投标文件.pdf.txt").read_text(encoding="utf-8")
        assert text.startswith(file_head_line(BID_HEAD))

    def test_same_named_sources_do_not_overwrite_each_other(self, case_dir: Path) -> None:
        duplicated = "\n\n".join(
            [
                _draft_file("附件.pdf (kind=pdf_text, route=native)", (1, "招标层附件")),
                _draft_file("附件.pdf (kind=pdf_text, route=native)", (1, "投标层附件")),
            ]
        )
        cm.materialize_corpus(case_dir, duplicated)

        bodies = {p.read_text(encoding="utf-8") for p in cm.corpus_dir(case_dir).glob("*.txt")}
        assert len(bodies) == 2, "同名文件被覆盖，第二份语料丢失"

    def test_traversal_in_a_source_name_is_sanitised(self, case_dir: Path) -> None:
        """源文件名来自用户上传（信任边界）：绝不能据此写到 corpus 目录之外。"""
        cm.materialize_corpus(
            case_dir, _draft_file("../../../etc/passwd (kind=text, route=native)", (1, "x"))
        )

        corpus = cm.corpus_dir(case_dir).resolve()
        for path in corpus.rglob("*"):
            assert path.resolve().is_relative_to(corpus)
        assert not (case_dir.parent / "etc").exists()

    def test_empty_draft_writes_nothing(self, case_dir: Path) -> None:
        assert cm.materialize_corpus(case_dir, "") is None
        assert not cm.corpus_dir(case_dir).exists()


class TestManifest:
    def test_one_entry_per_page_with_page_chars_kind(self, case_dir: Path, draft: str) -> None:
        cm.materialize_corpus(case_dir, draft)

        pages = _pages_of(_manifest(case_dir), "招标文件.pdf")
        assert [p["page"] for p in pages] == [1, 2]
        assert all(set(p) == {"page", "chars", "kind"} for p in pages)
        assert pages[0]["chars"] == len(TENDER_PAGE_1)

    def test_manifest_points_back_at_the_corpus_filename(self, case_dir: Path, draft: str) -> None:
        cm.materialize_corpus(case_dir, draft)

        for entry in _manifest(case_dir)["files"]:
            assert (cm.corpus_dir(case_dir) / entry["corpus_file"]).is_file()

    def test_scanned_pages_are_marked_image(self, case_dir: Path, draft: str) -> None:
        """route=ocr 的文件其页来自图像识别——kind 如实写 image，供人判断该不该带图重问。"""
        cm.materialize_corpus(case_dir, draft)

        assert _pages_of(_manifest(case_dir), "投标文件.pdf")[0]["kind"] == "image"

    def test_natively_read_pages_are_marked_text(self, case_dir: Path, draft: str) -> None:
        cm.materialize_corpus(case_dir, draft)

        assert _pages_of(_manifest(case_dir), "招标文件.pdf")[0]["kind"] == "text"

    def test_blank_pages_reuse_the_pipeline_blank_judgement(
        self, case_dir: Path, draft: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """空白页判定必须复用 ``server.ocr.pipeline`` 那一处，不得另造判据。

        判据同源即可机械证明：把 pipeline 的阈值调到 0，原本的空白页立刻不再算空白。
        """
        cm.materialize_corpus(case_dir, draft)
        assert _pages_of(_manifest(case_dir), "投标文件.pdf")[1]["kind"] == "blank"

        monkeypatch.setattr(pipeline, "MAX_BLANK_CHARS", 0)
        cm.materialize_corpus(case_dir, draft)
        assert _pages_of(_manifest(case_dir), "投标文件.pdf")[1]["kind"] != "blank"

    def test_anchorless_file_gets_one_entry_with_null_page(self, case_dir: Path) -> None:
        """native word/excel 整份直读没有页锚——如实记 page=null，不编页号。"""
        body = "资格证明材料汇总：营业执照、资质证书、项目负责人证书，均为原件扫描后附于本册。"
        cm.materialize_corpus(
            case_dir, f"{file_head_line('资格文件.docx (kind=word, route=native)')}\n{body}"
        )

        pages = _pages_of(_manifest(case_dir), "资格文件.docx")
        assert pages == [{"page": None, "chars": len(body), "kind": "text"}]


class TestCorpusIsDerivedNotSource:
    def test_clear_removes_the_previous_round(self, case_dir: Path, draft: str) -> None:
        """corpus 落在 case 目录内，不清就会被下一轮 ``_iter_files`` 当成待识别源文件。"""
        cm.materialize_corpus(case_dir, draft)
        (cm.corpus_dir(case_dir) / "已删除的文件.pdf.txt").write_text("上一轮", encoding="utf-8")

        cm.clear_corpus(case_dir)

        assert not cm.corpus_dir(case_dir).exists()

    def test_clear_only_touches_the_corpus_directory(self, case_dir: Path, draft: str) -> None:
        source = case_dir / "投标文件.pdf"
        source.write_bytes(b"%PDF-1.4 source")
        cm.materialize_corpus(case_dir, draft)

        cm.clear_corpus(case_dir)

        assert source.read_bytes() == b"%PDF-1.4 source"

    def test_clear_is_a_noop_when_nothing_was_written(self, case_dir: Path) -> None:
        cm.clear_corpus(case_dir)  # 不得抛


# ── qpdf 前置检查 ─────────────────────────────────────────────────────────────

_FAKE_QPDF = """#!/usr/bin/env python3
import pathlib, sys

args = [a for a in sys.argv[1:] if not a.startswith("--")]
src = pathlib.Path(args[0])
if "--check" in sys.argv:
    sys.exit(2 if b"DAMAGED" in src.read_bytes() else 0)
if "{mode}" == "fail":
    sys.stderr.write("qpdf: unrecoverable\\n")
    sys.exit(2)
pathlib.Path(args[1]).write_bytes(src.read_bytes().replace(b"DAMAGED", b"REPAIRED"))
sys.exit(0)
"""


@pytest.fixture
def fake_qpdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """装一个真的 qpdf 可执行文件到 PATH：走真实 subprocess，不 mock 掉命令构造与退出码。"""

    def _install(mode: str = "repair") -> Path:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        script = bin_dir / "qpdf"
        script.write_text(_FAKE_QPDF.format(mode=mode), encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        return script

    return _install


class TestQpdfPrecheck:
    def test_damaged_pdf_is_detected_and_repaired_in_place(self, case_dir: Path, fake_qpdf) -> None:
        """实跑第一发现：损坏文件页数报 5 实为 400——不先修，后面全链路都在读一份残缺文档。"""
        fake_qpdf()
        broken = case_dir / "投标文件.pdf"
        broken.write_bytes(b"%PDF-1.4 DAMAGED body")

        report = cm.repair_damaged_pdfs(case_dir)

        assert broken.read_bytes() == b"%PDF-1.4 REPAIRED body"
        assert report.repaired == ("投标文件.pdf",)
        assert report.unrepaired == ()

    def test_intact_pdf_is_left_byte_identical(self, case_dir: Path, fake_qpdf) -> None:
        fake_qpdf()
        intact = case_dir / "招标文件.pdf"
        intact.write_bytes(b"%PDF-1.4 fine")

        report = cm.repair_damaged_pdfs(case_dir)

        assert intact.read_bytes() == b"%PDF-1.4 fine"
        assert report.repaired == () and report.unrepaired == ()

    def test_failed_repair_keeps_the_original(self, case_dir: Path, fake_qpdf) -> None:
        fake_qpdf(mode="fail")
        broken = case_dir / "投标文件.pdf"
        broken.write_bytes(b"%PDF-1.4 DAMAGED body")

        report = cm.repair_damaged_pdfs(case_dir)

        assert broken.read_bytes() == b"%PDF-1.4 DAMAGED body"
        assert report.unrepaired == ("投标文件.pdf",)

    def test_missing_qpdf_degrades_with_a_warning(
        self, case_dir: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """外部工具缺席不能击穿管线：记 warning 继续，绝不抛。"""
        monkeypatch.setenv("PATH", str(case_dir))
        (case_dir / "投标文件.pdf").write_bytes(b"%PDF-1.4 DAMAGED body")

        with caplog.at_level("WARNING"):
            report = cm.repair_damaged_pdfs(case_dir)

        assert report.qpdf_available is False
        assert report.repaired == () and report.unrepaired == ()
        assert "qpdf" in caplog.text

    def test_only_pdfs_are_touched(self, case_dir: Path, fake_qpdf) -> None:
        fake_qpdf()
        other = case_dir / "投标文件.docx"
        other.write_bytes(b"PK\x03\x04 DAMAGED")

        cm.repair_damaged_pdfs(case_dir)

        assert other.read_bytes() == b"PK\x03\x04 DAMAGED"

    def test_symlinks_are_never_followed_out_of_the_case(
        self, case_dir: Path, fake_qpdf, tmp_path: Path
    ) -> None:
        """与 ``_iter_files`` 同一条边界：symlink 一律跳过，防经链接改写 case 外文件。"""
        fake_qpdf()
        outside = tmp_path / "outside.pdf"
        outside.write_bytes(b"%PDF-1.4 DAMAGED outside")
        (case_dir / "link.pdf").symlink_to(outside)

        cm.repair_damaged_pdfs(case_dir)

        assert outside.read_bytes() == b"%PDF-1.4 DAMAGED outside"


# ── 与 doc_pipeline 的接线 ────────────────────────────────────────────────────


def _pid() -> str:
    return f"tp-{uuid.uuid4().hex[:16]}"


class TestDocPipelineWiring:
    """A.1 的落点：上传预热 OCR 一产出底稿，corpus 同步落盘；前置修复早于目录扫描。"""

    @pytest.fixture
    def prewarm(self, monkeypatch: pytest.MonkeyPatch, draft: str):
        """把预热 OCR 换成确定性桩，并记录它被调用时 case 目录的实际状态。"""
        seen: dict[str, object] = {}

        def _fake_prewarm(case_path, **_kw):
            seen["corpus_present_at_ocr_time"] = cm.corpus_dir(case_path).exists()
            return draft, OcrDocReport("ready", (), ())

        monkeypatch.setattr(doc_pipeline, "prewarm_and_report", _fake_prewarm)
        return seen

    def test_project_doc_ocr_materialises_the_corpus(
        self, case_dir: Path, prewarm, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pid = _pid()
        store.upsert_project_doc(
            project_id=pid, tenant="t1", tender_files="[]", ocr_status="running"
        )
        monkeypatch.setattr(doc_pipeline, "extract_project_doc_info", _noop_extract)

        asyncio.run(doc_pipeline.run_project_doc_ocr(pid, str(case_dir), tenant="t1"))

        assert (cm.corpus_dir(case_dir) / cm.MANIFEST_NAME).is_file()
        assert sorted(p.name for p in cm.corpus_dir(case_dir).glob("*.txt")) == [
            "投标文件.pdf.txt",
            "招标文件.pdf.txt",
        ]

    def test_bid_doc_ocr_materialises_the_corpus(self, case_dir: Path, prewarm) -> None:
        pid, bid_id = _pid(), store.new_bid_id()
        store.upsert_bid_doc(
            project_id=pid,
            bid_id=bid_id,
            tenant="t1",
            bidder_name="投标人甲",
            bid_files="[]",
            ocr_status="running",
        )

        asyncio.run(doc_pipeline.run_bid_doc_ocr(pid, bid_id, str(case_dir), tenant="t1"))

        assert (cm.corpus_dir(case_dir) / cm.MANIFEST_NAME).is_file()

    def test_previous_corpus_is_cleared_before_the_scan(
        self, case_dir: Path, prewarm, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """重跑（doc_rerun）时上一轮语料必须先消失，否则会被当成本轮待识别源文件。"""
        pid = _pid()
        store.upsert_project_doc(
            project_id=pid, tenant="t1", tender_files="[]", ocr_status="running"
        )
        monkeypatch.setattr(doc_pipeline, "extract_project_doc_info", _noop_extract)
        cm.corpus_dir(case_dir).mkdir(parents=True)
        (cm.corpus_dir(case_dir) / "上一轮.pdf.txt").write_text("陈旧语料", encoding="utf-8")

        asyncio.run(doc_pipeline.run_project_doc_ocr(pid, str(case_dir), tenant="t1"))

        assert prewarm["corpus_present_at_ocr_time"] is False
        assert not (cm.corpus_dir(case_dir) / "上一轮.pdf.txt").exists()

    def test_damaged_pdfs_are_repaired_before_the_scan(
        self, case_dir: Path, monkeypatch: pytest.MonkeyPatch, fake_qpdf
    ) -> None:
        fake_qpdf()
        pid = _pid()
        store.upsert_project_doc(
            project_id=pid, tenant="t1", tender_files="[]", ocr_status="running"
        )
        monkeypatch.setattr(doc_pipeline, "extract_project_doc_info", _noop_extract)
        broken = case_dir / "招标文件.pdf"
        broken.write_bytes(b"%PDF-1.4 DAMAGED body")
        seen: dict[str, bytes] = {}

        def _fake_prewarm(case_path, **_kw):
            seen["bytes_at_ocr_time"] = broken.read_bytes()
            return "", OcrDocReport("failed", ("招标文件.pdf",), ())

        monkeypatch.setattr(doc_pipeline, "prewarm_and_report", _fake_prewarm)

        asyncio.run(doc_pipeline.run_project_doc_ocr(pid, str(case_dir), tenant="t1"))

        assert seen["bytes_at_ocr_time"] == b"%PDF-1.4 REPAIRED body"

    def test_failed_ocr_writes_no_corpus(
        self, case_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """底稿都没出来就没有语料可落——绝不留一个空 corpus 让模型以为查过了。"""
        pid = _pid()
        store.upsert_project_doc(
            project_id=pid, tenant="t1", tender_files="[]", ocr_status="running"
        )
        monkeypatch.setattr(
            doc_pipeline,
            "prewarm_and_report",
            lambda *_a, **_k: ("（无识别内容）", OcrDocReport("failed", (), ())),
        )

        asyncio.run(doc_pipeline.run_project_doc_ocr(pid, str(case_dir), tenant="t1"))

        assert not cm.corpus_dir(case_dir).exists()
        assert store.get_project_doc(pid, "t1")["ocr_status"] == "failed"

    def test_materialise_failure_never_flips_ocr_status(
        self, case_dir: Path, prewarm, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """落盘是增量能力：磁盘写坏了也不能把一份可用底稿改判成 failed。"""
        pid = _pid()
        store.upsert_project_doc(
            project_id=pid, tenant="t1", tender_files="[]", ocr_status="running"
        )
        monkeypatch.setattr(doc_pipeline, "extract_project_doc_info", _noop_extract)
        monkeypatch.setattr(
            doc_pipeline, "materialize_corpus", _raise_disk_full
        )

        asyncio.run(doc_pipeline.run_project_doc_ocr(pid, str(case_dir), tenant="t1"))

        assert store.get_project_doc(pid, "t1")["ocr_status"] == "ready"


async def _noop_extract(*_args, **_kwargs) -> None:
    """criteria 抽取是一次模型往返，与本文件无关，桩掉。"""


def _raise_disk_full(*_args, **_kwargs):
    raise OSError(28, "No space left on device")
