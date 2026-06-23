#!/usr/bin/env python
"""按需 OCR 单个文件（可选页范围）→ 文本，供评标 agent 核验底稿 / 重识别低清晰页。

为何存在（#8a）：评标默认用服务端预处理的整份 OCR 底稿；当某页扫描/盖章读不清、或需逐字核验
一条证据的真实页码时，agent 可对**指定文件的指定页**按需重识别（含印章 OCR），把"全靠 server
预处理"变成"Claude 按需取证"。复用 server.ocr 的确定性识别（content-sha256 缓存，不重复跑）。

用法：
    uv run python .claude/skills/ocr-page/ocr.py <文件路径> [--pages N-M] [--seal]
    --pages   只输出底稿 ``【第N页】`` 锚点落在该区间的内容（如 7 或 315-320）；缺省=整份
    --seal    该页含印章/证书等，启用印章 OCR 流水线（更慢，仅低清晰页用）

只读：不写任何文件、不改库；失败打印到 stderr 并以非 0 退出（agent 据此判断回落人工）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_PAGE_RE = re.compile(r"^\s*【第\s*(\d+)\s*页】\s*$")


def _slice_pages(body: str, spec: str) -> str:
    """裁剪到 ``【第N页】`` 锚点落在 [lo, hi] 的页；保留文件头行。spec 非法 → 原样返回。"""
    m = re.match(r"(\d+)(?:-(\d+))?$", spec.strip())
    if not m:
        return body
    lo = int(m.group(1))
    hi = int(m.group(2) or lo)
    out: list[str] = []
    cur: int | None = None
    keep = False
    for line in body.splitlines():
        anchor = _PAGE_RE.match(line)
        if anchor:
            cur = int(anchor.group(1))
            keep = lo <= cur <= hi
        if keep or (cur is None and line.startswith("### 文件")):
            out.append(line)
    return "\n".join(out) if out else body


def main() -> None:
    parser = argparse.ArgumentParser(description="按需 OCR 单文件（可选页范围）")
    parser.add_argument("file", help="待识别文件的路径（PDF/图片/Word/Excel/文本）")
    parser.add_argument("--pages", default="", help="页范围 N 或 N-M（底稿【第N页】锚点）")
    parser.add_argument("--seal", action="store_true", help="含印章/低清晰页，启用印章 OCR")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_file():
        print(f"[错误] 文件不存在或非文件：{path}", file=sys.stderr)
        sys.exit(2)

    try:
        from server.ocr.pipeline import _render_body, extract_one
    except Exception as exc:  # noqa: BLE001 - 导入失败明确报错供 agent 回落
        print(f"[错误] 无法加载 OCR 管道：{exc}", file=sys.stderr)
        sys.exit(3)

    try:
        result = extract_one(
            path, run_seal=args.seal, purpose="评标按需核验：完整、逐字还原本页文本与表格"
        )
        body = _render_body(result)
    except Exception as exc:  # noqa: BLE001 - 识别失败回落人工，不崩
        print(f"[错误] OCR 失败：{exc}", file=sys.stderr)
        sys.exit(4)

    if args.pages:
        body = _slice_pages(body, args.pages)
    print(body)


if __name__ == "__main__":
    main()
