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

# 单文件底稿截断上限，防超大扫描件撑爆映射 prompt。可经 env 调大（部署机 136 页合同场景）。
MAX_FILE_BLOCK_CHARS = int(os.getenv("OCR_MAX_FILE_BLOCK_CHARS", "40000"))


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


def _render_body(result: dict) -> str:
    if result.get("error"):
        return f"[识别失败] {result['error']}"
    # pages 仅指 OCR 引擎产物（list[每页 {markdown}]）；native 文件的页数在 page_count，
    # 不在此。isinstance 守卫防止把页数整数误当列表迭代。
    pages = result.get("pages")
    if isinstance(pages, list) and pages:
        return "\n".join(page.get("markdown", "") for page in pages)
    if result.get("tables"):
        return _render_tables(result["tables"])
    if result.get("blocks"):
        return "\n".join(result["blocks"])
    return ""


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
        parts.append(f"{head}\n{body}".rstrip())
    return "\n\n".join(parts) or "（无识别内容）"
