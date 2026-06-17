"""文档识别 → 表单回填 runner：Python 薄层，单跳内联（对齐 audit_runner）。

数据流：
1. `server.ocr.pipeline.extract_dir` 进程内跑完确定性流水线（分类 + 直读 + 调 OCR），
   **0 网关往返**；组装成内联"识别底稿"文本。
2. 把底稿 + 目标表单 schema 拼成自包含 prompt，交给模型做**唯一一次**判断——字段映射 +
   付款子表抽取——`allowed_tools=[]`、`setting_sources=[]`，**1 次网关往返**。
3. 按 `.claude/contracts/ocr/form-fill.schema.json` 校验后返回。

识别在 server.ocr（确定性，可测），映射判断在模型侧；Python 不做任何"理解"。
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import jsonschema

from server.core import _extract_json_object, run_agent_full
from server.ocr.pipeline import build_extraction_block, extract_dir
from server.platform.config import get_ocr_settings
from server.platform.paths import PROJECT_ROOT

logger = logging.getLogger(__name__)

OCR_CONTRACTS_DIR = PROJECT_ROOT / ".claude" / "contracts" / "ocr"
FORM_FILL_SCHEMA_PATH = OCR_CONTRACTS_DIR / "form-fill.schema.json"

MAPPING_INSTRUCTIONS = """你是表单回填映射器。下方已提供从案件文件识别出的"识别底稿"（分类 +
原生直读 / OCR 的确定性产物）与目标表单 schema。请**仅基于识别底稿**完成字段映射，无需调用任何工具：
- 映射到目标表单字段：单行 / 多行 / 下拉（必须命中 options）/ 数字（去千分位、保留精度）/ 日期（归一 ISO `YYYY-MM-DD`）。
- 合同付款节点逐条抽取进预测付款子表：节点名 / 触发条件 / 比例 / 金额 / 计划日期 / 币种，每字段带 confidence；
  比例与金额做自洽校验（Σ比例≈100%、Σ金额≈合同总额），不自洽则标 low_confidence。
- 任一关键字段（金额 / 日期 / 付款节点）低置信或冲突 → 写入 low_confidence 并置 needs_review=true，不臆测；
  识别底稿缺失对应内容 → 同样标记，不脑补。
输出纪律：最终只输出一个 JSON 对象（符合 form-fill 契约），分析写在 <think></think> 内，前后不得有其它文本；
所有文本字段一律用中文。
"""


def _load_form_fill_schema() -> dict[str, Any]:
    return json.loads(FORM_FILL_SCHEMA_PATH.read_text(encoding="utf-8"))


def _resolve_case_dir(case_dir: str) -> str:
    """把案件目录解析为绝对路径，并约束在项目根内（防路径穿越）。"""
    base = (Path(case_dir) if Path(case_dir).is_absolute() else PROJECT_ROOT / case_dir).resolve()
    base.relative_to(PROJECT_ROOT.resolve())  # 越界则 raise ValueError，由调用方处理
    return str(base)


def build_mapping_prompt(extraction_block: str, form_schema: dict[str, Any]) -> str:
    """自包含 prompt：映射指令 + 目标表单 schema + 识别底稿。"""
    schema_text = json.dumps(form_schema, ensure_ascii=False, indent=2)
    return (
        f"{MAPPING_INSTRUCTIONS}\n"
        f"=== 目标表单 schema ===\n{schema_text}\n\n"
        f"=== 识别底稿（唯一依据）===\n{extraction_block}\n"
    )


async def map_extraction_to_form(
    extraction_block: str,
    form_schema: dict[str, Any],
    *,
    request_id: str,
    tenant: str | None = None,
    **opts: Any,
) -> dict[str, Any]:
    """把识别底稿映射到目标表单：一次模型往返 + 契约校验，失败重试。

    输入已全部内联（底稿 + schema 在 prompt 里），故 allowed_tools=[]、setting_sources=[]，
    网关往返压到 1（对齐 audit 低延迟）。半截 JSON / 漏字段 / 流式崩溃时重跑一次降 flaky。

    Args:
        extraction_block: 识别底稿文本（pipeline.build_extraction_block 的产物）。
        form_schema: 目标表单定义，注入 prompt 指导映射。
        request_id: 请求标识，贯穿会话日志。
        tenant: 租户标识。

    Returns:
        符合 form-fill.schema.json 的回填结果 dict。

    Raises:
        jsonschema.ValidationError: 模型输出不符合契约（重试耗尽后）。
    """
    settings = get_ocr_settings()
    prompt = build_mapping_prompt(extraction_block, form_schema)
    schema = _load_form_fill_schema()

    last_error: Exception | None = None
    for attempt in range(settings.contract_max_retry + 1):
        try:
            raw = await run_agent_full(
                prompt,
                request_id=request_id,
                tenant=tenant,
                allowed_tools=settings.allowed_tools,  # 全部输入已内联 → 无需工具
                max_turns=settings.max_turns,
                setting_sources=[],  # 精简系统提示，对齐 audit 低延迟
                **opts,
            )
            result = _extract_json_object(raw)
            jsonschema.validate(result, schema)
            return result
        except Exception as exc:  # 半截 JSON / 漏字段 / 流式崩溃：重跑一次即显著降 flaky
            last_error = exc
            if attempt >= settings.contract_max_retry:
                raise
            logger.warning(
                "doc-extract mapping failed (%s, %d/%d), retrying: %s",
                type(exc).__name__,
                attempt + 1,
                settings.contract_max_retry + 1,
                exc,
                extra={"request_id": request_id, "tenant": tenant or "default"},
            )
    # 不可达：循环要么 return 要么在最后一次 attempt re-raise。
    raise AssertionError("unreachable: doc-extract retry loop exited") from last_error


async def run_doc_extract(
    case_dir: str,
    *,
    form_schema: dict[str, Any],
    request_id: str,
    tenant: str | None = None,
    run_seal: bool = False,
    **opts: Any,
) -> dict[str, Any]:
    """跑一次文档识别 → 表单回填；返回经 form-fill 契约校验的结果。

    确定性识别在 server.ocr 进程内完成（0 网关往返），仅字段映射经一次模型往返。
    识别与映射分别由 run_doc_recognize / map_extraction_to_form 承担，本函数只做编排。

    Args:
        case_dir: 案件目录（项目内相对或绝对路径），含待识别文件。
        form_schema: 目标表单定义（组件 + options + 子表列），注入 prompt 指导映射。
        request_id: 请求标识，贯穿会话日志。
        tenant: 租户标识。
        run_seal: 是否对扫描件追加印章识别。

    Returns:
        符合 form-fill.schema.json 的回填结果 dict。
    """
    recognized = await run_doc_recognize(case_dir, run_seal=run_seal)
    return await map_extraction_to_form(
        recognized["block"], form_schema, request_id=request_id, tenant=tenant, **opts
    )


async def run_doc_recognize(
    case_dir: str,
    *,
    run_seal: bool = False,
    timeout_sec: float | None = None,
) -> dict[str, Any]:
    """纯识别：对整个目录跑确定性流水线，返回 {results, block}，**不调模型**。

    供「给外部系统单独调 OCR」的同步端点使用。确定性流水线（分类 + 直读 + 调 OCR
    引擎）是同步阻塞调用（OCR 引擎 predict 走网络且 CPU 重），放线程池执行避免阻塞
    事件循环；可选硬超时兜底防无限挂起。每文件错误已在 pipeline 内隔离（标 error）。

    Args:
        case_dir: 案件目录（项目内相对或绝对路径），含待识别文件。
        run_seal: 是否对扫描件追加印章识别。
        timeout_sec: 识别**软超时**（秒）；None 表示不限。注：超时只取消请求等待，
            to_thread 工作线程无法强制取消、会继续到自然结束——调用方不应在
            TimeoutError 后立即删除 case_dir（可能仍被该线程读取）。

    Returns:
        {"results": [...每文件 extract-result...], "block": "...组装的识别底稿..."}。

    Raises:
        asyncio.TimeoutError: 超过 timeout_sec 未完成（软超时，工作线程可能仍在跑）。
        ValueError: case_dir 越出项目根（_resolve_case_dir 校验）。
    """
    resolved = _resolve_case_dir(case_dir)
    work = asyncio.to_thread(extract_dir, resolved, run_seal=run_seal)
    results = await (asyncio.wait_for(work, timeout=timeout_sec) if timeout_sec else work)
    return {"results": results, "block": build_extraction_block(results)}
