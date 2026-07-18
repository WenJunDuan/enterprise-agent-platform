"""Inline directory audit: preload case materials + local rules into one prompt.

Cuts the dominant latency source — serial tool round-trips through the model gateway —
by handing the agent everything it needs up front instead of having it Glob/Read files
one round-trip at a time. The agent still does the judgment and cites policy_refs from
the injected rules; Python only delivers the inputs.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from server.audit.direct import DirectTransportError, run_direct_audit
from server.common.domain_profile import (
    DomainProfile,
    assemble_domain_prompt,
    load_case_block as _assemble_case_block,
    load_rules as _assemble_rules,
    resolve_case_dir as _assemble_resolve_case_dir,
)
from server.core import (
    DEFAULT_OUTPUT_SCHEMA_NAME,
    AgentRunMeta,
    StructuredJSON,
    run_agent_json,
)
from server.platform.config import get_audit_settings
from server.platform.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

# D10① flag 门控（默认关）：开启后走 server/audit/direct.py 的 AsyncAnthropic 直连路径，
# 关闭（默认）时行为与 flag 引入前完全一致——现有 claude-agent-sdk CLI 子进程路径。
AUDIT_DIRECT_CONNECT_ENV = "AUDIT_DIRECT_CONNECT"


def _direct_connect_enabled() -> bool:
    return os.getenv(AUDIT_DIRECT_CONNECT_ENV, "0").strip().lower() in {"1", "true", "yes"}

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
  - 多项异常并存、足以认定数据不可信，且能在下方“本地规则”中找到禁止谎报 / 虚报 / 冒领 / 套取等数据真实性类条款 → `verdict=rejected`，`policy_refs` 引用该条款的 `rule_id`（数据真实性拒绝同样要引规则，不得空数组），`risk_score >= 80`，`risk_dimensions` 中 `anomaly` 取高分；`explanation` 客观列出触发判定的字段与取值，定性措辞克制。
  - 多项异常并存、足以认定数据不可信，但“本地规则”中确实没有任何数据真实性类条款可引用 → 不要判 `rejected`（无据判决不成立），改 `verdict=manual_review`，`manual_review_reason` 取 `data_conflict`（发票相关取 `invoice_invalid`）；`explanation` 说明触发判定的字段与取值，并注明本地规则未覆盖此类条款，需人工核实。
  - 仅个别可疑、证据不足以认定 → `verdict=manual_review`，`manual_review_reason` 取 `data_conflict`（发票相关取 `invoice_invalid`）；`explanation` 说明可疑点并指出需人工核实。
- 上述两条 `manual_review` 分支 `policy_refs` 允许为空数组；`rejected` 分支必须有 `policy_refs`（与常规分析一致，不因数据真实性判定而豁免）。无论哪个分支，`evidence_chain` 都必须把触发判定的字段与取值写进 `finding`。

输出：
- 决策只用 `verdict`（approved / rejected / manual_review）；不要输出 `result` / `conclusion`（服务端派生）。
- `reasons` 为简短中文字符串数组（每条一句话，**不要嵌套对象**）；`policy_refs` 为规则 ID 字符串数组；`evidence_chain` 各字段用中文。
- **措辞规范**（`explanation` / `reasons` / `evidence_chain` 通用，写得像财务 / 审计意见，平实克制）：
  - 禁用夸张或口语词（硬伤、铁证、实锤、妥妥、铁定、坐实、必然是 等），改用中性表述：存在、疑似、不满足、缺少、与……不一致。
  - 不堆砌技术黑话（如「Unix 纪元」「系统默认值占位符」），字段异常直接描述现象即可，例「日期为 1970-01-01，疑似默认值或占位值」。
  - 不加自我点评式括注（如「（典型占位数据）」「（非真实人员）」）；事实写进 `finding`，定性交给 `verdict` 与 `reasons`，同一问题只说一次，不连套多个标签。
  - 定性留有余地：除非证据确凿且规则支持，否则用「疑似 / 需人工核实」，不替调查人员下「造假 / 伪造」的终局结论。
- **输出纪律（严格遵守）**：分析在内部完成（如需思考，写在 `<think>...</think>` 内）；最终回复**只能是一个 JSON 对象**，其前后不得有任何分析、前言、说明或重复内容；所有文本字段一律用**中文**，不要中英文混杂。该 JSON 对象必须包含 `verdict` / `explanation` / `reasons` / `policy_refs` / `risk_score` / `evidence_chain` 六个字段，一个都不能少；`explanation` 为**必填且非空**字段，不论走常规审核还是数据真实性核验分支都必须填写，禁止省略。
- **JSON 合法性（极重要，违反会导致解析失败）**：字符串值内部引用人名 / 实体 / 字段值 / 票号时，**一律使用中文引号「」或『』**，**严禁在字符串值里使用半角双引号 `"`**（它会提前闭合字符串、破坏 JSON）；确需半角双引号时必须转义为 `\"`。例：写 `"申请人为「张三」"`，不要写 `"申请人为"张三""`。
"""


# 兜底文案：无材料 / 无规则时仍要让模型走 manual_review，而非脑补。
CASE_MISSING_FALLBACK = "（未找到本案材料，请据此输出 manual_review）"
RULES_MISSING_FALLBACK = "（本地规则缺失，无适用规则时输出 manual_review / rule_gap）"
RESULT_CONTRACT = "common/audit-result.schema.json"


def _expense_profile() -> DomainProfile:
    """Build the expense DomainProfile from current module config.

    构造时读模块全局（PROJECT_ROOT 间接、EXPENSE_RULES_DIR 直接），使测试 monkeypatch
    这些全局后立即生效；profile 本身廉价，每次审核重建无虞。
    """
    return DomainProfile(
        domain="expense",
        instructions=AUDIT_INSTRUCTIONS,
        rules_dir=EXPENSE_RULES_DIR,
        request_file=CASE_REQUEST_FILE,
        case_missing_fallback=CASE_MISSING_FALLBACK,
        rules_missing_fallback=RULES_MISSING_FALLBACK,
        result_contract=RESULT_CONTRACT,
    )


def load_expense_rules() -> str:
    """Concatenate every local expense rule file, with filename provenance headers."""
    return _assemble_rules(EXPENSE_RULES_DIR)


def _resolve_case_dir(directory_path: str) -> Path | None:
    return _assemble_resolve_case_dir(directory_path, PROJECT_ROOT)


def load_case_block(directory_path: str) -> str:
    """Read the case request JSON inline and list any attachments by name."""
    return _assemble_case_block(directory_path, PROJECT_ROOT, CASE_REQUEST_FILE)


def build_inline_audit_prompt(directory_path: str, *, ocr_block: str | None = None) -> str:
    """Compose a self-contained audit prompt: instructions + case materials + all rules.

    ``ocr_block``（P4）：附件的确定性 OCR/直读底稿（发票/收据等）；有则注入，模型无需再 Read。
    经 ``assemble_domain_prompt`` 通用装配（expense 域 profile）；输出与旧专版字节一致。
    """
    return assemble_domain_prompt(
        _expense_profile(), directory_path, project_root=PROJECT_ROOT, ocr_block=ocr_block
    )


async def run_inline_directory_audit(
    directory_path: str,
    *,
    request_id: str,
    tenant: str | None,
    ocr_block: str | None = None,
    **opts: Any,
) -> tuple[StructuredJSON, AgentRunMeta]:
    """Run a directory audit with materials + rules preloaded; keep only Read for attachments.

    ``ocr_block``（P4）：附件确定性 OCR 底稿，**由路由层预处理后传入**（feature 域 audit/ 不可
    跨域 import ocr/；OCR 预处理放 routes/audit_worker，见 test_layering）。注入后模型无需再 Read。

    D10① flag 门控（``AUDIT_DIRECT_CONNECT``，默认关）：关闭时行为与 flag 引入前完全一致——
    全部走下方 ``_run_cli_directory_audit``（claude-agent-sdk CLI 子进程）。开启时先走
    ``server/audit/direct.py`` 的 AsyncAnthropic 直连路径；**回落语义**（critic F2，不可
    静默降级）——传输类故障（连接/鉴权/网关 5xx/超时，秒级失败）单次回落 CLI 路径（复合最坏
    ≈ 直连超时 + CLI 自身重试环 < AUDIT_TIMEOUT_SEC 180s）；契约类故障（重试耗尽仍不合规，
    换路径大概率同败）直接向上抛出，**不回落**。
    """
    if _direct_connect_enabled():
        settings = get_audit_settings()
        # 直连路径只支持 run_direct_audit 显式声明的 opts（review round1 F3）：从副本里取出
        # project_id/archive_to_results 转发，其余键 **fail-fast**——不静默丢弃，避免 flag
        # on/off 行为悄悄漂移（如某调用方新传 evidence_source 时直连侧无声吞掉）。opts 原样
        # 保留供传输类回落时透传给 CLI 路径（CLI 经 run_agent_json 支持这些键）。
        direct_opts = dict(opts)
        project_id = direct_opts.pop("project_id", None)
        archive_to_results = direct_opts.pop("archive_to_results", True)
        if direct_opts:
            raise ValueError(
                f"AUDIT_DIRECT_CONNECT 直连路径不支持这些选项: {sorted(direct_opts)}；"
                "请走 CLI 路径（AUDIT_DIRECT_CONNECT=0）或扩展 run_direct_audit 显式支持。"
            )
        prompt = build_inline_audit_prompt(directory_path, ocr_block=ocr_block)
        try:
            return await run_direct_audit(
                prompt,
                request_id=request_id,
                tenant=tenant,
                schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
                contract_max_retry=settings.contract_max_retry,
                project_id=project_id,
                archive_to_results=archive_to_results,
            )
        except DirectTransportError as exc:
            logger.warning(
                "audit direct-connect transport failure, falling back to CLI path once: %s",
                exc,
                extra={"request_id": request_id, "tenant": tenant or "default"},
            )
            return await _run_cli_directory_audit(
                directory_path,
                request_id=request_id,
                tenant=tenant,
                ocr_block=ocr_block,
                **opts,
            )
        # DirectContractError：设计禁止静默降级，原样向上抛出，不回落 CLI 路径。
    return await _run_cli_directory_audit(
        directory_path, request_id=request_id, tenant=tenant, ocr_block=ocr_block, **opts
    )


async def _run_cli_directory_audit(
    directory_path: str,
    *,
    request_id: str,
    tenant: str | None,
    ocr_block: str | None = None,
    **opts: Any,
) -> tuple[StructuredJSON, AgentRunMeta]:
    """claude-agent-sdk CLI 子进程路径（D10① 引入前的 ``run_inline_directory_audit`` 原实现，
    仅改名——flag off 时字节级行为不变，D8 wiring 断言写法同款覆盖见
    ``tests/test_audit_direct_connect.py``）。
    """
    # 所有开关集中在 config.AuditSettings（含各项取舍背景）；每次审核读一次，
    # 部署机改 env 重启即生效。
    settings = get_audit_settings()
    prompt = build_inline_audit_prompt(directory_path, ocr_block=ocr_block)

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
