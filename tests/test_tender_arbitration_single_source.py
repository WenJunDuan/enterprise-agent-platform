"""C. 判 0 / manual 仲裁收敛为单一决策表——保表不减语义。

同一套仲裁规则原先写在 5 处并互相叠加例外（`SKILL.md` 不可判定项节、`.claude/CLAUDE.md`
tender 节、`tender-evaluate.md` 的 (a)(b) 二分 / 确认未满足默认判 0 / S4 决断优先总纲），
读者要把 5 段拼起来才知道一个项该判 0 还是 manual。收敛成 S3 一张决策表，其余改为引用。

**每条规则都对应一次历史误判**，因此本测试是一张可执行的语义对照表：左列是收敛前的出处，
右列是收敛后必须仍然存在的判据标记。删重复表述可以，删规则不行。
"""

from __future__ import annotations

import pytest

from server.platform.paths import PROJECT_ROOT

COMMAND = PROJECT_ROOT / ".claude/commands/tender-evaluate.md"
SKILL = PROJECT_ROOT / ".claude/skills/tender-eval/SKILL.md"
PROJECT_CLAUDE_MD = PROJECT_ROOT / ".claude/CLAUDE.md"


def _command_text() -> str:
    return COMMAND.read_text(encoding="utf-8")


def _claude_md_tender_section() -> str:
    """只取 CLAUDE.md 的 tender 节——expense 节自有一套 ``data_conflict`` 触发条件，与本项无关。"""
    text = PROJECT_CLAUDE_MD.read_text(encoding="utf-8")
    start = text.index("### tender")
    return text[start : text.index("### system", start)]


# ── 语义对照表：收敛前出处 → 收敛后必须仍在场的判据标记 ────────────────────────
#
# id / 原出处 / 规则一句话 / 判据标记（全部须出现在决策表所在的命令文件里）
SEMANTIC_MAP: list[tuple[str, str, str, tuple[str, ...]]] = [
    (
        "A1",
        "cmd S1 护栏 + SKILL 降级规则 + CLAUDE.md 规则两层",
        "缺招标文件/定位不到评标办法/通则层缺口 → manual_review(rule_gap)，不得编造规则",
        ("rule_gap", "定位不到"),
    ),
    (
        "A2",
        "cmd 废标扣分证据读不清先重识别 + SKILL 低清页证据复核",
        "判罚/扣分/资格页读不清 → 先 ocr-page 重识别（印章页 --seal）再判",
        ("ocr-page", "--seal", "重识别"),
    ),
    (
        "A3",
        "cmd (b) 分支 + R3 low_clarity_files 兜底",
        "疑似已提供但读不清/未还原/印章压字/截断/未定位到 → manual_review(insufficient_evidence)，禁按「否则不得分」判 0",
        ("insufficient_evidence", "印章压字", "low_clarity_files", "否则不得分"),
    ),
    (
        "A4",
        "SKILL 不可判定项节 + CLAUDE.md 不可判定项绝不判 0 + cmd pass_fail",
        "横比/外部数据/现场答辩/manual 模式 → score:null + manual_review，绝不判 0",
        (
            "requires_cross_bid_comparison",
            "requires_external_data",
            "requires_live_event",
            "绝不判 0",
        ),
    ),
    (
        "A5",
        "cmd 窄情形 (ii)",
        "投错项目/该维度全文无可对应章节 → manual_review(non_responsive)",
        ("non_responsive", "无从判断"),
    ),
    (
        "A6",
        "cmd 一致性核验① + CLAUDE.md 典型一致性风险",
        "业绩项目经理与拟派负责人确认为不同人 → 该业绩直接不得分（scored，不是 manual）",
        ("确认是不同的人", "不予认可"),
    ),
    (
        "A7",
        "cmd 一致性核验② + CLAUDE.md 典型一致性风险",
        "仅写法存疑同一人（简繁/形近/OCR 易混）→ manual_review(data_conflict)",
        ("data_conflict", "王建国"),
    ),
    (
        "A6+A7 证据",
        "cmd 一致性核验尾句",
        "两种情形都须同时引业绩页与拟派负责人页两处出处（实施条例第40/42条）",
        ("两处出处", "第40/42条"),
    ),
    (
        "A8",
        "cmd (a) 分支 + cmd 确认未满足默认判 0 + CLAUDE.md 单标果断评分纪律",
        "底稿完整可读、已定位、确认未提供/未响应/不满足（客观项）→ score:0 + status:scored",
        ("已核投标第N页该维度", "确认"),
    ),
    (
        "A8-rejected",
        "cmd status:rejected 限定句",
        "status:rejected 只用于该评分项自身必交材料缺失，不因整单废标清零",
        ("必交", "不因整单废标"),
    ),
    (
        "A9",
        "cmd S4 决断优先总纲 + CLAUDE.md 单标果断评分纪律",
        "其余一切可依本标书判定的项一律果断出分",
        ("果断出分",),
    ),
    (
        "manual 白名单",
        "cmd S4 总纲 + cmd 窄情形 (i)(ii)(iii) + cmd additive 禁 punt",
        "manual 只留给 A1/A3/A4/A5/A7；嫌麻烦/条目多/拿不准/主观都不在内",
        ("嫌麻烦", "条目多", "拿不准"),
    ),
    (
        "范畴错误（双向）",
        "cmd (b) 尾句 + cmd 确认未满足尾句",
        "读不清≠没提供；确认不满足≠待核验，两个方向都是硬伤",
        ("范畴错误",),
    ),
    (
        "pending_reason",
        "cmd score:null 硬性要求",
        "score:null 必带 pending_reason，六值枚举，不得用 evidence_unresolved 兜一切",
        (
            "pending_reason",
            "cross_bid",
            "external_data",
            "live_event",
            "evidence_unresolved",
            "manual_mode",
        ),
    ),
    (
        "报价拆层",
        "cmd 报价判断拆层 + cmd 初步评审报价审查 + CLAUDE.md 单标纪律",
        "报价有效性单标立判（vs 控制价/大小写/算术/唯一报价），只有评标基准价等群体数值才 pending",
        ("有效报价", "控制价", "大小写", "评标基准价"),
    ),
    (
        "独立评审单元",
        "cmd S4 每袋投标是独立评审单元 + CLAUDE.md 单标纪律",
        "除外部依赖数值本身外，一切判断都在本标书内闭合",
        ("独立评审单元",),
    ),
    (
        "主观档次项",
        "cmd banded 主观档次 + CLAUDE.md 单标纪律",
        "主观档次项直接选档给分 status:scored，缺失归最低档/判 0，不写免责套话",
        ("evaluator_type", "最低档", "以评委会为准"),
    ),
    (
        "additive 禁 punt",
        "cmd additive",
        "客观响应项条目再多也要逐条核对给分，不得整项 manual",
        ("逐条核对",),
    ),
    (
        "废标 confirmed 闸",
        "cmd confirmed 闸 + cmd verdict 合成",
        "仅已确认废标事实 confirmed:true 才触发 rejected；疑似/读不清一律 confirmed:false",
        ("confirmed", "自证清白"),
    ),
    (
        "verdict 解耦",
        "cmd 废标独立 gate + cmd verdict 与 scoring 解耦 + CLAUDE.md 资格失败句",
        "资格失败/废标只决定 verdict，scoring[] 仍逐项有扣有得",
        ("解耦", "清零"),
    ),
    (
        "资格审查优先级",
        "cmd S3 先运行资格审查 + SKILL 资格审查最高优先级 + CLAUDE.md",
        "资格审查先于评分运行、不计 total_max、fail 判据严格、外部数据只能 manual",
        ("eligibility_checks", "eligibility_rules", "最高优先级"),
    ),
    (
        "formula 闭合性",
        "cmd formula",
        "变量全闭合才代入算分，否则 manual_review，不得临场心算",
        ("formula_spec", "心算"),
    ),
    (
        "G5 固定限价例外",
        "SKILL 不可判定项节的横比例外（该节已删，语义须由命令承载）",
        "依招标已载明固定限价算的价格分（变量全为招标常量 + 本家报价）可单家算，不走横比 manual",
        ("tender_constant", "bid_component", "限价类单家可算"),
    ),
    (
        "低清页页锚权威",
        "SKILL 低清页证据复核（该节已删）",
        "重识别输出的【第N页】是权威页锚，不得用文档印刷页码替代",
        ("印刷", "page_mismatch"),
    ),
]


@pytest.mark.parametrize(
    ("rule_id", "origin", "rule", "markers"),
    [(r[0], r[1], r[2], r[3]) for r in SEMANTIC_MAP],
    ids=[r[0] for r in SEMANTIC_MAP],
)
def test_every_arbitration_rule_survives_the_convergence(rule_id, origin, rule, markers):
    text = _command_text()
    missing = [m for m in markers if m not in text]

    assert not missing, f"{rule_id}（原出处：{origin}）语义丢失，缺判据标记 {missing}；规则：{rule}"


class TestSingleSource:
    """收敛的判据：仲裁规则只在命令文件里说一次，另外两处只引用。"""

    ARBITRATION_TOKENS = (
        "requires_live_event",
        "requires_external_data",
        "requires_cross_bid_comparison",
        "绝不判 0",
        "范畴错误",
        "data_conflict",
        "insufficient_evidence",
    )

    @pytest.mark.parametrize("token", ARBITRATION_TOKENS)
    def test_project_claude_md_no_longer_restates_arbitration(self, token):
        text = _claude_md_tender_section()

        assert token not in text, f"CLAUDE.md 仍在复述仲裁规则「{token}」，应改为引用 S3 决策表"

    @pytest.mark.parametrize("token", ARBITRATION_TOKENS)
    def test_skill_no_longer_restates_arbitration(self, token):
        text = SKILL.read_text(encoding="utf-8")

        assert token not in text, f"SKILL.md 仍在复述仲裁规则「{token}」，应改为引用 S3 决策表"

    def test_both_files_point_at_the_single_decision_table(self):
        for path in (SKILL, PROJECT_CLAUDE_MD):
            text = path.read_text(encoding="utf-8")
            assert "决策表" in text, f"{path.name} 必须留一句指向 S3 判分仲裁决策表的引用"

    def test_the_decision_table_exists_and_declares_itself_authoritative(self):
        text = _command_text()

        assert "判分仲裁决策表" in text
        assert "唯一裁决口径" in text

    def test_table_covers_a1_through_a9(self):
        text = _command_text()

        for row in ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9"):
            assert f"| {row} |" in text, f"决策表缺 {row} 行"
