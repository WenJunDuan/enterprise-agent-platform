"""编排：目录 → 每文件分类 → 直读/OCR → 组装内联"识别底稿"。不调模型。

这是确定性流水线的单一入口，被 `server.ocr.runner`（进程内）与 `python -m server.ocr`
（交互式）共用。每个文件独立 try，一个文件失败不拖垮整批（标 manual + error）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from server.ocr import OcrError
from server.ocr.classify import classify
from server.ocr.engine import recognize, recognize_seal
from server.ocr.native import native_read

logger = logging.getLogger(__name__)

# 单文件底稿截断上限，防超大扫描件撑爆映射 prompt
MAX_FILE_BLOCK_CHARS = 20000


def _iter_files(case_dir: str) -> list[Path]:
    base = Path(case_dir)
    if not base.is_dir():
        return []
    return [p for p in sorted(base.rglob("*")) if p.is_file()]


def extract_one(path: Path, *, run_seal: bool = False) -> dict:
    """对单个文件分类并按路由直读 / OCR；异常归一为 manual + error。"""
    try:
        route = classify(path)
        if route["route"] == "native":
            return {**route, **native_read(path)}
        if route["route"] == "ocr":
            result = {**route, **recognize(path)}
            if run_seal:
                result["seals"] = recognize_seal(path).get("seals", [])
            return result
        return {**route, "kind": "manual"}
    except OcrError as exc:
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
    if result.get("pages"):
        return "\n".join(page.get("markdown", "") for page in result["pages"])
    if result.get("tables"):
        return _render_tables(result["tables"])
    if result.get("blocks"):
        return "\n".join(result["blocks"])
    return ""


def build_extraction_block(results: list[dict]) -> str:
    """把结构化产物组装成内联文本底稿，供模型做字段映射。"""
    parts: list[str] = []
    for result in results:
        name = Path(result.get("path", "?")).name
        head = f"### 文件: {name} (kind={result.get('kind')}, route={result.get('route')})"
        body = _render_body(result)[:MAX_FILE_BLOCK_CHARS]
        seals = result.get("seals")
        if seals:
            head += f" [检出印章 {len(seals)} 枚]"
        parts.append(f"{head}\n{body}".rstrip())
    return "\n\n".join(parts) or "（无识别内容）"
