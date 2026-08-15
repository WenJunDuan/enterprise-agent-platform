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

# 脚手架实测（本机 2026-08-15，命令见 ``scripts/measure_tender_scaffold.py``）：
#   /tender-evaluate 命令文件 20,260 字 + tender-eval skill 全部 references 21,331 字
#   + audit-result/criteria 两份 schema 16,398 字 = 57,988 字（中文为主，1 字≈1 token）。
# 再加 CLI 自身的 system prompt 与工具定义（服务端不可测，按同量级留额）与服务端固定块
# （OCR 头注释 / criteria 头尾 / 底稿告警 / 截断标记）→ 取 90,000 token。
# **旧值 30,000 已被本次实测证伪**：仅提示词资产就 57,988，30K 从来装不下。
_SCAFFOLD_RESERVE_TOKENS = 90_000

# agent 循环自留：评标是多轮循环，模型还会重识别低清页、扩展思考、写长 JSON 结论，
# 这些都在同一窗口累积。按有效上限的 1/4 留给循环自身（沿用既有比例，单位改 token）。
_AGENT_LOOP_MARGIN_DIVISOR = 4


class InjectionBudgetExhausted(RuntimeError):
    """规则层（脚手架 + criteria + 循环余量）已吃满有效上限，没有额度留给证据。

    这是**不可达的账**，不是可降级的状态：继续下去只会重演 08-15 那次"把招标文件整份挤掉"。
    """


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


def fallback_max_bytes() -> int:
    """底稿注入的字节兜底上限——由 token 上限换算，不再是独立常量（AC6 单点）。"""
    return tokens_to_bytes(effective_context_tokens())


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


def plan_injection(*, criteria: dict[str, Any] | None, query_count: int) -> InjectionPlan:
    """按闭式账目分配本次注入额度。

    Args:
        criteria: 本次评标的项目规则对象（额度按其实际体量现场测）。
        query_count: 本次要检索的项数（评分项 + 资格规则）。

    Returns:
        :class:`InjectionPlan`；``per_item_tokens`` 是**除**出来的余量，故账目恒闭合。

    Raises:
        ValueError: ``query_count <= 0``——无查询项就不该走检索组装，内部不变量破坏即抛。
        InjectionBudgetExhausted: 规则层已吃满上限，没有额度留给证据。
    """
    if query_count <= 0:
        raise ValueError(f"query_count must be positive, got {query_count}")
    total = effective_context_tokens()
    scaffold = scaffold_tokens()
    criteria_cost = criteria_tokens(criteria)
    margin = total // _AGENT_LOOP_MARGIN_DIVISOR
    evidence = total - scaffold - criteria_cost - margin
    if evidence < query_count:
        raise InjectionBudgetExhausted(
            f"规则层已占满注入预算：脚手架 {scaffold} + criteria {criteria_cost} + "
            f"循环余量 {margin} ≥ 有效上限 {total} token（剩余 {evidence}，需至少 {query_count}）。"
            f"请按标定档 {CALIBRATION_DOC_PATH} 复测 CLI 实际上限并调整 "
            f"TENDER_EFFECTIVE_CONTEXT_TOKENS；不要靠缩小证据额度掩盖——"
            "那正是 2026-08-15 把招标文件整份挤掉的做法。"
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


# 一个 chunk 的典型 token 量（S0-B 部署机实测：146 chunk 的 p90 = 3,453 字；见标定档）。
# 用 p90 而非中位数：按中位数算会系统性高估能塞下的 chunk 数，超窗的代价远大于少取一个 chunk。
_TYPICAL_CHUNK_TOKENS = 3_453
# 每项至少取 1 个 chunk：取 0 等于该项必然 evidence_unresolved，那不是预算问题而是配置错。
_MIN_CHUNKS_PER_QUERY = 1


def chunks_per_query_budget(*, criteria: dict[str, Any] | None, query_count: int) -> int:
    """每个检索项可取几个 chunk——由闭式账目派生，替代旧的写死常量 ``_CHUNKS_PER_QUERY=3``。

    Args:
        criteria: 本次评标的项目规则对象。
        query_count: 本次要检索的项数。

    Returns:
        每项 chunk 数上限（≥1）。项数越多每项越少，总量恒受标定上限约束。
    """
    plan = plan_injection(criteria=criteria, query_count=query_count)
    return max(_MIN_CHUNKS_PER_QUERY, plan.per_item_tokens // _TYPICAL_CHUNK_TOKENS)


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
