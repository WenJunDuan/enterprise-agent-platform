"""编排：目录 → 每文件分类 → 直读/OCR → 组装内联"识别底稿"。不调模型。

这是确定性流水线的单一入口，被 `server.ocr.runner`（进程内）与 `python -m server.ocr`
（交互式）共用。每个文件独立 try，一个文件失败不拖垮整批（标 manual + error）。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from server.ocr.classify import classify
from server.ocr.engine import recognize, recognize_seal
from server.ocr.native import native_read

logger = logging.getLogger(__name__)

# 单文件底稿截断上限，防超大扫描件撑爆映射 prompt。默认 200000：评标场景标书动辄上百页
# （华为南通用例 158 页），旧 40000 只够开头几页、正文/业绩被静默砍掉致评标失真。大上下文
# 模型（如 deepseek [1M]）可吃下；本机/小上下文模型经 env OCR_MAX_FILE_BLOCK_CHARS 调小。
MAX_FILE_BLOCK_CHARS = int(os.getenv("OCR_MAX_FILE_BLOCK_CHARS", "200000"))

# P2 置信度门控：OCR 逐块 score 低于此阈值 → 文件标 low（依赖字段须人工复核）。可经 env 调。
OCR_CLARITY_MIN_CONFIDENCE = float(os.getenv("OCR_CLARITY_MIN_CONFIDENCE", "0.6"))

# 低置信/未知清晰度的底稿提示——把"识别不清晰"从事后靠模型猜变成事前显式标注。
_CLARITY_NOTE = {
    "low": " [⚠清晰度低：OCR 部分文本置信度低，依赖本文件的关键字段(金额/日期/单位)请标 needs_review]",
    "unknown": " [清晰度未知：本文件经图像 OCR 但无逐块置信度信号，关键字段请人工抽查]",
}

# P4：是否对 case 目录做确定性 OCR 预处理后注入模型上下文（=0 关闭，回落模型自己 Read）。
OCR_PREPROCESS = os.getenv("OCR_PREPROCESS", "1").lower() in {"1", "true", "yes"}


def _iter_files(case_dir: str) -> list[Path]:
    base = Path(case_dir)
    if not base.is_dir():
        return []
    base_resolved = base.resolve()
    files: list[Path] = []
    for p in sorted(base.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue  # 安全：跳过符号链接，防经 symlink 读取 case 目录外的文件
        try:
            p.resolve().relative_to(base_resolved)  # resolved 必须仍在 base 内
        except ValueError:
            continue
        files.append(p)
    return files


def _recognize_with_seal(path: Path, route: dict, *, run_seal: bool) -> dict:
    """走 OCR 引擎识别（可选印章），合并分诊信息。"""
    result = {**route, **recognize(path)}
    if run_seal:
        result["seals"] = recognize_seal(path).get("seals", [])
    return result


def _has_extractable_text(native: dict) -> bool:
    """native 直读是否抽到非空文本（blocks 或 tables 任一有内容）。"""
    if any(block.strip() for block in native.get("blocks", [])):
        return True
    return any(
        any(str(cell).strip() for cell in row)
        for table in native.get("tables", [])
        for row in table.get("rows", [])
    )


def extract_one(path: Path, *, run_seal: bool = False) -> dict:
    """对单个文件分类并按路由直读 / OCR；任何失败归一为 error（per-file 隔离）。

    - font-only 扫描 PDF（有字体但 native 抽不到文本）回退 OCR，避免返回空结果。
    - 任何异常（损坏文件 / 缺引擎 / 解析错误）归一为 kind=error，单个失败不拖垮整批。
    """
    try:
        route = classify(path)
        if route["route"] == "native":
            native = native_read(path)
            if route.get("handler") == "pdf_text" and not _has_extractable_text(native):
                fallback = {
                    **route,
                    "route": "ocr",
                    "handler": "pdf_scan",
                    "note": "PDF 有字体但无可抽文本，回退 OCR",
                }
                return _recognize_with_seal(path, fallback, run_seal=run_seal)
            return {**route, **native}
        if route["route"] == "ocr":
            return _recognize_with_seal(path, route, run_seal=run_seal)
        return {**route, "kind": "manual"}
    except Exception as exc:  # per-file 隔离：损坏 / 缺引擎 / 解析错误都归一为 error
        logger.warning("extract failed for %s: %s", path, exc)
        return {"path": str(path), "kind": "error", "route": "manual", "error": str(exc)}


def extract_dir(case_dir: str, *, run_seal: bool = False) -> list[dict]:
    """对目录下每个文件跑确定性识别，返回结构化产物列表（不调模型）。"""
    return [extract_one(path, run_seal=run_seal) for path in _iter_files(case_dir)]


def _render_tables(tables: list[dict]) -> str:
    lines: list[str] = []
    for table in tables:
        if table.get("name"):
            lines.append(f"[表: {table['name']}]")
        for row in table.get("rows", []):
            lines.append("\t".join(str(cell) for cell in row))
    return "\n".join(lines)


def _page_anchor(page_no: int) -> str:
    """页锚点：让模型 evidence/basis 能引到底稿真实页（G2 证据定位准确性）。"""
    return f"【第 {page_no} 页】\n"


def _render_body(result: dict) -> str:
    if result.get("error"):
        return f"[识别失败] {result['error']}"
    # pages 仅指 OCR 引擎产物（list[每页 {markdown}]）；native 文件的页数在 page_count，
    # 不在此。isinstance 守卫防止把页数整数误当列表迭代。
    pages = result.get("pages")
    if isinstance(pages, list) and pages:
        # 每页加页锚点（page_number 缺/None 才回退序号；不用 `or` 以免 page_number=0 被吞）。
        return "\n\n".join(
            _page_anchor(pn if (pn := page.get("page_number")) is not None else idx)
            + (page.get("markdown") or "")
            for idx, page in enumerate(pages, start=1)
        )
    # native：blocks(正文) 与 tables(表) 可并存（pdf_text/word 两者都有）→ **都渲染**。
    # 旧逻辑 tables 分支吃掉 blocks 会丢正文；P1 给 pdf_text 加了 find_tables 后更明显，故合并。
    segments: list[str] = []
    blocks = result.get("blocks")
    if blocks:
        # pdf_text 的 blocks 一页一项（read_pdf_text 逐页 append）→ 按页打锚点，跳空页但保留页号，
        # 让模型能引真实页（G2）；其余 kind（word/text）blocks 非页结构，原样拼。
        if result.get("kind") == "pdf_text":
            segments.append(
                "\n\n".join(
                    _page_anchor(i) + b
                    for i, b in enumerate(blocks, start=1)
                    if isinstance(b, str) and b.strip()
                )
            )
        else:
            segments.append("\n".join(blocks))
    if result.get("tables"):
        segments.append(_render_tables(result["tables"]))
    return "\n\n".join(seg for seg in segments if seg.strip())


def file_clarity(result: dict, *, threshold: float = OCR_CLARITY_MIN_CONFIDENCE) -> str:
    """文件级清晰度信号（确定性，不调模型）：clear / low / unknown / failed。

    - error / kind=error → failed
    - OCR 产物：任一页 confidence < threshold → low；全无置信度信号（VLM 端点路径）→ unknown
    - native 直读（数字文件，零 OCR 误差）→ clear

    这是"识别不清晰"的**检测**原语：底稿据此显式标注，下游不再拿糊文本当真。
    """
    if result.get("error") or result.get("kind") == "error":
        return "failed"
    pages = result.get("pages")
    if isinstance(pages, list) and pages:
        confidences = [
            page["confidence"]
            for page in pages
            if isinstance(page, dict)
            and isinstance(page.get("confidence"), (int, float))
            and not isinstance(page.get("confidence"), bool)
        ]
        if not confidences:
            return "unknown"
        return "low" if min(confidences) < threshold else "clear"
    return "clear"


def build_extraction_block(results: list[dict]) -> str:
    """把结构化产物组装成内联文本底稿，供模型做字段映射。

    单文件超过 MAX_FILE_BLOCK_CHARS 时截断并**显式标记**——避免静默丢掉尾部内容
    （如合同付款节点）让模型误以为底稿完整。截断段提示模型对相关字段标 needs_review。
    """
    parts: list[str] = []
    for result in results:
        name = Path(result.get("path", "?")).name
        head = f"### 文件: {name} (kind={result.get('kind')}, route={result.get('route')})"
        full_body = _render_body(result)
        body = full_body[:MAX_FILE_BLOCK_CHARS]
        if len(full_body) > MAX_FILE_BLOCK_CHARS:
            body += (
                f"\n\n...[内容已截断：本文件共 {len(full_body)} 字符，仅保留前 "
                f"{MAX_FILE_BLOCK_CHARS}；尾部信息（如合同付款节点）可能丢失，"
                f"相关字段请标 low_confidence / needs_review]"
            )
        seals = result.get("seals")
        if seals:
            head += f" [检出印章 {len(seals)} 枚]"
        head += _CLARITY_NOTE.get(file_clarity(result), "")
        parts.append(f"{head}\n{body}".rstrip())
    return "\n\n".join(parts) or "（无识别内容）"


def ocr_preprocess_block(case_dir: str, *, skip: set[str] | None = None) -> str | None:
    """P4：对 case 目录做确定性 OCR 预处理，返回内联底稿供注入模型上下文（不调判断模型）。

    OCR_PREPROCESS=0 关闭（回落模型自己 Read）。任何失败 → None（降级，**绝不拖垮**审核/评标）。
    skip：按文件名跳过已单独内联的文件（如 audit-request.json）。**同步**函数，async 调用方须经
    ``asyncio.to_thread`` 调用（含云 OCR，会阻塞事件循环）。
    """
    if not OCR_PREPROCESS:
        return None
    try:
        results = extract_dir(case_dir)
        if skip:
            results = [r for r in results if Path(r.get("path", "")).name not in skip]
        if not results:
            return None
        return build_extraction_block(results)
    except Exception:
        logger.warning("ocr_preprocess 失败 %s（降级回落模型 Read）", case_dir, exc_info=True)
        return None
