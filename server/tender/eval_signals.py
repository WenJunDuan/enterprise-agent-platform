"""一次评标会话的降级信号——回填质量门的判据来源。

2026-08-17 生产事故：criteria 抽取失败 → 证据层跳过 → 784,903 字节底稿被预算闸截到
178,641（砍 77%）→ 模型只看到 23% 的材料。**那次会话自解析出的 criteria 随后被回填成项目
永久权威**，后续每一家投标都继承这份从残卷里解析出来的规则。

要挡住它，回填点（``tender.worker``）必须知道"这次注入被削过没有"。截断这件事只有预算闸
自己知道（``draft_budget.bound_draft`` / ``context_slim.bound_tender_context``），而
``tender_context_truncated`` 那条日志是给运维看的、进不了判断。本模块就是那条信号线。

**为什么用 ContextVar 装一个可变记录**：预算闸夹在 worker 与模型调用之间隔着好几层，
逐层加参数要改一路签名（含另有他用的纯计算函数）。ContextVar 只保证**向下**复制
（子任务 / ``to_thread`` 拿到的是同一份引用的副本），因此值必须是**可变对象**——深处
标记的是发起方手里的同一个记录，标记才回得来。
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(slots=True)
class EvaluationSignals:
    """本次评标会话里发生过的降级事实。

    Attributes:
        context_truncated: 注入给模型的底稿 / 上下文被预算闸削过。削过 = 这次结论及其
            副产物（自解析 criteria）是从残卷得出的，不足以固化成项目规则。
    """

    context_truncated: bool = False


_SIGNALS: ContextVar[EvaluationSignals | None] = ContextVar(
    "tender_evaluation_signals", default=None
)


@contextlib.contextmanager
def evaluation_signals() -> Iterator[EvaluationSignals]:
    """开一次评标会话的信号作用域，产出的记录在退出后仍可读。

    Yields:
        本次会话的 :class:`EvaluationSignals`；作用域内任何深度（含子任务 / 工作线程）
        的标记都写在这一个对象上。
    """
    record = EvaluationSignals()
    token = _SIGNALS.set(record)
    try:
        yield record
    finally:
        _SIGNALS.reset(token)


def mark_context_truncated() -> None:
    """记下"本次注入被削过"。

    作用域外调用是 no-op：eval CLI、单测、上传期抽取都没有会话在跑，它们既不读这个信号，
    也不该因为预算闸多说一句话而失败。
    """
    record = _SIGNALS.get()
    if record is not None:
        record.context_truncated = True
