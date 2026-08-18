"""评标注入预算的**单一来源**（KD3）：全文以 token 计，闭式账目由构造保证。

三次事故（2026-08-14~15）都是在给同一条降级路径打补丁，算术缺陷有三种形态：

1. **单位错**——默认上限写成 ``64,000``，其实是按"64K token 窗口"反推的字节数。
2. **口径错**——改按 ``MODEL_CONTEXT_WINDOW`` 推导，部署值 1,048,576 得出 2.1MB 预算，
   等于没有闸；而 bundled CLI 约 200K token 就拒。**模型能力 ≠ CLI 行为**。
3. **落笔即不可达**——"每项 ≤8KB × 20 项 + 脚手架 25K = 79K ≤ 60K" 这个账当场就不闭合。

本模块的对策不是"再调一个更好的数字"，而是改变结构：

- **唯一需要标定的量**是 :data:`TENDER_EFFECTIVE_CONTEXT_TOKENS`（CLI 实测拒绝阈值）；
- 脚手架按实际提示词资产**测**（见 ``scripts/measure_tender_scaffold.py``）；
- criteria 按传入的真实对象**现场测**；
- 证据额度是**减完再除**的余量，因此
  ``scaffold + criteria + Σ(per_item) + margin ≤ 总额`` 恒成立，不可能写出不可达的账；
- 余量不足时**显式抛错**并点名标定常量与标定档，绝不静默缩水。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from server.tender.evidence_chunks import MAX_CHUNK_CHARS

# 标定档：CLI 有效上限的测法与测得值。错误消息一律带上它——防止本常量变成第五个写死的错数字。
CALIBRATION_DOC_PATH = ".ai_state/sprints/2026-08-15-tender-context-pipeline/design.md"

# ── 唯一的标定常量 ──────────────────────────────────────────────────────────────
#
# bundled CLI 的**实测**拒绝阈值（≈200K token），见标定档「决定性事实」节：招标 38,541 字 +
# 投标 370,529 字 ≈ 409K token 的单会话必拒。刻意**不**取自 ``MODEL_CONTEXT_WINDOW``——那描述
# 模型能力，与 CLI 实际接受多少无关（08-14 教训）。换模型/换 CLI 后按标定档复测并改 env。
TENDER_EFFECTIVE_CONTEXT_TOKENS = 200_000

# 中文 UTF-8 3 字节/字 ≈ 1 token。全模块只有这一处做字节↔token 换算（旧代码在两个模块里
# 各存一份换算假设，且一处写 1.0 一处写 3，正是 64,000B 单位错的温床）。
_BYTES_PER_TOKEN = 3

# 脚手架实测（2026-08-17 复跑，命令见 ``scripts/measure_tender_scaffold.py``）：
#   /tender-evaluate 命令 20,212 字 + tender-eval SKILL.md 1,419 字（references 死副本已删）
#   + audit-result/criteria 两份 schema 16,398 字 = 38,029 字（中文为主，1 字≈1 token）。
# 再加 CLI 自身的 system prompt 与工具定义（服务端不可测，按同量级留额）与服务端固定块
# （OCR 头注释 / criteria 头尾 / 底稿告警 / 截断标记）→ 常量维持 90,000 token 不下调，
# 差额转成评标循环与证据侧的安全垫；调低须先复跑脚本确认不跌破下界（见脚本头注）。
# **旧值 30,000 已被 2026-08-15 实测（当时 57,988 字）证伪**：30K 从来装不下。
_SCAFFOLD_RESERVE_TOKENS = 90_000

# agent 循环自留：评标是多轮循环，模型还会重识别低清页、扩展思考、写长 JSON 结论，
# 这些都在同一窗口累积。按有效上限的 1/4 留给循环自身（沿用既有比例，单位改 token）。
_AGENT_LOOP_MARGIN_DIVISOR = 4


class InjectionBudgetExhausted(RuntimeError):
    """规则层（脚手架 + criteria + 循环余量）挤掉了证据额度，本次注入不可达。

    这是**不可达的账**，不是可降级的状态：继续下去只会重演 08-15 那次"把招标文件整份挤掉"。

    Attributes:
        cause: 机器码，两取一（上层据此分流，不必 grep 中文消息）：

            - ``"reserve_too_large"``——窗口本身放得下，是 ``TENDER_SCAFFOLD_RESERVE_TOKENS``
              留额压过头。**可配置解锁**。
            - ``"window_too_small"``——即便脚手架留额归零也放不下 criteria + 证据下界。
              调 env 无用，只能换更大窗口的端点，或承认本部署评不了这个项目。
    """

    def __init__(self, message: str, *, cause: str) -> None:
        super().__init__(message)
        self.cause = cause


def _positive_int_env(name: str, default: int) -> int:
    """读一个正整数 env；缺失/非法/非正一律回落 ``default``（配置错不该炸掉评标）。"""
    raw = (os.getenv(name) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def effective_context_tokens() -> int:
    """本次部署下 CLI 实际能接受的输入 token 上限（唯一标定量）。"""
    return _positive_int_env("TENDER_EFFECTIVE_CONTEXT_TOKENS", TENDER_EFFECTIVE_CONTEXT_TOKENS)


def estimate_tokens(text: str) -> int:
    """估算文本的输入 token 数。

    中文 OCR 底稿按 1 字符 ≈ 1 token（保守：ASCII 实际更省，宁可高估不低估）。
    """
    return len(text or "")


def tokens_to_bytes(tokens: int) -> int:
    """token → UTF-8 字节（中文 3B/字）。字节闸是最终兜底，判据本身仍以 token 计。"""
    return tokens * _BYTES_PER_TOKEN


def fallback_injection_tokens() -> int:
    """证据层不适用时，**回落路径**可注入的 token 额度。

    与 :func:`plan_injection` 同构造：``有效上限 − 脚手架 − 循环余量``。回落路径没有 criteria
    注入块（那条路上 criteria 本来就取不到），故只扣这两项，剩下的整块给底稿。

    **不得直接用 :func:`effective_context_tokens`**（pass1 就是这么写的）：那等于把整个窗口
    当成底稿可用额度，加上 90K 脚手架必然超窗，而爆窗是一次性硬失败——闸开得比收编前还大
    2.3 倍，形同虚设。
    """
    total = effective_context_tokens()
    return max(1, total - scaffold_tokens() - total // _AGENT_LOOP_MARGIN_DIVISOR)


def fallback_max_bytes() -> int:
    """底稿注入的字节兜底上限——由回落 token 额度换算，不再是独立常量（AC6 单点）。"""
    return tokens_to_bytes(fallback_injection_tokens())


def scaffold_tokens() -> int:
    """单次评标的脚手架占用（提示词资产 + CLI 自身 + 服务端固定块）。"""
    return _positive_int_env("TENDER_SCAFFOLD_RESERVE_TOKENS", _SCAFFOLD_RESERVE_TOKENS)


def criteria_tokens(criteria: dict[str, Any] | None) -> int:
    """criteria 注入块的**实测**占用（按实际序列化形态计，不用估算值）。

    与 ``criteria_context._criteria_context_block`` 同样用 ``indent=2`` 序列化——那是真正
    进 prompt 的形态，紧凑序列化会低估三成左右。
    """
    if not criteria:
        return 0
    return estimate_tokens(json.dumps(criteria, ensure_ascii=False, indent=2))


@dataclass(frozen=True)
class InjectionPlan:
    """一次评标的注入额度分配。各字段单位均为 token。

    不变量（AC5，由 :func:`plan_injection` 的构造保证）::

        scaffold + criteria + per_item * query_count + margin <= effective_context_tokens()
    """

    scaffold_tokens: int
    criteria_tokens: int
    margin_tokens: int
    evidence_tokens: int
    per_item_tokens: int
    query_count: int
    total_tokens: int

    @property
    def chunks_per_item(self) -> int:
        """每个检索项可取几个 chunk——本概念的**唯一**推导处（P2/DRY）。

        除数取 chunk 的硬上限而非 p90：p90 会系统性高估装得下几块，而越预算的代价是整单
        一次性硬失败。至少 1 个——取 0 等于该项必然 ``evidence_unresolved``，那不是预算
        问题而是配置错。
        """
        return max(1, self.per_item_tokens // MAX_CHUNK_CHARS)


def evidence_floor_tokens(*, criteria_cost: int, query_count: int) -> int:
    """证据额度的**可论证下界**：不得低于它要回答的那一层规则本身的额度。

    等价的按项说法是 ``per_item_tokens >= criteria_tokens / query_count``——某一项分到的
    证据额度，至少要能装下描述这一项规则的那么多字。低于它的注入必然是**规则占多数**的，
    模型只能照着招标文件的评分表给投标打分；critic 离线复跑 ``53f94fd0`` 观测到的正是这个
    形态（投标报价 82 分项拿到的 301 token 是招标层废标条款）。

    刻意**不**取计划档原文提的 ``query_count × MAX_CHUNK_CHARS``：那个门槛在本系统跑过的
    每一种标定下都不可达（默认 200K 标定下规则层与循环余量吃掉 70%，20 项需要 80,000 而
    可用只有 60,000），落笔即不可达的门槛只会被下一个人整条注释掉。

    下界同时保底 ``query_count``（每项至少 1 token），使无 criteria 的回落路径也仍有闸。

    Args:
        criteria_cost: 本次 criteria 注入块的实测 token 数。
        query_count: 本次要检索的项数。

    Returns:
        证据额度的下界（token）。
    """
    return max(query_count, criteria_cost)


def _budget_exhausted(
    *, total: int, scaffold: int, criteria_cost: int, margin: int, evidence: int, floor: int
) -> InjectionBudgetExhausted:
    """构造带实测数字与可执行解锁动作的容量不足异常，并判定两种原因中的哪一种。

    判据是算术而非阈值：脚手架留额是唯一可调的那一项（循环余量按有效上限定比派生），
    故"把 scaffold 调到 0 之后还够不够"就把两种原因分干净了——够 → ``reserve_too_large``
    （改 env 即可解锁）；不够 → ``window_too_small``（调任何 env 都没用，只能换更大窗口的
    端点，或如实承认本部署评不了这个项目）。参数均为 :func:`plan_injection` 现场算出的
    实测量，逐个进消息，让运维不必回查代码就能核对这笔账。
    """
    floor_note = (
        "下界 = criteria 实测额度，证据不得少于它要回答的规则"
        if floor == criteria_cost
        else "下界 = 检索项数，每项至少 1 token"
    )
    account = (
        f"注入预算不足以承载本次评标：有效上限 {total} token（TENDER_EFFECTIVE_CONTEXT_TOKENS）"
        f"− 脚手架 {scaffold}（TENDER_SCAFFOLD_RESERVE_TOKENS）− criteria 实测 {criteria_cost}"
        f" − 循环余量 {margin} = 证据额度 {evidence}，低于下界 {floor}（{floor_note}）。"
    )
    if criteria_cost + floor <= total - margin:
        return InjectionBudgetExhausted(
            account
            + "原因：**脚手架留额压过头**——窗口本身放得下，是 TENDER_SCAFFOLD_RESERVE_TOKENS 占了"
            f"本该留给证据的空间。解锁：把 TENDER_SCAFFOLD_RESERVE_TOKENS 调到不超过 "
            f"{max(0, total - margin - criteria_cost - floor)}，或按标定档 {CALIBRATION_DOC_PATH} "
            "复测 CLI 实际上限后上调 TENDER_EFFECTIVE_CONTEXT_TOKENS。"
            "不要靠缩小证据额度掩盖——那正是 2026-08-15 把招标文件整份挤掉的做法。",
            cause="reserve_too_large",
        )
    return InjectionBudgetExhausted(
        account
        + "原因：**窗口装不下**——即便脚手架留额归零，criteria 加证据下界仍超出本部署的有效"
        f"上限（需要 {criteria_cost + floor + margin}，只有 {total}）。改配置无用："
        f"请按标定档 {CALIBRATION_DOC_PATH} 复测后改用更大窗口的端点，或如实承认本项目在当前"
        "部署下不可自动评标并转人工——绝不能让它静默出一份烂分。",
        cause="window_too_small",
    )


def plan_injection(*, criteria: dict[str, Any] | None, query_count: int) -> InjectionPlan:
    """按闭式账目分配本次注入额度。

    Args:
        criteria: 本次评标的项目规则对象（额度按其实际体量现场测）。
        query_count: 本次要检索的项数（评分项 + 资格规则）。

    Returns:
        :class:`InjectionPlan`；``per_item_tokens`` 是**除**出来的余量，故账目恒闭合。

    Raises:
        ValueError: ``query_count <= 0``——无查询项就不该走检索组装，内部不变量破坏即抛。
        InjectionBudgetExhausted: 证据额度跌破 :func:`evidence_floor_tokens` 的下界。
    """
    if query_count <= 0:
        raise ValueError(f"query_count must be positive, got {query_count}")
    total = effective_context_tokens()
    scaffold = scaffold_tokens()
    criteria_cost = criteria_tokens(criteria)
    margin = total // _AGENT_LOOP_MARGIN_DIVISOR
    evidence = total - scaffold - criteria_cost - margin
    floor = evidence_floor_tokens(criteria_cost=criteria_cost, query_count=query_count)
    if evidence < floor:
        raise _budget_exhausted(
            total=total,
            scaffold=scaffold,
            criteria_cost=criteria_cost,
            margin=margin,
            evidence=evidence,
            floor=floor,
        )
    per_item = evidence // query_count
    return InjectionPlan(
        scaffold_tokens=scaffold,
        criteria_tokens=criteria_cost,
        margin_tokens=margin,
        evidence_tokens=per_item * query_count,
        per_item_tokens=per_item,
        query_count=query_count,
        total_tokens=total,
    )


def chunks_per_query_budget(*, criteria: dict[str, Any] | None, query_count: int) -> int:
    """每个检索项可取几个 chunk——由闭式账目派生，替代旧的写死常量 ``_CHUNKS_PER_QUERY=3``。

    Args:
        criteria: 本次评标的项目规则对象。
        query_count: 本次要检索的项数。

    Returns:
        每项 chunk 数上限（≥1）。项数越多每项越少，总量恒受标定上限约束。
    """
    return plan_injection(criteria=criteria, query_count=query_count).chunks_per_item


def describe_context_rejection(*, observed_tokens: int) -> str:
    """CLI 因超窗拒绝时的运维可读说明（AC6：点名标定常量与标定档）。

    ``server.common.contract`` 已把 ``Prompt is too long`` 列为不可重试——即爆窗是一次性
    硬失败，没有"多试几次"的余地，所以这条消息必须直接给出可执行的下一步。
    """
    return (
        f"注入 {observed_tokens} token 被端点拒绝（超出 CLI 实际上限）。"
        f"当前标定值 TENDER_EFFECTIVE_CONTEXT_TOKENS={effective_context_tokens()}，"
        f"说明实测上限已变——请按标定档 {CALIBRATION_DOC_PATH} 附录复跑二分测法，"
        "用测得值更新该 env，不要凭猜调数字。"
    )
