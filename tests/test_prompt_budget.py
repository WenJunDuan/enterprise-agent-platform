"""提示词预算门禁（KD3）：热路径提示词字节上界 + CLAUDE.md 调度实体存在性机械核对。

**超界了怎么办**：不要抬这里的常量。把超界文件里的裁决细则**下沉**到对应 skill 的
`references/` 下（一个细则一档，单档 ≤ ``REFERENCE_FILE_CAP``），并在命令里对应步骤开头写一条
确定性 `Read` 指令拉取——先例见 `.claude/commands/tender-evaluate.md` 的 S1–S4 与
`.claude/skills/tender-eval/references/`。上界确需调整时，走 PR 显式改本文件常量并说明理由
（棘轮机械化：只有改常量这一个入口，防"每出一次事故加一段"把命令重新撑回 38KB）。

上界取值 = 2026-08-12/13 实测字节 + 约 15% 余量；`tender-evaluate.md` 取重构后目标值 15,000。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_DIR = PROJECT_ROOT / ".claude"

# 文件 → 字节上界。实测值见 .ai_state/sprints/2026-08-12-prompt-architecture/design.md「已验证基线」。
PROMPT_BUDGETS: dict[str, int] = {
    ".claude/commands/tender-evaluate.md": 15_000,  # 重构后 12,442（界前 38,754）
    ".claude/commands/tender-compare.md": 8_200,  # 实测 7,132
    ".claude/commands/tender-extract-info.md": 6_800,  # 实测 5,871
    ".claude/commands/audit.md": 5_300,  # 实测 4,584
    ".claude/CLAUDE.md": 9_600,  # KD4 改后实测 8,412
}

# references/ 单文件上界：渐进披露的一档细则应能一次读完，超了说明该拆成两档。
REFERENCE_FILE_CAP = 10_240

# 调度表里出现的实体名（反引号内、形如 `/cmd` 或 `some-entity`）必须能解析到真实文件。
_ENTITY_RE = re.compile(r"`(/?[a-z][a-z0-9-]*)`")


def _byte_size(path: Path) -> int:
    return len(path.read_bytes())


@pytest.mark.parametrize(("rel_path", "cap"), sorted(PROMPT_BUDGETS.items()))
def test_prompt_file_within_byte_budget(rel_path: str, cap: int) -> None:
    path = PROJECT_ROOT / rel_path
    size = _byte_size(path)
    assert size <= cap, (
        f"{rel_path} 已 {size}B，超上界 {cap}B（超 {size - cap}B）。"
        "超界须把裁决细则下沉到对应 skill 的 references/ 并在步骤开头加确定性 Read，"
        "而不是抬高本文件常量；流程见本测试头注。"
    )


def test_reference_files_within_byte_budget() -> None:
    """下沉产物本身也受限——单档过大等于把热路径的问题搬了个家。"""
    oversized = {
        str(path.relative_to(PROJECT_ROOT)): _byte_size(path)
        for path in sorted(CLAUDE_DIR.glob("skills/*/references/*.md"))
        if _byte_size(path) > REFERENCE_FILE_CAP
    }
    assert not oversized, (
        f"references 单文件超 {REFERENCE_FILE_CAP}B：{oversized}。"
        "拆成更细的一事一档（如按步骤/按评分方式），不要抬高本文件常量。"
    )


def _dispatch_table_rows() -> list[str]:
    lines = (CLAUDE_DIR / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    rows = [line for line in lines if line.startswith("|")]
    assert len(rows) >= 3, "CLAUDE.md 未找到业务域调度表（表头+分隔+至少一行业务域）"
    return rows[2:]


def _known_entities() -> set[str]:
    """可被调度的实体全集：command 文件名 + skill/agent frontmatter 的 name。"""
    entities = {f"/{path.stem}" for path in (CLAUDE_DIR / "commands").glob("*.md")}
    for path in [*CLAUDE_DIR.glob("skills/**/SKILL.md"), *CLAUDE_DIR.glob("agents/**/*.md")]:
        for line in path.read_text(encoding="utf-8").splitlines()[:6]:
            if line.startswith("name:"):
                entities.add(line.removeprefix("name:").strip())
                break
    return entities


def test_claude_md_dispatch_entities_exist() -> None:
    """调度表提到的每个实体都得真实存在——悬空名会让路由指向不存在的能力。"""
    known = _known_entities()
    dangling = {
        name
        for row in _dispatch_table_rows()
        for name in _ENTITY_RE.findall(row.split("|")[3] if row.count("|") > 3 else row)
        if name not in known
    }
    assert not dangling, (
        f"CLAUDE.md 调度表引用了不存在的实体：{sorted(dangling)}。"
        "改成真实的 command（.claude/commands/*.md）/ skill / agent 名，或补建该实体。"
    )
