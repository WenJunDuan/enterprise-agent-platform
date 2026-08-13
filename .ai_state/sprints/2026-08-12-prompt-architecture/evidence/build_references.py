"""KD1 搬家器：从界前的 tender-evaluate.md 逐行**原文切片**生成 5 个 references 文件。

用脚本切片而非手抄，是为了机械保证"零语义删改"——被搬运的规则行一个字都不会在搬运过程中
被改写。各文件的导语/权威标注是新增的衔接内容，与被搬运原文分开写在 HEADERS 里。

用法（在仓库根）：`uv run python .ai_state/sprints/2026-08-12-prompt-architecture/evidence/build_references.py <界前文件>`
界前文件取 `git show eac2a16:.claude/commands/tender-evaluate.md > /tmp/tender-evaluate.before.md`。
"""

from __future__ import annotations

import sys
from pathlib import Path

REF_DIR = Path(".claude/skills/tender-eval/references")

# 各 references 文件 → [(小节标题, 原文行号区间 inclusive), ...]，行号对齐界前 38,754B 版本。
LAYOUT: dict[str, list[tuple[str, tuple[int, int]]]] = {
    "s1-criteria-structuring.md": [
        ("", (30, 55)),
    ],
    "s3-scoring-modes.md": [
        ("## 评分产出与 pending_reason 硬闸", (75, 76)),
        ("## 按 score_mode 判分（五种方式的裁决细则）", (77, 95)),
    ],
    "s4-verdict-summary.md": [
        ("## 废标 / 资格独立 gate（与逐项评分解耦）", (96, 98)),
        ("## 一致性核验", (99, 99)),
        ("## verdict 合成", (106, 109)),
        ("## 结论表述与依据（explanation / policy_refs / evidence_chain）", (110, 119)),
    ],
    "evidence-citation.md": [
        ("## 出处页号书写规则（硬性，页锚溯源）—— 权威全文", (10, 18)),
        ("## 证据定位准确性（硬要求，定位项必须 = 实际找到的）", (100, 101)),
    ],
    "output-json.md": [
        ("## manual_review_reason 枚举（全文）", (126, 126)),
        ("## extracted_data 字段契约对照", (127, 127)),
        ("## 结论必须钉入的案卷头字段", (132, 132)),
        ("## JSON 合法性与单对象输出", (129, 130)),
    ],
}

HEADERS: dict[str, str] = {
    "s1-criteria-structuring.md": """# S1 · criteria 结构化提取细则（权威版）

> 由 `/tender-evaluate` S1 开头确定性 `Read`（与 `s1-locate-criteria.md` 一并读，各读一次）。
> 命令骨架只留 S1 的目标句与 `rule_gap` 硬门，**criteria 怎么提、字段怎么填以本文件为权威**。
> 本文件含 S1 必做的两个动作：① 直读招标文件解析 criteria；② 读通则层国家法规作法律底座。
""",
    "s3-scoring-modes.md": """# S3 · 逐项评判与五种 score_mode 裁决细则（权威版）

> 由 `/tender-evaluate` S3 开头确定性 `Read`（一次）。资格审查与决断纪律留在命令骨架，
> **逐项怎么判分以本文件为权威**。证据/页锚书写细则见 S2 开头已读的 `evidence-citation.md`，
> 本文件不重复。
""",
    "s4-verdict-summary.md": """# S4 · 废标 gate / 一致性 / verdict 合成与结论表述（权威版）

> 由 `/tender-evaluate` S4 开头确定性 `Read`（一次）。决断总纲与"每袋投标是独立评审单元"
> 留在命令骨架，**废标 gate、一致性二分决断、verdict 合成、explanation / policy_refs /
> evidence_chain 口径以本文件为权威**。
""",
    "evidence-citation.md": """# 证据与页锚书写细则（权威版）

> 由 `/tender-evaluate` S2 开头确定性 `Read`（一次），**S3 / S4 沿用不重复读**。
> 命令骨架头部的页锚规则是三行简版，**两种坐标系的完整判定与书写规则以本文件为权威**。
""",
    "output-json.md": """# 输出 JSON 细则（权威版）

> 由 `/tender-evaluate` 产出最终 JSON **之前**确定性 `Read`（一次）。命令骨架只留输出契约
> 核心（单 JSON、`verdict` 三值、禁 `review_dimension`、措辞口径），**枚举全文、字段契约
> 对照与 JSON 合法性细则以本文件为权威**。
""",
}

# 搬运时只做的两处**非语义**改写：去掉原文的有序列表编号前缀（脱离原编号语境后编号无意义），
# 以及把原文里指向"见 S4"之类的相对措辞保持原样（不改）。编号前缀在 containment 归一化里同样
# 被剥离，故不影响逐行核对。
NUMBERED_PREFIXES = tuple(f"{i}. " for i in range(1, 10))


def slice_lines(src: list[str], span: tuple[int, int]) -> list[str]:
    start, end = span
    out = []
    for raw in src[start - 1 : end]:
        stripped = raw.lstrip()
        if stripped.startswith(NUMBERED_PREFIXES):
            indent = raw[: len(raw) - len(stripped)]
            raw = f"{indent}- {stripped[3:]}"
        out.append(raw)
    return out


def main() -> int:
    before = Path(sys.argv[1]).read_text(encoding="utf-8").split("\n")
    for name, sections in LAYOUT.items():
        chunks = [HEADERS[name].rstrip("\n")]
        for title, span in sections:
            body = "\n".join(slice_lines(before, span)).rstrip("\n")
            chunks.append(f"{title}\n\n{body}" if title else body)
        text = "\n\n".join(chunks) + "\n"
        path = REF_DIR / name
        path.write_text(text, encoding="utf-8")
        print(f"{path}: {len(text.encode('utf-8'))}B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
