"""Inline directory audit: preload case materials + local rules into one prompt.

Cuts the dominant latency source — serial tool round-trips through the model gateway —
by handing the agent everything it needs up front instead of having it Glob/Read files
one round-trip at a time. The agent still does the judgment and cites policy_refs from
the injected rules; Python only delivers the inputs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from server.core import DEFAULT_OUTPUT_SCHEMA_NAME, AgentRunMeta, StructuredJSON, run_agent_json
from server.platform.paths import PROJECT_ROOT

EXPENSE_RULES_DIR = PROJECT_ROOT / "knowledge" / "expense"
CASE_REQUEST_FILE = "audit-request.json"

AUDIT_INSTRUCTIONS = """你是企业报销审核员。下方已提供本案的全部材料与本地规则，**请直接基于这些内容一次性完成审核，通常无需再调用任何工具读取文件**（仅当确需查看附件原件时才用 Read）。

审核要求：
- 先在内部从案件材料提取关键事实作为事实底稿：申请人、类别、金额、币种、日期、发票号、附件、`missing_fields`、字段间冲突；缺失项如实标记，不要脑补。
- 只依据下方“本地规则”判断，不使用训练记忆中的制度，不编造规则、附件或审批记录。
- 规则命中：`priority` 数字越小越优先；同优先级 `reject` 优先于 `approve`。
- 综合判断：规则命中、金额 / 限额 / 比例、预算与流程、事前申请一致性、发票有效性、异常迹象。
- `policy_refs` 必须来自命中规则的 `rule_id`；`evidence_chain` 给出 `source` / `finding` / `conclusion`。
- 找不到适用规则时输出 `verdict=manual_review`，`manual_review_reason=rule_gap`，不要编造。
- `manual_review` 时必须填 `manual_review_reason`，只能取：missing_approval / rule_gap / data_conflict / insufficient_evidence / budget_exceeded / invoice_invalid / pre_approval_mismatch。

造假快速识别（优先于常规分析；命中“一眼假”硬伤时第一时间据此定性，不必逐项展开常规审核，也不要再调用工具，尽快出结论）：
- 典型“一眼假”的数据完整性硬伤：
  - 占位 / 测试值：申请人写“测试 / xxx / 张三李四”等，发票号全为同一数字或 1234…/0000…，金额为 9999 / 123456 等明显占位；
  - 不可能或矛盾的日期：未来日期、报销日期早于费用发生日期、明显超常理的区间；
  - 发票号 / 税号格式明显伪造：位数不符、含非法字符、与币种 / 地区规则明显冲突；
  - 字段自相矛盾：分项金额之和与合计不符、币种与金额单位冲突、附件与申报严重不一致。
- 按程度区分结论（拿不准时一律从宽用 manual_review，不要轻易 rejected）：
  - 明显伪造（多项硬伤，或单项铁证）→ `verdict=rejected`，`risk_score >= 80`，`risk_dimensions` 中 `anomaly` 取高分；`explanation` 以“数据疑似造假”开头并点明具体伪造点。
  - 仅可疑、证据不足以定性 → `verdict=manual_review`，`manual_review_reason` 取 `data_conflict`（发票相关取 `invoice_invalid`）；`explanation` 以“数据疑似造假”开头说明可疑点，交人工复核。
- 造假判定基于数据真实性而非业务限额，此时 `policy_refs` 允许为空数组；但 `evidence_chain` 必须把触发判定的字段与取值写进 `finding`。

输出：
- 只返回一个符合 `.claude/contracts/common/audit-result.schema.json` 的 JSON 对象。
- 决策只用 `verdict`（approved / rejected / manual_review）；不要输出 `result` / `conclusion`（服务端派生）。
- `explanation` / `reasons` / `evidence_chain` 用中文；不要输出 JSON 之外的任何文字。
"""


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def load_expense_rules() -> str:
    """Concatenate every local expense rule file, with filename provenance headers."""
    if not EXPENSE_RULES_DIR.is_dir():
        return ""
    blocks: list[str] = []
    for path in sorted(EXPENSE_RULES_DIR.glob("*.json")):
        text = _read_text(path)
        if text is not None:
            blocks.append(f"### {path.name}\n{text}")
    return "\n\n".join(blocks)


def _resolve_case_dir(directory_path: str) -> Path | None:
    candidate = Path(directory_path)
    resolved = (candidate if candidate.is_absolute() else PROJECT_ROOT / candidate).resolve()
    try:
        resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return None
    return resolved if resolved.is_dir() else None


def load_case_block(directory_path: str) -> str:
    """Read the case request JSON inline and list any attachments by name."""
    case_dir = _resolve_case_dir(directory_path)
    if case_dir is None:
        return ""
    blocks: list[str] = []
    request_text = _read_text(case_dir / CASE_REQUEST_FILE)
    if request_text is not None:
        blocks.append(f"### {CASE_REQUEST_FILE}\n{request_text}")
    attachments = [
        p.name for p in sorted(case_dir.iterdir()) if p.is_file() and p.name != CASE_REQUEST_FILE
    ]
    if attachments:
        listing = "\n".join(f"- {directory_path}/{name}" for name in attachments)
        blocks.append(f"### 附件文件清单（如需查看原件可用 Read 读取）\n{listing}")
    return "\n\n".join(blocks)


def build_inline_audit_prompt(directory_path: str) -> str:
    """Compose a self-contained audit prompt: instructions + case materials + all rules."""
    case_block = load_case_block(directory_path) or "（未找到本案材料，请据此输出 manual_review）"
    rules_block = load_expense_rules() or "（本地规则缺失，无适用规则时输出 manual_review / rule_gap）"
    return (
        f"{AUDIT_INSTRUCTIONS}\n"
        f"=== 本案材料 ===\n{case_block}\n\n"
        f"=== 本地规则（唯一依据）===\n{rules_block}\n"
    )


async def run_inline_directory_audit(
    directory_path: str,
    *,
    request_id: str,
    tenant: str | None,
    **opts: Any,
) -> tuple[StructuredJSON, AgentRunMeta]:
    """Run a directory audit with materials + rules preloaded; keep only Read for attachments."""
    return await run_agent_json(
        build_inline_audit_prompt(directory_path),
        schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
        request_id=request_id,
        tenant=tenant,
        allowed_tools=["Read"],
        max_turns=int(os.getenv("AUDIT_INLINE_MAX_TURNS", "8")),
        **opts,
    )
