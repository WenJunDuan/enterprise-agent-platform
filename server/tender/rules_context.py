"""通则层法规与业务记忆的服务端注入块（A：把模型自取的 Read 搬到服务端）。

**为什么搬家**：这两类资产内容固定、位置确定、每单必读，而每个 agent turn 都要重新预填充
整份底稿（实测 ~83K token），让模型自己 ``Read`` 等于每单白烧 3-5 轮 × 1-3 分钟。内容一字未改，
只是从"模型花轮次去取"变成"服务端拼 context 时给"。

**注入位置**：``runner`` 把本块拼在 criteria 之后——``context_slim.bound_tender_context`` 削减
预算时只削招标/投标证据段，criteria 之后的尾段整块保留。法规是承重结论的法定依据（``policy_refs``
只能引这里的真实 ``rule_id``），被削掉等于结论无法回溯。
"""

from __future__ import annotations

from server.common.domain_profile import load_rules
from server.platform.paths import PROJECT_ROOT

TENDER_RULES_DIR = PROJECT_ROOT / "knowledge" / "tender"
TENDER_MEMORY_DIR = PROJECT_ROOT / "knowledge" / "memory" / "tender"

_RULES_HEADER = (
    "\n\n=== 通则层国家法规（法律底座，已注入，勿再 Read）===\n"
    "（废标 / 资格 / 一致性 / 程序的法定依据，跨项目稳定，**不含**本项目分值权重；"
    "承重结论的 policy_refs 只能引本节里真实存在的 rule_id。）\n"
)

# 缺失不静默：通则层缺失本就是既有的 manual_review(rule_gap) 降级路径，注入化后这条路径
# 只能改由本文案承载，删掉它等于模型不知道自己缺了法定底座。
_RULES_MISSING = (
    "\n\n=== 通则层国家法规 ===\n"
    "（通则层法规缺失：无法定底座，相关结论降级 manual_review（rule_gap），"
    "不得用训练记忆补规则。）\n"
)

_MEMORY_HEADER = (
    "\n\n=== 相似案例记忆（辅助线索，已注入，勿再 Read）===\n"
    "（只作 memory: 辅助证据，**不能**替代通则层规则与招标文件 criteria。）\n"
)


def tender_rules_block() -> str:
    """Build the injected statutes (+ optional case memory) block for one evaluation.

    Returns:
        以两个换行开头的可直接拼接文本块。法规目录缺失时返回带 ``rule_gap`` 降级说明的
        文案（不返回空串——"没有法定底座"这件事必须对模型可见）；记忆目录为空时不产出
        记忆小节。
    """
    statutes = load_rules(TENDER_RULES_DIR)
    block = f"{_RULES_HEADER}{statutes}\n" if statutes else _RULES_MISSING
    memory = load_rules(TENDER_MEMORY_DIR)
    if memory:
        block += f"{_MEMORY_HEADER}{memory}\n"
    return block
