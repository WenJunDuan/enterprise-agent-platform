"""Inline directory audit: preload case materials + local rules into one prompt.

Cuts the dominant latency source — serial tool round-trips through the model gateway —
by handing the agent everything it needs up front instead of having it Glob/Read files
one round-trip at a time. The agent still does the judgment and cites policy_refs from
the injected rules; Python only delivers the inputs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from server.core import (
    DEFAULT_OUTPUT_SCHEMA_NAME,
    AgentRunMeta,
    StructuredJSON,
    run_agent_json,
)
from server.platform.config import get_audit_settings
from server.platform.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

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

数据真实性快速核验（优先于常规分析；命中明显异常时尽快据此定性，不必逐项展开常规审核，也不要再调用工具）：
- 常见的数据完整性异常：
  - 占位 / 测试值：申请人为“测试 / xxx / 张三李四”等，发票号全为同一数字或 1234…/0000…，金额为 9999 / 123456 等明显占位；
  - 不可能或矛盾的日期：未来日期、报销日期早于费用发生日期、明显超常理的区间；
  - 发票号 / 税号格式不符：位数不符、含非法字符、与币种 / 地区规则不一致；
  - 字段自相矛盾：分项金额之和与合计不符、币种与金额单位冲突、附件与申报严重不一致。
- 按程度区分结论（拿不准时一律从宽用 manual_review，不要轻易 rejected）：
  - 多项异常并存、足以认定数据不可信 → `verdict=rejected`，`risk_score >= 80`，`risk_dimensions` 中 `anomaly` 取高分；`explanation` 客观列出触发判定的字段与取值，定性措辞克制。
  - 仅个别可疑、证据不足以认定 → `verdict=manual_review`，`manual_review_reason` 取 `data_conflict`（发票相关取 `invoice_invalid`）；`explanation` 说明可疑点并指出需人工核实。
- 该判定基于数据真实性而非业务限额，此时 `policy_refs` 允许为空数组；但 `evidence_chain` 必须把触发判定的字段与取值写进 `finding`。

输出：
- 决策只用 `verdict`（approved / rejected / manual_review）；不要输出 `result` / `conclusion`（服务端派生）。
- `reasons` 为简短中文字符串数组（每条一句话，**不要嵌套对象**）；`policy_refs` 为规则 ID 字符串数组；`evidence_chain` 各字段用中文。
- **措辞规范**（`explanation` / `reasons` / `evidence_chain` 通用，写得像财务 / 审计意见，平实克制）：
  - 禁用夸张或口语词（硬伤、铁证、实锤、妥妥、铁定、坐实、必然是 等），改用中性表述：存在、疑似、不满足、缺少、与……不一致。
  - 不堆砌技术黑话（如「Unix 纪元」「系统默认值占位符」），字段异常直接描述现象即可，例「日期为 1970-01-01，疑似默认值或占位值」。
  - 不加自我点评式括注（如「（典型占位数据）」「（非真实人员）」）；事实写进 `finding`，定性交给 `verdict` 与 `reasons`，同一问题只说一次，不连套多个标签。
  - 定性留有余地：除非证据确凿且规则支持，否则用「疑似 / 需人工核实」，不替调查人员下「造假 / 伪造」的终局结论。
- **输出纪律（严格遵守）**：分析在内部完成（如需思考，写在 `<think>...</think>` 内）；最终回复**只能是一个 JSON 对象**，其前后不得有任何分析、前言、说明或重复内容；所有文本字段一律用**中文**，不要中英文混杂。
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
    # 所有开关集中在 config.AuditSettings（含各项取舍背景）；每次审核读一次，
    # 部署机改 env 重启即生效。
    settings = get_audit_settings()
    prompt = build_inline_audit_prompt(directory_path)

    for attempt in range(settings.contract_max_retry + 1):
        try:
            return await run_agent_json(
                prompt,
                schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
                request_id=request_id,
                tenant=tenant,
                structured=settings.structured_output,
                allowed_tools=settings.allowed_tools,
                max_turns=settings.inline_max_turns,
                setting_sources=[] if settings.lean_context else ["project"],
                **opts,
            )
        except Exception as exc:
            if attempt >= settings.contract_max_retry:
                raise
            logger.warning(
                "audit attempt failed (%s, %d/%d), retrying: %s",
                type(exc).__name__,
                attempt + 1,
                settings.contract_max_retry + 1,
                exc,
                extra={"request_id": request_id, "tenant": tenant or "default"},
            )
    # 不可达：循环要么 return 要么在最后一次 attempt re-raise。
    raise AssertionError("unreachable: audit retry loop exited without returning")
