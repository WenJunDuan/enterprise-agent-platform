"""AC2 机械核对：界前 tender-evaluate.md 的每一非结构行，必须仍存在于「新骨架 + 5 个
references」的并集里（逐字，允许行首列表符/缩进/编号差异）。

判据来自 design.md AC2：搬家零语义删改。未命中的行必须逐条落在 WHITELIST（页锚简版替换、
枚举语义迁 schema、纯衔接句三类），否则本脚本非零退出。

用法（仓库根）：
  git show eac2a16:.claude/commands/tender-evaluate.md > /tmp/tender-evaluate.before.md
  uv run python .ai_state/sprints/2026-08-12-prompt-architecture/evidence/containment_check.py /tmp/tender-evaluate.before.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

UNION_FILES = [
    Path(".claude/commands/tender-evaluate.md"),
    *(
        Path(".claude/skills/tender-eval/references") / name
        for name in (
            "s1-criteria-structuring.md",
            "s3-scoring-modes.md",
            "s4-verdict-summary.md",
            "evidence-citation.md",
            "output-json.md",
        )
    ),
]

# 行首噪声：缩进 / 列表符 / 有序编号 / markdown 标题井号。归一化后两侧同口径去除。
LEAD = re.compile(r"^[\s>]*(?:[-*+]\s+|\d+\.\s+|#+\s*)*")
# 结构行：frontmatter 分隔符与空行，不承载规则语义。
STRUCTURAL = {"", "---"}

# 未命中白名单：{界前行号: (类别, 理由)}。类别 ∈ 页锚简版替换 / 枚举语义迁 schema / 纯衔接句。
WHITELIST: dict[int, tuple[str, str]] = {
    76: (
        "枚举语义迁 schema",
        "界前 L76 把 pending_reason 硬闸与六个取值的逐值语义写在同一行。搬家后硬闸句、"
        "'score 非 null 不写该字段'、'选最贴切的一个不要用 evidence_unresolved 兜底' 三条行为"
        "规则在 s3-scoring-modes.md 逐字保留，仅**逐值语义**改由同文件速查表承载并标注权威 = "
        "audit-result.schema.json 的 enum + description（KD2 语义单源；review pass1 F3：原写法"
        "使同一份语义在 s3 内重复两份）。语义零丢失，仅换承载位置，故整行不再逐字命中。",
    ),
}


def normalize(line: str) -> str:
    return LEAD.sub("", line).strip()


def main() -> int:
    before = Path(sys.argv[1]).read_text(encoding="utf-8").split("\n")
    union = "\n".join(
        normalize(line) for path in UNION_FILES for line in path.read_text(encoding="utf-8").split("\n")
    )
    missing: list[tuple[int, str]] = []
    checked = 0
    for lineno, raw in enumerate(before, 1):
        norm = normalize(raw)
        if norm in STRUCTURAL:
            continue
        checked += 1
        if norm not in union:
            missing.append((lineno, norm))

    unlisted = [(n, s) for n, s in missing if n not in WHITELIST]
    print(f"界前非结构行: {checked}  未命中: {len(missing)}  白名单覆盖: {len(missing) - len(unlisted)}")
    for lineno, norm in missing:
        tag = f"WHITELIST[{WHITELIST[lineno][0]}]" if lineno in WHITELIST else "UNLISTED"
        print(f"  L{lineno} {tag}: {norm[:70]}")
    stale = sorted(set(WHITELIST) - {n for n, _ in missing})
    for lineno in stale:
        print(f"  L{lineno} STALE_WHITELIST: 该行已命中并集，白名单条目应删除")
    return 0 if not unlisted and not stale else 1


if __name__ == "__main__":
    raise SystemExit(main())
