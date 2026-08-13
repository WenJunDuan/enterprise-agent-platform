"""AC1 逐节字节预算复核：按 design.md KD1 的预算表逐节量 tender-evaluate.md。

用法（仓库根）：`uv run python .ai_state/sprints/2026-08-12-prompt-architecture/evidence/section_budget.py`
"""

from __future__ import annotations

from pathlib import Path

TARGET = Path(".claude/commands/tender-evaluate.md")

# (节名, 起始标记, design KD1 预算上界 B)；"头部+页锚简版" 一行预算覆盖前两段，故合并计。
SECTIONS = [
    ("frontmatter+引言", None, None),
    ("页锚简版", "### 出处页号书写规则", None),
    ("执行方式+S0", "## 执行方式", 700),
    ("S1", "### S1 ", 900),
    ("S2", "### S2 ", 2_400),
    ("S3", "### S3 ", 2_800),
    ("S4", "### S4 ", 1_800),
    ("输出契约", "## 输出契约", 2_600),
    ("单投标人边界+参数", "## 单投标人边界", 1_300),
]
HEAD_CAP = 1_200  # 头部+页锚简版
TOTAL_CAP = 13_700
FILE_CAP = 15_000


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    bounds = [0] + [text.index(mark) for _, mark, _ in SECTIONS if mark] + [len(text)]
    ok = True
    head = total = 0
    for (name, _, cap), start, end in zip(SECTIONS, bounds[:-1], bounds[1:], strict=True):
        size = len(text[start:end].encode("utf-8"))
        total += size
        if cap is None:
            head += size
            print(f"{name:>18}: {size:>6}B")
            continue
        verdict = "OK" if size <= cap else f"OVER by {size - cap}"
        ok &= size <= cap
        print(f"{name:>18}: {size:>6}B  cap {cap:>5}  {verdict}")
    for label, size, cap in (
        ("头部+页锚简版", head, HEAD_CAP),
        ("合计", total, TOTAL_CAP),
        ("整文件", len(text.encode("utf-8")), FILE_CAP),
    ):
        verdict = "OK" if size <= cap else f"OVER by {size - cap}"
        ok &= size <= cap
        print(f"{label:>18}: {size:>6}B  cap {cap:>5}  {verdict}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
