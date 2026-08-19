"""Phase A.3 结论义务（用户产品裁决 2026-08-19）：评标必须给结论，不得留裸 manual_review。

背景全部来自回归闸基线与用户人工核实：

- 报价勾稽 0/3 —— **金额就在文件里**，三个 case 都有报价，结论却一个都没呈现；
- manual_review 项只写"需人工复核"，不写已找到什么、缺什么、查过哪里 —— 人工接手时等于
  从零重做，这类结论对业务没有价值；
- 规则罗列与逐项销项没有强制对应关系，漏一项在结论里看不出来。

本文件只约束**输出义务**，不碰判定标准：判 0 / 待人工的裁决口径仍只有 S3 判分仲裁决策表
（A1–A9 + manual 白名单）一处，末尾两个测试就是钉这一条的——义务加码不得顺手放宽或收紧口径。
"""

from __future__ import annotations

import pytest

from server.platform.paths import PROJECT_ROOT

COMMAND = PROJECT_ROOT / ".claude/commands/tender-evaluate.md"


@pytest.fixture(scope="module")
def command_text() -> str:
    return COMMAND.read_text(encoding="utf-8")


# id / 义务 / 必须在场的判据标记
DUTIES: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "三选一",
        "每个资格项与评分项只能三选一：给分 / 有据判 0 / 待人工，没有第四种（沉默）",
        ("三选一",),
    ),
    (
        "待人工三要素",
        "待人工必须附：已找到什么（含页码）/ 缺什么 / 查过哪里——缺任一条就是无效结论",
        ("已找到什么", "缺什么", "查过哪里"),
    ),
    (
        "S1 全量清单",
        "S1 先把资格规则 + 评分项全量罗列成清单（含分值），清单是 S3 的销项底册",
        ("全量罗列", "清单"),
    ),
    (
        "S3 逐条销项",
        "S3 对着清单逐条销项，每条落「要求→证据→页码→判定」四段，漏项 = 未完成",
        ("逐条销项", "要求→证据→页码→判定", "漏项"),
    ),
    (
        "报价大小写",
        "报价必须提取金额的大写与小写两种写法（开标一览表 / 投标函）",
        ("大写", "小写"),
    ),
    (
        "报价勾稽结论",
        "必须给出「报价已提供且勾稽一致 / 不一致」的明确结论，不能沉默",
        ("勾稽一致",),
    ),
    (
        "价格分待横比",
        "价格分本身标「待横比合成」——单家算不出横比价格分是设计，但报价呈现是义务",
        ("待横比",),
    ),
    (
        "基本信息块",
        "招标/投标基本信息（项目名·编号·招标人·投标人·信用代码·法定代表人）必产成块，逐项带页码出处",
        ("basic_info", "project_name", "tender_no", "tenderee", "credit_code", "legal_person"),
    ),
    (
        "不照抄上传字段",
        "基本信息一律抓自文件内容，不照抄上传时人填的字段（那不是证据）",
        ("不照抄上传",),
    ),
    (
        "投标人名一致性",
        "投标文件正文的投标人名 ↔ 上传申报名，不符要点名",
        ("consistency", "上传申报名"),
    ),
    (
        "应标一致性",
        "投标文件声称响应的项目名称/编号 ↔ 本次招标项目——不一致 = 重大发现（投错标/套卷），须显式判定 + 两侧页码",
        ("应标一致性", "投错标", "两侧页码"),
    ),
]


@pytest.mark.parametrize(
    ("duty_id", "duty", "markers"), DUTIES, ids=[d[0] for d in DUTIES]
)
def test_conclusion_duty_is_stated_in_the_command(
    command_text: str, duty_id: str, duty: str, markers: tuple[str, ...]
) -> None:
    missing = [m for m in markers if m not in command_text]

    assert not missing, f"{duty_id} 缺判据标记 {missing}；义务：{duty}"


def test_bare_manual_review_is_explicitly_banned(command_text: str) -> None:
    """"需人工复核"四个字单独成句就是本轮要消灭的产物形态，命令里必须显式禁掉。"""
    assert "裸 manual_review" in command_text or "不得只写「需人工复核」" in command_text


def test_price_duty_does_not_reopen_the_cross_bid_semantics(command_text: str) -> None:
    """报价义务只加"呈现"，不改 cross_bid 判定：横比项仍是 score:null + 决策表 A4。"""
    assert "requires_cross_bid_comparison" in command_text
    assert "评标基准价" in command_text


class TestArbitrationVerdictScopeUnchanged:
    """义务加码不得动裁决口径——A1–A9 与 manual 白名单是本轮明令一个字不改的部分。"""

    def test_manual_whitelist_is_verbatim(self, command_text: str) -> None:
        assert "**manual 白名单 = A1 / A3 / A4 / A5 / A7，此外一律不得 manual**" in command_text

    def test_decision_table_still_declares_itself_the_only_authority(
        self, command_text: str
    ) -> None:
        assert "判分仲裁决策表" in command_text
        assert "唯一裁决口径" in command_text
        for row in ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9"):
            assert f"| {row} |" in command_text, f"决策表缺 {row} 行"

    def test_the_duty_defers_to_the_table_instead_of_restating_it(
        self, command_text: str
    ) -> None:
        """新义务必须写明"判定标准看决策表"，否则又是一处并行口径（三处叠加例外的老病）。"""
        duty_section = command_text[command_text.index("三选一") :][:600]

        assert "决策表" in duty_section
