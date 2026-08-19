"""Phase A.1 语料落盘：底稿切片成可检索的 ``<case>/corpus/``，PDF 入管线前先 qpdf 修复。

**为什么**（纠偏令 v2 纠偏令一）：会话前检索永远在"不知道什么重要"时决定模型能看什么——
实测 6 项 ``evidence_unresolved`` 的材料"投标文件里明明有"，而跨文件矛盾对按项检索是结构
盲区（没有单项查询会同时召回两处）。corpus 是补证工具面（A.2 的 Grep/Read，钉死在本目录）
唯一能访问的语料：工具面是"能查"，corpus 是"有得查"。

**边界**：只做确定性文件操作，不调模型、不写库。产物是**底稿的切片**而非再加工——重排或
重渲染会让模型引到一份服务端从未注入、页锚也对不上的文本。

**corpus 是派生物，不是源文件**：它落在 case 目录内，而 ``pipeline._iter_files`` 递归扫该
目录。因此每次落盘先 :func:`clear_corpus` 重建，OCR 重跑（``doc_rerun``）前也必须先清——
否则上一轮的 .txt 会被当成待识别文件，底稿自我复制、文件清单失真。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, NamedTuple

from server.common.agent_bridge import CORPUS_READ_MAX_LINES
from server.common.corpus import (
    _parse_file_head,
    file_head_line,
    parse_page_anchor,
    split_source_files,
)
from server.ocr import pipeline

logger = logging.getLogger(__name__)

# 语料目录名与清单文件名：落盘端（本模块）与路径闸（``agent_bridge`` 的 corpus PreToolUse
# hook，经 runner 传入的 ``corpus_root``）必须指同一个目录，故只在此定义一次。
CORPUS_DIR_NAME = "corpus"
MANIFEST_NAME = "manifest.json"

# 文件头里的路由标记：``### 文件: x.pdf (kind=pdf_scan, route=ocr)``。
_ROUTE_RE = re.compile(r"route=([A-Za-z_]+)")
# 落盘文件名消毒：源文件名来自用户上传（信任边界）。目录部分由 ``Path().name`` 剥掉，
# 这里再把路径/通配/控制字符换成下划线，杜绝据此写到 corpus 目录之外。
_UNSAFE_NAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

# qpdf 前置检查（参照实跑第一发现：损坏文件页数报 5 实为 400——不先修，后面整条链路都在
# 读一份残缺文档）。退出码语义见 qpdf 手册：0=无问题，2=有错误，3=仅警告。
QPDF_BINARY = "qpdf"
QPDF_TIMEOUT_SEC = 120
_QPDF_CHECK_DAMAGED = 2
_QPDF_WRITE_OK = frozenset({0, 3})


def corpus_dir(case_dir: str | Path) -> Path:
    """本案语料目录 ``<case>/corpus/``（落盘端与工具面路径闸的唯一约定）。"""
    return Path(case_dir) / CORPUS_DIR_NAME


def clear_corpus(case_dir: str | Path) -> None:
    """清掉本案上一轮语料。

    OCR 重跑前必须调用：corpus 是派生物，留在 case 目录里会被下一轮 ``_iter_files``
    当成待识别源文件（见模块 docstring）。未落盘过时是空操作。
    """
    shutil.rmtree(corpus_dir(case_dir), ignore_errors=True)


def agency_context_block(corpus_root: str | Path) -> str:
    """补证指引（仅 ``TENDER_AGENCY=1`` 时追加在注入末尾，见 ``runner``）。

    初始注入**不变**——这段只说"注入之外还能怎么查"，不改模型对已注入片段的处置。

    Args:
        corpus_root: 本案语料目录；渲染成绝对路径，模型据此拼 Read 的 ``file_path``。
    """
    root = Path(corpus_root).resolve()
    return (
        "\n\n=== 补证工具（按需用，不是必走步骤）===\n"
        f"以上未注入的材料**不等于**投标人未提供：本案完整底稿已按源文件落在 {root}/"
        f"（每份一个 .txt，{MANIFEST_NAME} 列出每页字数与 text/image/blank）。\n"
        f"补证方式：先 Grep 在该目录内定位，再 Read 按行区间取原文（单次不超过 "
        f"{CORPUS_READ_MAX_LINES} 行）；这两个工具只能访问该目录，越界会被拒绝。\n"
        "引用页码取所读文本里的【第N页】页锚，不是文件正文的印刷页号；"
        "补证后仍未定位到的项按决策表原判，不因为查过就改判。\n"
    )


# ── 落盘 ──────────────────────────────────────────────────────────────────────


def _source_name(head: str) -> str:
    """从文件头串取纯文件名。

    走 ``corpus._parse_file_head``（底稿协议的解析单点）而不是自己切 ``(kind=``：切法
    在两处各写一份，加一个新标记就会静默分叉（该函数 docstring 记的正是这条教训）。
    """
    return _parse_file_head(head)[0]


def _route_of(head: str) -> str:
    match = _ROUTE_RE.search(head)
    return match.group(1) if match else ""


def _corpus_filename(source: str, used: set[str]) -> str:
    """把源文件名转成 corpus 目录内安全且唯一的 ``.txt`` 名。"""
    base = _UNSAFE_NAME_RE.sub("_", Path(source).name).strip(". ") or "source"
    candidate = f"{base}.txt"
    index = 2
    while candidate in used:
        candidate = f"{base}-{index}.txt"
        index += 1
    used.add(candidate)
    return candidate


def _split_pages(body: str) -> list[tuple[int | None, str]]:
    """把一个文件段的正文按页锚切成 ``[(页号, 该页原文)]``。

    无页锚的文件（native word/excel 整份直读）返回单条 ``page=None``——如实记，不编页号。
    锚点之前的空前言不成页（它不带任何内容），但**带锚的空白页要保留**：那正是
    manifest 要如实呈现的 ``blank``。
    """
    pages: list[tuple[int | None, list[str]]] = []
    for line in body.splitlines():
        anchor = parse_page_anchor(line)
        if anchor is not None:
            pages.append((anchor[0], []))
            continue
        if not pages:
            pages.append((None, []))
        pages[-1][1].append(line)
    return [
        (page, "\n".join(lines))
        for page, lines in pages
        if page is not None or "\n".join(lines).strip()
    ]


def _page_kind(page_text: str, route: str) -> str:
    """该页在 manifest 里的类别：``blank`` / ``image`` / ``text``。

    空白判定**复用** ``pipeline`` 那一处（``MAX_BLANK_CHARS`` 阈值 + 同一条谓词）——另造
    判据会让"底稿里算空白"与"清单里算空白"在同一页上给出不同答案。
    ``image`` = 该文件整份走图像识别（``route=ocr``）：底稿不带逐页来源，故按文件级路由如实标。
    """
    if pipeline._blank_page_count([page_text]) == 1:
        return "blank"
    return "image" if route == "ocr" else "text"


def _file_manifest(head: str, body: str, corpus_file: str) -> dict[str, Any]:
    route = _route_of(head)
    return {
        "source": _source_name(head),
        "corpus_file": corpus_file,
        "route": route,
        "pages": [
            {"page": page, "chars": len(text.strip()), "kind": _page_kind(text, route)}
            for page, text in _split_pages(body)
        ],
    }


def materialize_corpus(case_dir: str | Path, draft_text: str) -> Path | None:
    """把已渲染的底稿按源文件切片落到 ``<case>/corpus/``，并写 ``manifest.json``。

    Args:
        case_dir: 本案目录（上传落盘目录 / 评标目录）。
        draft_text: ``build_extraction_block`` 产的底稿全文（带 ``### 文件:`` 头与页锚）。

    Returns:
        manifest 路径；底稿为空或不含任何文件头时返回 ``None``（不建目录）。
    """
    segments = [(head, body) for head, body in split_source_files(draft_text or "") if head]
    if not segments:
        return None
    target = corpus_dir(case_dir)
    clear_corpus(case_dir)  # 幂等重建：上一轮残留（含已删源文件的语料）不得混进本轮
    target.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    files: list[dict[str, Any]] = []
    for head, body in segments:
        corpus_file = _corpus_filename(_source_name(head), used)
        # 底稿原样：文件头 + 正文逐字回写，让 grep 命中处自带归属声明与页锚。
        (target / corpus_file).write_text(f"{file_head_line(head)}\n{body}", encoding="utf-8")
        files.append(_file_manifest(head, body, corpus_file))
    manifest = target / MANIFEST_NAME
    manifest.write_text(
        json.dumps({"case": Path(case_dir).name, "files": files}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("tender_corpus_materialized", extra={"case_dir": str(case_dir), "n": len(files)})
    return manifest


# ── qpdf 前置修复 ─────────────────────────────────────────────────────────────


class PdfRepairReport(NamedTuple):
    """一次 qpdf 前置检查的结果（供日志与调用方观测，不进结论）。

    Attributes:
        qpdf_available: 本机/镜像里是否有 qpdf 可执行文件。
        repaired: 检出损坏并已重写的文件名。
        unrepaired: 检出损坏但重写失败、仍按原件进管线的文件名。
    """

    qpdf_available: bool
    repaired: tuple[str, ...]
    unrepaired: tuple[str, ...]


def _case_pdfs(case_dir: Path) -> list[Path]:
    """case 目录内的 PDF（与 ``pipeline._iter_files`` 同一条边界：跳 symlink、resolve 后仍须在案内）。"""
    if not case_dir.is_dir():
        return []
    base = case_dir.resolve()
    pdfs: list[Path] = []
    for path in sorted(case_dir.rglob("*")):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".pdf":
            continue
        try:
            path.resolve().relative_to(base)
        except ValueError:
            continue
        pdfs.append(path)
    return pdfs


def _run_qpdf(*args: str) -> subprocess.CompletedProcess[bytes] | None:
    """跑一次 qpdf（列表 argv，不过 shell）；超时/系统级失败返回 ``None``。"""
    try:
        return subprocess.run(  # noqa: S603 - argv 列表，路径来自目录枚举而非用户字符串
            [QPDF_BINARY, *args], capture_output=True, timeout=QPDF_TIMEOUT_SEC, check=False
        )
    except (OSError, subprocess.SubprocessError):
        logger.warning("qpdf_invocation_failed", extra={"qpdf_args": args}, exc_info=True)
        return None


def _rewrite_pdf(pdf: Path) -> bool:
    """用 qpdf 重写一份损坏 PDF，成功才原地替换。

    临时文件落在 case 目录**之外**（同盘的上一级），因此崩溃残留不会被 OCR 当成源文件；
    重写失败一律保留原件——修不好也比换成半份好，per-file 隔离由 OCR 侧兜底。
    """
    fd, tmp_name = tempfile.mkstemp(dir=pdf.parent.parent, prefix=".qpdf-", suffix=".pdf")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        result = _run_qpdf(str(pdf), str(tmp))
        if result is None or result.returncode not in _QPDF_WRITE_OK or tmp.stat().st_size == 0:
            return False
        shutil.copymode(pdf, tmp)  # 别把上传件的权限换成 mkstemp 的 0600
        os.replace(tmp, pdf)
        return True
    finally:
        tmp.unlink(missing_ok=True)


def repair_damaged_pdfs(case_dir: str | Path) -> PdfRepairReport:
    """PDF 入管线前置：``qpdf --check`` 检出损坏的先修复。

    qpdf 缺席时**记 warning 继续**——外部工具不在镜像里不该击穿整条管线（此时损坏文件
    仍按原样进 OCR，页数失真的老行为不变，但日志里有痕）。

    Args:
        case_dir: 本案目录。

    Returns:
        :class:`PdfRepairReport`。
    """
    pdfs = _case_pdfs(Path(case_dir))
    if shutil.which(QPDF_BINARY) is None:
        if pdfs:
            logger.warning(
                "qpdf_unavailable_skipping_pdf_precheck",
                extra={"case_dir": str(case_dir), "pdf_count": len(pdfs)},
            )
        return PdfRepairReport(False, (), ())
    repaired: list[str] = []
    unrepaired: list[str] = []
    for pdf in pdfs:
        check = _run_qpdf("--check", str(pdf))
        if check is None or check.returncode != _QPDF_CHECK_DAMAGED:
            continue
        (repaired if _rewrite_pdf(pdf) else unrepaired).append(pdf.name)
    if repaired or unrepaired:
        logger.warning(
            "qpdf_repaired_damaged_pdfs",
            extra={"case_dir": str(case_dir), "repaired": repaired, "unrepaired": unrepaired},
        )
    return PdfRepairReport(True, tuple(repaired), tuple(unrepaired))
