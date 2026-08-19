"""agency 生产可见性：把双侧上传目录的 corpus 汇集到**本次评标** case 的 corpus/。

缺口（sprint proposals P1 首条）：Phase A 的语料落在 ``doc_pipeline`` 处理的**上传目录**，
而评标会话拿到的 ``corpus_root`` 是**评标提交目录**——两个不同路径。生产 doc-layer 路径下
``TENDER_AGENCY=1`` 时模型 grep 的是空目录，开关等于空转。

三条不变量，每条都对应一次可预见的事故：

1. **双侧可 grep**：招标侧与本投标侧的语料都要在同一个可 grep 面里——跨文件矛盾（声明函↔
   报价）对单侧语料是结构盲区。
2. **跨投标人零可见**：A 家评标会话绝不能 grep 到 B 家语料。汇集只取**当前 bid_id** 那一家，
   落点是本次评标 case 目录内，路径闸（``agent_bridge`` corpus hook）据此钉死。
3. **派生物不得回流成源文件**：corpus 落在 case 目录内，而 inline OCR 回落路径会递归扫该
   目录——重试同一 request_id 时上一轮的 .txt 会被当成待识别源文件（底稿自我复制）。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from server.common.agent_bridge import AgentRunMeta, build_options
from server.common.corpus import file_head_line, page_anchor_text
from server.tender import agency_corpus, doc_layer, runner
from server.tender import corpus_materialize as cm

# ── 夹具 ──────────────────────────────────────────────────────────────────────

TENDER_HEAD = "招标文件.pdf (kind=pdf_text, route=native)"
BID_HEAD = "投标文件.pdf (kind=pdf_scan, route=ocr)"
OTHER_BID_HEAD = "投标文件-乙.pdf (kind=pdf_scan, route=ocr)"

TENDER_PAGE = "第一章 评标办法：本项目采用综合评估法，由评标委员会依本章标准逐项打分。"
BID_A_PAGE = "投标函：甲科技有限公司响应本项目全部要求，投标报价为人民币玖佰捌拾万元整。"
BID_B_MARK = "乙工程有限公司的商务报价明细与技术偏离表，属于另一家投标人的独有语料。"


def _draft(head: str, page_no: int, text: str) -> str:
    """渲染一个文件段（与 ``build_extraction_block`` 同形：文件头 + 页锚 + 正文）。"""
    return f"{file_head_line(head)}\n{page_anchor_text(page_no)}\n{text}"


def _upload_case(root: Path, name: str, head: str, page_no: int, text: str) -> Path:
    """造一个"上传目录 + 已落盘 corpus"，等价于 doc_pipeline 跑完 A.1 之后的形态。"""
    case_dir = root / name
    case_dir.mkdir(parents=True)
    (case_dir / "audit-request.json").write_text("{}", encoding="utf-8")
    cm.materialize_corpus(case_dir, _draft(head, page_no, text))
    return case_dir


@pytest.fixture
def project_tree(tmp_path: Path) -> dict[str, Path]:
    """一个招标项目下的四个 case 目录：招标层、A 家、B 家，以及 A 家的评标提交目录。"""
    root = tmp_path / "acme" / "tender" / "tp-1"
    tender_case = _upload_case(root, "tender-doc", TENDER_HEAD, 1, TENDER_PAGE)
    bid_a_case = _upload_case(root, "bid-a", BID_HEAD, 7, BID_A_PAGE)
    bid_b_case = _upload_case(root, "bid-b", OTHER_BID_HEAD, 7, BID_B_MARK)
    eval_case = root / "eval-a"
    eval_case.mkdir()
    return {
        "tender": tender_case,
        "bid_a": bid_a_case,
        "bid_b": bid_b_case,
        "eval": eval_case,
    }


def _assemble(tree: dict[str, Path], *, bid: str = "bid_a") -> agency_corpus.AgencyCorpus | None:
    return agency_corpus.assemble_case_corpus(
        tree["eval"],
        tender_case_path=str(tree["tender"]),
        bid_case_path=str(tree[bid]),
    )


def _texts_under(root: Path) -> str:
    return "".join(p.read_text(encoding="utf-8") for p in sorted(Path(root).rglob("*.txt")))


# ── 汇集形态 ──────────────────────────────────────────────────────────────────


class TestAssembleBothSides:
    def test_both_sides_land_under_the_eval_case_corpus(self, project_tree) -> None:
        assembled = _assemble(project_tree)

        assert assembled is not None
        assert assembled.root == cm.corpus_dir(project_tree["eval"])
        assert (assembled.root / "tender" / "招标文件.pdf.txt").is_file()
        assert (assembled.root / "bid" / "投标文件.pdf.txt").is_file()

    def test_copied_text_is_the_draft_verbatim_with_page_anchors(self, project_tree) -> None:
        """corpus 是底稿切片而非再加工——引用页锚必须与服务端注入的那份逐字一致。"""
        assembled = _assemble(project_tree)

        copied = (assembled.root / "bid" / "投标文件.pdf.txt").read_text(encoding="utf-8")
        source = (cm.corpus_dir(project_tree["bid_a"]) / "投标文件.pdf.txt").read_text(
            encoding="utf-8"
        )
        assert copied == source
        assert page_anchor_text(7) in copied and BID_A_PAGE in copied

    def test_manifest_merges_both_sides_with_side_tagged_relative_paths(
        self, project_tree
    ) -> None:
        """补证指引承诺 root 下有 manifest.json；双侧汇集后它必须仍然存在且指得到真文件。"""
        assembled = _assemble(project_tree)

        manifest = json.loads((assembled.root / cm.MANIFEST_NAME).read_text(encoding="utf-8"))
        sides = {entry["side"] for entry in manifest["files"]}
        assert sides == {"tender", "bid"}
        for entry in manifest["files"]:
            assert entry["corpus_file"].startswith(f"{entry['side']}/")
            assert (assembled.root / entry["corpus_file"]).is_file()
            assert entry["pages"], "每页字数/类别应从源 manifest 带过来，不得丢"

    def test_only_corpus_texts_are_copied(self, project_tree) -> None:
        """上传目录里的原件与 sidecar 不进补证面（它只该看语料，不该看提交元数据）。"""
        assembled = _assemble(project_tree)

        copied = {p.name for p in assembled.root.rglob("*") if p.is_file()}
        assert "audit-request.json" not in copied

    def test_rebuild_drops_last_round_leftovers(self, project_tree) -> None:
        """幂等重建：上一轮（含已删源文件）的语料不得混进本轮。"""
        _assemble(project_tree)
        stale = cm.corpus_dir(project_tree["eval"]) / "tender" / "上一轮.txt"
        stale.write_text("过期语料", encoding="utf-8")

        assembled = _assemble(project_tree)

        assert not stale.exists()
        assert (assembled.root / "tender" / "招标文件.pdf.txt").is_file()


class TestAssembleDegradations:
    def test_absent_source_corpus_yields_nothing_instead_of_an_empty_promise(
        self, project_tree, tmp_path
    ) -> None:
        """双侧都没有落盘语料 → 不建目录、返回 None（宁可不承诺，也不指向空目录）。"""
        empty = tmp_path / "no-corpus"
        empty.mkdir()

        assembled = agency_corpus.assemble_case_corpus(
            project_tree["eval"], tender_case_path=str(empty), bid_case_path=None
        )

        assert assembled is None
        assert not cm.corpus_dir(project_tree["eval"]).exists()

    def test_one_side_present_still_assembles_that_side(self, project_tree) -> None:
        assembled = agency_corpus.assemble_case_corpus(
            project_tree["eval"], tender_case_path=str(project_tree["tender"]), bid_case_path=None
        )

        assert assembled is not None and assembled.sides == ("tender",)
        assert (assembled.root / "tender" / "招标文件.pdf.txt").is_file()

    def test_source_equal_to_target_is_left_untouched(self, project_tree) -> None:
        """directory 模式可能直接提交上传目录本身——此时清空重建会把源语料抹掉。"""
        bid_case = project_tree["bid_a"]
        existing = cm.corpus_dir(bid_case) / "投标文件.pdf.txt"

        assembled = agency_corpus.assemble_case_corpus(
            bid_case,
            tender_case_path=str(project_tree["tender"]),
            bid_case_path=str(bid_case),
        )

        assert assembled is None
        assert existing.is_file(), "源语料被自己的重建抹掉了"


# ── 跨投标人隔离 ──────────────────────────────────────────────────────────────


class TestCrossBidderIsolation:
    def test_other_bidders_corpus_never_enters_the_assembled_surface(self, project_tree) -> None:
        assembled = _assemble(project_tree, bid="bid_a")

        assert BID_B_MARK not in _texts_under(assembled.root)
        assert not list(assembled.root.rglob("投标文件-乙.pdf.txt"))

    def test_assembled_root_stays_inside_this_evaluation_case(self, project_tree) -> None:
        """corpus_root 必须落在本次评标 case 内——指到项目公共父目录即等于对全部投标人开放。"""
        assembled = _assemble(project_tree, bid="bid_a")

        assert assembled.root.resolve().is_relative_to(project_tree["eval"].resolve())
        assert not cm.corpus_dir(project_tree["bid_b"]).resolve().is_relative_to(
            assembled.root.resolve()
        )

    def test_manifest_names_no_other_bidder_path(self, project_tree) -> None:
        assembled = _assemble(project_tree, bid="bid_a")

        manifest = (assembled.root / cm.MANIFEST_NAME).read_text(encoding="utf-8")
        assert "bid-b" not in manifest and "投标文件-乙" not in manifest

    def test_path_gate_denies_reading_the_other_bidders_corpus(self, project_tree) -> None:
        """隔离由工具层强制，不靠提示词：闸对 B 家语料必须 deny。"""
        assembled = _assemble(project_tree, bid="bid_a")
        options = build_options(case_root=project_tree["eval"], corpus_root=assembled.root)
        matcher = next(m for m in options.hooks["PreToolUse"] if m.matcher == "Read")
        target = cm.corpus_dir(project_tree["bid_b"]) / "投标文件-乙.pdf.txt"

        decision = asyncio.run(
            matcher.hooks[0](
                {"tool_name": "Read", "tool_input": {"file_path": str(target), "limit": 50}},
                None,
                None,
            )
        )

        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"


# ── 读 doc 层拿双侧上传目录 ───────────────────────────────────────────────────


class TestPrepareFromDocLayer:
    def _rows(self, tree: dict[str, Path], monkeypatch) -> None:
        async def fake_rows(project_id, bid_id, tenant):
            return (
                {"case_path": str(tree["tender"]), "ocr_status": "ready"},
                {"case_path": str(tree["bid_a"]), "ocr_status": "ready"},
            )

        monkeypatch.setattr(doc_layer, "read_doc_rows", fake_rows)

    def test_case_paths_come_from_the_doc_rows(self, project_tree, monkeypatch) -> None:
        self._rows(project_tree, monkeypatch)

        assembled = asyncio.run(
            agency_corpus.prepare_agency_corpus("tp-1", "bid-a", "acme", project_tree["eval"])
        )

        assert assembled is not None and assembled.sides == ("tender", "bid")
        assert BID_A_PAGE in _texts_under(assembled.root)

    def test_missing_bid_id_prepares_nothing(self, project_tree, monkeypatch) -> None:
        """无法定位当前家时绝不退而求其次拼别家语料——宁可没有补证面。"""
        self._rows(project_tree, monkeypatch)

        assembled = asyncio.run(
            agency_corpus.prepare_agency_corpus("tp-1", None, "acme", project_tree["eval"])
        )

        assert assembled is None

    def test_doc_layer_read_failure_never_breaks_the_evaluation(
        self, project_tree, monkeypatch
    ) -> None:
        async def boom(*_a, **_kw):
            raise RuntimeError("db down")

        monkeypatch.setattr(doc_layer, "read_doc_rows", boom)

        assert (
            asyncio.run(
                agency_corpus.prepare_agency_corpus("tp-1", "bid-a", "acme", project_tree["eval"])
            )
            is None
        )


# ── runner 接线 ───────────────────────────────────────────────────────────────


def _fake_meta() -> AgentRunMeta:
    return AgentRunMeta(
        request_id="rid-agency-corpus",
        conversation_id="conv-test",
        claude_session_id="sess-test",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="common/audit-result.schema.json",
        log_file="logs/test.log",
        result_file=None,
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def _run_eval(monkeypatch, tree: dict[str, Path], *, draft: str | None = "底稿") -> dict[str, Any]:
    """跑一次评标（doc 层命中），回传服务端实际发给 SDK 的那套 kwargs。"""
    calls: dict[str, Any] = {}

    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        calls.update(opts)
        return {"verdict": "manual_review"}, _fake_meta()

    async def fake_resolve(project_id, bid_id, tenant):
        from server.tender.doc_context import DocLayerOutcome

        return DocLayerOutcome(text=draft)

    async def fake_rows(project_id, bid_id, tenant):
        return (
            {"case_path": str(tree["tender"]), "ocr_status": "ready"},
            {"case_path": str(tree["bid_a"]), "ocr_status": "ready"},
        )

    monkeypatch.setattr(runner, "run_command_json", fake_run_command_json)
    monkeypatch.setattr(runner, "_resolve_doc_layer", fake_resolve)
    monkeypatch.setattr(runner, "resolve_project_criteria", lambda *_a, **_kw: (None, None))
    monkeypatch.setattr(doc_layer, "read_doc_rows", fake_rows)
    asyncio.run(
        runner.run_tender_evaluation(
            request_id="rid-agency-corpus",
            tenant="acme",
            directory_path=str(tree["eval"]),
            project_id="tp-1",
            bid_id="bid-a",
        )
    )
    return calls


class TestRunnerWiring:
    def test_agency_root_is_populated_with_both_sides(self, project_tree, monkeypatch) -> None:
        """本刀的核心：生产 doc-layer 路径下 corpus_root 不再是空目录。"""
        monkeypatch.setenv("TENDER_AGENCY", "1")

        opts = _run_eval(monkeypatch, project_tree)

        root = opts["corpus_root"]
        assert root == cm.corpus_dir(project_tree["eval"])
        assert TENDER_PAGE in _texts_under(root)
        assert BID_A_PAGE in _texts_under(root)

    def test_bound_root_contains_no_other_bidder_path(self, project_tree, monkeypatch) -> None:
        monkeypatch.setenv("TENDER_AGENCY", "1")

        opts = _run_eval(monkeypatch, project_tree)

        root: Path = opts["corpus_root"]
        assert str(project_tree["bid_b"]) not in str(root)
        assert BID_B_MARK not in _texts_under(root)

    def test_layout_is_described_to_the_model(self, project_tree, monkeypatch) -> None:
        """双侧分目录后，补证指引若仍说 root 下每份一个 .txt，模型的 Read 会全部被闸拒。"""
        monkeypatch.setenv("TENDER_AGENCY", "1")

        context = _run_eval(monkeypatch, project_tree)["context"]

        assert "tender/" in context and "bid/" in context
        assert str(cm.corpus_dir(project_tree["eval"])) in context

    def test_default_off_writes_no_corpus_at_all(self, project_tree, monkeypatch) -> None:
        """对照组逐字不变：开关不开时连语料都不落（磁盘与注入都零变更）。"""
        monkeypatch.delenv("TENDER_AGENCY", raising=False)

        opts = _run_eval(monkeypatch, project_tree)

        assert "corpus_root" not in opts
        assert not cm.corpus_dir(project_tree["eval"]).exists()

    def test_inline_fallback_clears_stale_corpus_before_ocr(
        self, project_tree, monkeypatch
    ) -> None:
        """重试同一 request_id 时，上一轮汇集的 .txt 不得被 inline OCR 当成源文件。"""
        stale = cm.corpus_dir(project_tree["eval"]) / "bid" / "上一轮.txt"
        stale.parent.mkdir(parents=True)
        stale.write_text("上一轮语料", encoding="utf-8")
        scanned: dict[str, bool] = {}

        def fake_ocr(directory_path, *, purpose=None):
            scanned["corpus_present"] = cm.corpus_dir(Path(directory_path)).exists()
            return "底稿"

        monkeypatch.setattr(runner, "ocr_preprocess_block", fake_ocr)
        _run_eval(monkeypatch, project_tree, draft=None)

        assert scanned["corpus_present"] is False
