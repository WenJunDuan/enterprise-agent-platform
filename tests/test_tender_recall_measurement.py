"""AC0b 度量脚本的诚实性闸（返工 F3）。

pass1 用**自带构造语料**跑出 100% 并据此把 AC0b 计 PASS。该语料把 20 个查询词逐字埋进正文，
≥3 字通道 verbatim 必中；ground truth 又用子串匹配，把"措辞不同"这类漏检排除出分母——
**这个度量结构上抓不住 S0-B 真实数据暴露的那类失败**（真实项「价格-最后报价」verbatim 缺失
→ 裸用召回 38%）。

所以本测试锁的不是"召回率数字"，而是**脚本不得在没有真实底稿时给出 PASS**：判据一旦能由
构造保证，它就不再是判据。解锁路径 = 拿部署机真实底稿跑 ``uv run python
scripts/measure_tender_recall.py <底稿.txt>``。
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "measure_tender_recall.py"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("measure_tender_recall", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_synthetic_corpus_can_never_report_ac0b_pass(script, capsys):
    """无真实底稿时只能申报 BLOCKED，且退出码非 0（不得被 CI 当成通过）。"""
    code = script.main(["measure_tender_recall.py"])

    out = capsys.readouterr().out
    assert code != 0, "构造语料上的结果不得作为 AC0b 通过证据"
    assert "AC0b: BLOCKED" in out
    assert "AC0b: PASS" not in out


def test_blocked_output_states_the_unlock_path(script, capsys):
    """BLOCKED 必须写清怎么解锁——只说"待验证"等于把问题留给下一个人猜。"""
    script.main(["measure_tender_recall.py"])

    out = capsys.readouterr().out
    assert "真实底稿" in out
    assert "measure_tender_recall.py" in out


def test_real_draft_run_still_produces_a_verdict(script, capsys, tmp_path):
    """传入底稿时照常出 PASS/FAIL——BLOCKED 只是"没测"，不是把脚本废掉。"""
    draft = tmp_path / "bid.txt"
    draft.write_text(
        "# 第一章 投标函\n投标报价：人民币壹佰贰拾万元整。\n"
        "# 第二章 技术标\n施工组织设计详见本章。\n",
        encoding="utf-8",
    )

    script.main(["measure_tender_recall.py", str(draft)])

    out = capsys.readouterr().out
    assert "AC0b: PASS" in out or "AC0b: FAIL" in out
    assert "BLOCKED" not in out
