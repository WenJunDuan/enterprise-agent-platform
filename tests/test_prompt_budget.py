"""提示词预算门禁（KD3）：热路径提示词字节上界 + CLAUDE.md 调度实体存在性机械核对。

**超界了怎么办**：不要抬这里的常量。先删重复表述、收紧措辞（先例：2026-08-17 `b1bc53f`
仲裁口径收敛为单一决策表，净省约 2.7KB）；确属新增规则挤不下时，走 PR 显式改本文件常量并
说明理由（棘轮机械化：只有改常量这一个入口，防"每出一次事故加一段"把命令越撑越大）。
**不要**把细则下沉到 references/ 再加运行时 `Read`——该形态已于 2026-08-14 因会话累计
上下文反增导致生产爆窗而回滚（见下方修正记录）；现行架构 = 按入口**单文件自洽** + 服务端
注入，references/ 仅存于允许交互 `Read` 的 skill（如 multi-ocr）。

上界取值 = 2026-08-12/13 实测字节 + 约 15% 余量。

**2026-08-14 生产事故后的重要修正**：本门禁只约束**单文件字节**，不约束**一次会话累计注入
上下文的总量**——两者可以反向。prompt-architecture 重构把本文件从 38,754B 降到 12,442B（门禁
显示"瘦身 68%"全绿），但真实落进上下文的脚手架总量 = 命令正文 + 6 条强制 Read 的 references
(34,585B) + CLAUDE.md，从 48,706B **涨到** 55,439B（+13.8%），且峰值时刻从会话开头挪到了产出
JSON 之前。在窗口远小于 Claude 的内网模型（DeepSeek Flash 等）上直接 `Prompt is too long`，
四次评标全部无结论。故 `tender-evaluate.md` 已回滚到 38,754B 单文件形态，上界随之复原。

下一版重设结构前必须先解决：预算判据要改成「单会话累计注入字节 vs **部署的最小窗口模型**」，
而不是单文件字节。详见 .ai_state/compound/2026-08-14-learning-prompt-budget-must-be-per-session.md。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_DIR = PROJECT_ROOT / ".claude"

# 文件 → 字节上界。实测值见 .ai_state/sprints/2026-08-12-prompt-architecture/design.md「已验证基线」。
PROMPT_BUDGETS: dict[str, int] = {
    # 2026-08-14 回滚至单文件形态：实测 38,754（重构版 12,442 因会话累计上下文反而更大而回退，
    # 见模块 docstring）。此上界是"守住不再变长"，不是"允许长"——重设结构时按新判据重取。
    ".claude/commands/tender-evaluate.md": 40_000,
    ".claude/commands/tender-compare.md": 8_200,  # 实测 7,132
    # 2026-08-17 收敛：s1-locate-criteria.md（1,633B，原运行时 Read）内联进命令后删除，
    # 另吸收无效标触发词检索 371B。单会话账持平（旧 5,871+Read 1,633≈7,504 → 新 7,491，
    # 且省一次工具往返），故常量随迁移调整，非放松棘轮。
    ".claude/commands/tender-extract-info.md": 7_700,  # 实测 7,491
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
        "先删重复表述/收紧措辞，而不是抬高本文件常量；确属新增规则挤不下时"
        "走 PR 显式改常量并说明理由，流程见本测试头注（勿下沉 references+Read，已回滚）。"
    )


def test_reference_files_within_byte_budget() -> None:
    """下沉产物本身也受限——单档过大等于把热路径的问题搬了个家。

    用 ``skills/**`` 递归匹配：子 skill（如 ``skills/multi-ocr/recognize/``）下沉的 references
    同样受限，否则往深一层挪目录就能绕过本闸。
    """
    oversized = {
        str(path.relative_to(PROJECT_ROOT)): _byte_size(path)
        for path in sorted(CLAUDE_DIR.glob("skills/**/references/*.md"))
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


def _frontmatter_lines(path: Path) -> list[str]:
    """取 YAML frontmatter 区（首个 ``---`` 到下一个 ``---`` 之间）。

    按边界取而不是取固定前 N 行：frontmatter 变长（多加几个 tools/model 字段）时
    ``name:`` 会被挤出固定窗口，实体表随之静默漏项。无 frontmatter 的文件返回空。
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return lines[1:idx]
    return []


def _known_entities() -> set[str]:
    """可被调度的实体全集：command 文件名 + skill/agent frontmatter 的 name。"""
    entities = {f"/{path.stem}" for path in (CLAUDE_DIR / "commands").glob("*.md")}
    for path in [*CLAUDE_DIR.glob("skills/**/SKILL.md"), *CLAUDE_DIR.glob("agents/**/*.md")]:
        for line in _frontmatter_lines(path):
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
