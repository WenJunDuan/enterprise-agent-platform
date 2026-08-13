"""KD1 搬家器（骨架侧）：用界前原文的**逐行切片** + 新增衔接行，拼出瘦身后的 tender-evaluate.md。

保留段一律走 `("keep", (start, end))` 从界前文件原样切片（不手抄，杜绝搬运期改写）；
新增的目标句 / Read 指令 / 简版页锚 / 指向句走 `("new", text)`，是本次唯一的措辞增量。

用法（在仓库根）：`uv run python .ai_state/sprints/2026-08-12-prompt-architecture/evidence/build_skeleton.py <界前文件>`
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TARGET = Path(".claude/commands/tender-evaluate.md")
REF = ".claude/skills/tender-eval/references"

ANCHOR_BRIEF = f"""### 出处页号书写规则（硬性，页锚溯源）· 简版

- 出处**照抄底稿实际出现的坐标系，不得互换、不得臆造**：`【第 N 页】`→写 `文件名 第N页`；`【转换稿第 M 页】`→写 `文件名 转换稿第M页` 并给该条 `evidence_chain` 加 `"page_kind":"converted"`。
- 底稿里该文件**没有页锚**→只写文件名+章节，**不编页号**；`[⚠页号存疑…]` 文件的页号仅供参考、照写。
- 本节是简版，**完整规则以 `{REF}/evidence-citation.md` 为权威**（S2 开头读一次）。"""

FAIL_VISIBLE = """- **细则文件 `Read` 失败（部署缺陷）不得静默续判**：整单降 `manual_review`（`rule_gap`），`explanation` 写明「评分细则文件缺失，本单按骨架规则保守评定」。"""

S1_READ = f"""- **提取细则**：`Read {REF}/s1-criteria-structuring.md`（字段定义、通则层法规 Read、护栏），本步按其执行。"""

S1_GOAL = """- 目标：直读招标文件的**资格审查/初步评审**与**评标办法**，解析为 `extracted_data.criteria`（`eligibility_rules[]`+评分 `items[]`+出处），对齐 `.claude/contracts/tender/criteria.schema.json`，随结论持久化为会话规则。"""

S1_GATE = """- **硬门**：招标文件没写的标准不得臆测补；缺招标文件 / 定位不到资格审查或评标办法 / 通则层缺失 → 相关项降 `manual_review`（`rule_gap`）并写清缺什么。"""

S2_READ = f"""- **先读证据书写细则（一次，S3/S4 沿用不重读）**：`Read {REF}/evidence-citation.md`。"""

S3_READ = f"""- **先读判分细则（一次）**：`Read {REF}/s3-scoring-modes.md`（五种 `score_mode` 的裁决细则、`pending_reason` 取值速查、判 0 与 manual 的范畴边界）。证据书写按 S2 已读的 `evidence-citation.md`。"""

S3_SCORING = """- 资格审查之后，对照 S1 的 `criteria` 逐项判分，写入 `extracted_data.scoring`（每项 `{item, max, score, status, score_mode, basis, …按 mode 的明细}`，`item`/`max`/`score_mode` 与 criteria 对应项一致）；**按该项 `score_mode` 判分的全部细则以 `s3-scoring-modes.md` 为准**。
- ⚠ **硬闸**：凡 `score:null` 的项**必须同时给 `pending_reason`**（缺失或取值不在枚举内 → 整单契约失败）；**取值与各值语义见 `.claude/contracts/common/audit-result.schema.json`**（服务端按该 schema 校验，选最贴切的一个）。`score` 非 null 的项不要写该字段。"""

S4_READ = f"""- **先读汇总细则（一次）**：`Read {REF}/s4-verdict-summary.md`（废标 / 资格独立 gate 与 `confirmed` 闸、一致性二分决断、`verdict` 合成、`explanation` / `policy_refs` / `evidence_chain` 口径与口头总分一致性）——本步的判定与表述一律以该文件为准。"""

S4_OUT = """- 产出：`verdict`（三值）+ `explanation` / `reasons` + 页级 `evidence_chain` + `risk_score`，并把逐项 `scoring`、`eligibility_checks`、`disqualification_hits` 与 `criteria` 一并留在 `extracted_data`。**不要要求或输出 `review_dimension` 字段**（展示维度由前端按 `criteria.items[]` 既有结构化字段派生）。"""

OUT_READ = f"""- **产出 JSON 前先读一次**：`Read {REF}/output-json.md`（`manual_review_reason` 枚举全文、`extracted_data` 字段契约对照、JSON 合法性细则）——下列 1-7 是核心硬门，细则以该文件为准。"""

OUT_POINTERS = """4. `manual_review` 时必须填 `manual_review_reason`（**枚举全文见 `output-json.md`**），并在 `explanation` 写明哪些评分项不能自动判定、缺什么材料、哪条规则无法闭合。
5. `extracted_data` 须含 `eligibility_checks`（最高优先级，先于 `scoring` 产出）、`scoring`、废标走 `disqualification_hits`（独立 gate，**不混入 scoring**），以及 `bidder_info` / `tender_info` 案卷头——**各字段契约对照见 `output-json.md`**。"""

# ("keep", (起,止)) = 界前原文逐行切片；("new", 文本) = 本次新增的衔接/指向/简版行。
PLAN: list[tuple[str, object]] = [
    ("keep", (1, 6)),
    ("new", ANCHOR_BRIEF),
    ("keep", (20, 22)),
    ("new", FAIL_VISIBLE),
    ("keep", (24, 26)),
    ("keep", (28, 29)),
    ("new", S1_READ),
    ("new", S1_GOAL),
    ("new", S1_GATE),
    ("keep", (57, 57)),
    ("new", S2_READ),
    ("keep", (58, 66)),
    ("keep", (68, 68)),
    ("new", S3_READ),
    ("keep", (69, 74)),
    ("new", S3_SCORING),
    ("keep", (103, 103)),
    ("new", S4_READ),
    ("keep", (104, 105)),
    ("new", S4_OUT),
    ("keep", (121, 121)),
    ("new", OUT_READ),
    ("keep", (123, 125)),
    ("new", OUT_POINTERS),
    ("keep", (128, 128)),
    ("keep", (131, 131)),
    ("keep", (134, 138)),
    ("keep", (140, 141)),
]


def join_blocks(blocks: list[str]) -> str:
    """块间默认空行分隔；但相邻两块若同属一个列表（前块末行与后块首行都是列表项）则不插空行。"""
    is_item = re.compile(r"^\s*(-|\d+\.)\s").match
    text = blocks[0]
    for block in blocks[1:]:
        same_list = bool(is_item(text.rsplit("\n", 1)[-1]) and is_item(block))
        text += ("\n" if same_list else "\n\n") + block
    return text


def main() -> int:
    before = Path(sys.argv[1]).read_text(encoding="utf-8").split("\n")
    blocks: list[str] = []
    for kind, payload in PLAN:
        if kind == "keep":
            start, end = payload  # type: ignore[misc]
            blocks.append("\n".join(before[start - 1 : end]).strip("\n"))
        else:
            blocks.append(str(payload).strip("\n"))
    text = join_blocks(blocks) + "\n"
    TARGET.write_text(text, encoding="utf-8")
    size = len(text.encode("utf-8"))
    print(f"{TARGET}: {size}B ({len(text.splitlines())} 行)")
    return 0 if size <= 15_000 else 1


if __name__ == "__main__":
    raise SystemExit(main())
