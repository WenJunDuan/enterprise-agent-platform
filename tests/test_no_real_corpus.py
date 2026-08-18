"""真实语料守卫：代码、测试与提示词里不得出现真实**机构 / 公司名**。

**能抓什么、不能抓什么（别扩大声称范围）**：本守卫只按「汉字 + 机构性后缀」的形态抓，
因此抓得到 `某某科技有限公司` / `某某学院`，**抓不到**无后缀的项目名（`青岛诺德中心…建设项目`）
与真人姓名（触发本次治理的 A7 那处）——后两类在形态上与正常业务文本不可分。
声称范围必须与实际能力一致，否则下一个人会误以为项目名也有守卫
（依据 coding-standards P1「可达性论证的检索式必须能抓住它要防的失败」）。

**为什么要机械化**：用户纪律「样本只用于验证，不得当规格；任何具体项目的数据不得进仓库」
写在文档里两个月，真实语料仍悄悄渗进 11 个文件——其中一个**真人姓名**待在生产提示词
`.claude/commands/tender-evaluate.md` 的判分决策表里，随每一次评标发给模型
（见 `.ai_state/compound/2026-08-17-decision-real-corpus-worktree-only-purge.md`）。
劝导挡不住渐进渗入，形态检查能。

**守卫本身不得存真名**（否则等于把要清除的东西又写回仓库），故不用黑名单，改为
「组织名形态正则 + 合成名允许清单」：命中形态而不在允许清单里 → 判红，由人确认它是
合成语料后显式加进 ``_SYNTHETIC_ALLOWED``。加白是有意动作，渗入则是无意动作——
这个不对称正是守卫的价值。
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 扫描面：模型看得到的提示词 + 会被 clone 的代码与测试。
# **必须含 `agent-front/src`**：本次治理里真实公司名 10 处全部在前端测试
# （`model.test.ts`），漏掉它等于对命中最多的目录不设防（pass4 F12 实测指出）。
_SCAN_DIRS = (
    "server",
    "tests",
    "scripts",
    "agent-front/src",
    ".claude/commands",
    ".claude/agents",
    ".claude/skills",
    # 评标回归闸金标准（Phase 0）：`eval/golden/*/expected.yaml` 逐条描述真实标书的缺陷，
    # 是最容易把真名写回来的地方。扫描面不含它 = 对新目录的匿名化纪律不设防。
    # 连带把 `.yaml` 纳入后缀：金标准是 yaml，只加目录不加后缀等于加了个不生效的守卫。
    "eval",
)
_SCAN_SUFFIXES = {".py", ".md", ".ts", ".tsx", ".yaml"}

# 中文组织 / 项目名形态：2-8 个汉字 + 机构性后缀。真实语料几乎必然落进这个形态。
_ORG_SHAPE = re.compile(r"[一-龥]{2,8}(?:有限公司|股份公司|集团|学院|大学|研究院|设计院)")

# 合成语料允许清单：新增前先确认它**不是**真实存在的机构。保持极短。
# 首轮加白的 8 条均已逐条人工核实为合成（某某 / 甲方 / 乙 / 示例 / AI 前缀等明示虚构标记）；
# 同批扫出的「投标人TZ…」经核实为**真实公司**，已改成合成名而非加白——
# 加白是有意动作、渗入是无意动作，这个不对称正是本守卫的价值。
_SYNTHETIC_ALLOWED = frozenset(
    {
        "甲科技有限公司",
        "乙工程有限公司",
        "某某有限公司",
        "示例有限公司",
        "某某建设工程有限公司",
        "投标人某某建设集团",
        "甲方建设有限公司",
        "识别建设有限公司",  # 完整串为「AI识别建设有限公司」
        "示例学院",
        # 前端 mock / 占位数据（pass4 F12 扩面后纳入扫描）：无真实世界指代的通用占位。
        # 同批扫出的真实企业名（中铁十二局 / 中建华东 / 上海地铁集团 / 无锡城投等）
        # 已改成合成名而非加白。
        "示例科技有限公司",
        "示例数字科技有限公司",
        "示例差旅服务有限公司",
        "示例轨道交通集团",
        "示例城投集团",
        "丙建设集团有限公司",
        "丁工程集团有限公司",
        "丙建集团",  # 上二者的简称形态（UI 短名列）
        "丁工集团",
        "市政建设集团有限公司",
        "省建工集团股份有限公司",
        "市政集团",
        "市水务集团",
        "临港产投集团",
    }
)

# 本守卫自身与状态档会引用形态样例，排除以免自指翻红。
_EXEMPT_FILES = {"tests/test_no_real_corpus.py"}


def _scan_files() -> list[Path]:
    files: list[Path] = []
    for rel in _SCAN_DIRS:
        root = PROJECT_ROOT / rel
        if not root.exists():
            continue
        files.extend(p for p in root.rglob("*") if p.is_file() and p.suffix in _SCAN_SUFFIXES)
    return files


def test_no_real_organization_names_in_code_or_prompts() -> None:
    """组织名形态命中且不在合成允许清单 → 判红。"""
    hits: dict[str, set[str]] = {}
    for path in _scan_files():
        rel = str(path.relative_to(PROJECT_ROOT))
        if rel in _EXEMPT_FILES:
            continue
        found = {
            m.group(0)
            for m in _ORG_SHAPE.finditer(path.read_text(encoding="utf-8", errors="ignore"))
            if m.group(0) not in _SYNTHETIC_ALLOWED
        }
        if found:
            hits[rel] = found
    assert not hits, (
        f"疑似真实机构/公司名进入代码或提示词：{hits}。\n"
        "真实语料只用于验证、不得进仓库（用户纪律）。改成合成名并保住其结构性质"
        "（如 OCR 易混需保留形近字对、字面错位需保留连续重合字数）；"
        "确认是合成名则加进 _SYNTHETIC_ALLOWED。"
    )
