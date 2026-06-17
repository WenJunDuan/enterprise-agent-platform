"""CLI 入口：`python -m server.ocr <dir> [--seal]` → stdout 识别底稿 JSON。

供 multi-ocr skill 交互式使用：agent 发**一次** Bash 调用即拿到整个目录的确定性识别产物，
不再逐文件往返。服务端热路径不走这里，而由 `server.ocr.runner` 进程内直接调 pipeline。
"""

from __future__ import annotations

import json
import sys

from server.ocr.pipeline import build_extraction_block, extract_dir


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("-")]
    run_seal = "--seal" in argv
    if len(args) != 1:
        print(json.dumps({"error": "usage: python -m server.ocr <dir> [--seal]"}), file=sys.stderr)
        return 2
    results = extract_dir(args[0], run_seal=run_seal)
    print(json.dumps({"results": results, "block": build_extraction_block(results)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
