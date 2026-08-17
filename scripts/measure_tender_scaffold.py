#!/usr/bin/env python3
"""实测评标脚手架的 token 占用（KD3/AC6：预算取值必须附实测方法与测得值，可复跑）。

    uv run python scripts/measure_tender_scaffold.py

统计进入单次评标 prompt 的**固定**提示词资产：/tender-evaluate 命令文件、tender-eval skill
目录（2026-08-17 起仅 SKILL.md，references 死副本已收敛删除）、输出契约 schema。
中文为主，按 1 字符 ≈ 1 token 计。

不含 CLI 自身的 system prompt 与工具定义（服务端不可观测），故实测值是
``server.tender.injection_budget._SCAFFOLD_RESERVE_TOKENS`` 的**下界**——该常量在实测值之上
留出 CLI 侧余量。任何调低该常量的改动都必须先复跑本脚本，确认没跌破下界。
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

TARGETS = (
    ".claude/commands/tender-evaluate.md",
    ".claude/skills/tender-eval",
    ".claude/contracts/common/audit-result.schema.json",
    ".claude/contracts/tender/criteria.schema.json",
)


def _iter_files(target: pathlib.Path):
    if target.is_dir():
        yield from sorted(p for p in target.rglob("*") if p.is_file())
    elif target.is_file():
        yield target


def main() -> int:
    total = 0
    missing: list[str] = []
    for name in TARGETS:
        target = REPO_ROOT / name
        if not target.exists():
            missing.append(name)
            continue
        for path in _iter_files(target):
            size = len(path.read_text(encoding="utf-8", errors="replace"))
            total += size
            print(f"{size:>8}  {path.relative_to(REPO_ROOT)}")

    print(f"{total:>8}  TOTAL (chars ≈ tokens)")
    if missing:
        # 资产缺失会让测得值偏小，进而诱使别人调低预留——必须显式失败而不是报一个小数字。
        print(f"MISSING: {', '.join(missing)}", file=sys.stderr)
        return 1

    from server.tender.injection_budget import scaffold_tokens

    reserved = scaffold_tokens()
    print(f"{reserved:>8}  _SCAFFOLD_RESERVE_TOKENS (含 CLI 侧余量)")
    if reserved < total:
        print(
            f"FAIL: 预留 {reserved} < 实测下界 {total}——脚手架装不下，"
            "请按实测值上调 TENDER_SCAFFOLD_RESERVE_TOKENS",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    raise SystemExit(main())
