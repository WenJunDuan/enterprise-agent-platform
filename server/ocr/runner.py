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

MAPPING_INSTRUCTIONS = """你是表单回填映射器。下方提供"识别底稿"（确定性识别产物）与目标表单 schema。
**仅基于识别底稿**完成字段映射，无需调用任何工具；**输出形态由目标表单 schema 决定**。

映射规则：
- 对 schema.fields 的每个字段输出一项；底稿无对应内容 → value 置 null、加入 low_confidence，不脑补。
- 值规整：数字去千分位保留精度；日期归一 ISO `YYYY-MM-DD`；下拉必须命中 options。
- 合同付款节点逐条进对应子表（节点名/触发条件/比例/金额/计划日期/币种）；Σ比例≈100%、Σ金额≈合同总额，不自洽标 low_confidence。
- 任一关键字段低置信/冲突/缺失 → 加入 low_confidence 且 needs_review=true。

**输出格式（严格遵守，只输出这一个 JSON 对象，分析写在 <think></think> 内，前后无其它文本）**：
{
  "fields": [
    {"key": "字段名", "component": "single_line", "value": null, "confidence": 0.3}
  ],
  "sub_tables": [
    {"key": "子表名", "rows": []}
  ],
  "low_confidence": ["字段名"],
  "needs_review": true,
  "evidence": [{"source": "文件名/字段", "finding": "原因"}]
}

**硬性约束**：
- `fields` 与 `sub_tables` 必须是**数组**，不是对象 / 字典。
- `confidence` 必须是 **0~1 的数字**（如 0.3 / 0.6 / 0.9），不是 "low" / "high" 文字。
- 字段级原因写进 `evidence`，**不要**放进 fields 项里（不要 reason 键）。
- **禁止**额外顶层键：不要 values / review_notes / low_confidence_fields / analysis_summary / summary。
- 所有文本字段一律用中文。
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


_COMPONENTS = frozenset({"single_line", "multi_line", "select", "number", "date", "sub_table"})
_CONFIDENCE_WORDS = {
    "high": 0.9,
    "medium": 0.6,
    "mid": 0.6,
    "low": 0.3,
    "none": 0.0,
    "unknown": 0.3,
}


def _coerce_confidence(value: Any, *, default: float) -> float:
    """模型 confidence（数字 / "low"/"high" 文字 / null）归一为 0~1 数字。"""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    if isinstance(value, str):
        return _CONFIDENCE_WORDS.get(value.strip().lower(), default)
    return default


def _lookup_model_field(model_fields: Any, key: str) -> tuple[Any, Any, Any]:
    """从模型 fields（dict{key:{...}} / dict{key:值} / list[{key,...}]）提取 (value, confidence, note)。"""
    if isinstance(model_fields, dict):
        entry = model_fields.get(key)
        if isinstance(entry, dict):
            note = entry.get("reason") or entry.get("note") or entry.get("source")
            return entry.get("value"), entry.get("confidence"), note
        return entry, None, None  # 形如 {key: 值}
    if isinstance(model_fields, list):
        for item in model_fields:
            if isinstance(item, dict) and item.get("key") == key:
                note = item.get("reason") or item.get("note") or item.get("source")
                return item.get("value"), item.get("confidence"), note
    return None, None, None


def _normalize_sub_tables(raw_sub_tables: Any, form_schema: dict[str, Any]) -> list[dict[str, Any]]:
    """模型 sub_tables（dict{key:{rows}} / list）归一为契约 list[{key, columns?, rows}]。

    以 form_schema.sub_tables 为准：schema 声明的子表都出现（模型没给则空 rows）。
    """
    schema_tables = {
        st["key"]: st
        for st in (form_schema.get("sub_tables") or [])
        if isinstance(st, dict) and st.get("key")
    }
    collected: dict[str, dict[str, Any]] = {}

    def _add(key: str, body: Any) -> None:
        if not key:
            return
        if isinstance(body, dict):
            rows = body.get("rows", [])
        elif isinstance(body, list):
            rows = body
        else:
            rows = []
        entry: dict[str, Any] = {"key": key, "rows": [r for r in rows if isinstance(r, dict)]}
        cols = schema_tables.get(key, {}).get("columns")
        if cols:
            entry["columns"] = cols
        collected[key] = entry

    if isinstance(raw_sub_tables, dict):
        for key, body in raw_sub_tables.items():
            _add(str(key), body)
    elif isinstance(raw_sub_tables, list):
        for item in raw_sub_tables:
            if isinstance(item, dict) and item.get("key"):
                _add(str(item["key"]), item)

    for key, st in schema_tables.items():  # schema 声明但模型没给 → 补空
        if key not in collected:
            entry: dict[str, Any] = {"key": key, "rows": []}
            if st.get("columns"):
                entry["columns"] = st["columns"]
            collected[key] = entry
    return list(collected.values())


def normalize_to_form_schema(raw: Any, form_schema: dict[str, Any]) -> dict[str, Any]:
    """围绕 form_schema 把模型自由输出归一为 form-fill 契约结构。

    **输出形态由 form_schema 决定，不信任模型结构**：遍历 schema.fields，从模型输出
    （dict / list / None 等任意结构）提取值，component 一律取自 schema，缺失字段
    value=null 并入 low_confidence。只修结构、不臆造业务值——模型说没有就保留 null。

    覆盖现场实测的各种异形：fields 用对象索引、confidence 用 "low"/"high" 文字、
    sub_tables 用对象、顶层多 analysis_summary/low_confidence_fields、整体为 None。

    Args:
        raw: 模型输出经 _extract_json_object 后的对象（dict / None / 异形均可）。
        form_schema: 前端传来的目标表单定义（fields[] / sub_tables[]）。

    Returns:
        符合 form-fill.schema.json 的 dict。
    """
    obj = raw if isinstance(raw, dict) else {}
    schema_fields = form_schema.get("fields", []) if isinstance(form_schema, dict) else []
    model_fields = obj.get("fields")
    if model_fields is None:
        model_fields = obj.get("values")  # 常见别名

    fields: list[dict[str, Any]] = []
    low_confidence: list[str] = []
    evidence: list[dict[str, str]] = []

    for sf in schema_fields:
        if not isinstance(sf, dict) or not sf.get("key"):
            continue
        key = str(sf["key"])
        component = sf["component"] if sf.get("component") in _COMPONENTS else "single_line"
        value, raw_conf, note = _lookup_model_field(model_fields, key)
        has_value = value not in (None, "", [], {})
        confidence = _coerce_confidence(raw_conf, default=0.8 if has_value else 0.3)
        fields.append({"key": key, "component": component, "value": value, "confidence": confidence})
        if not has_value or confidence < 0.6:
            low_confidence.append(key)
        if note:
            evidence.append({"source": key, "finding": str(note)[:500]})

    for alias in ("low_confidence", "low_confidence_fields"):  # 合并模型的多种命名
        for lc in obj.get(alias) or []:
            if isinstance(lc, str) and lc not in low_confidence:
                low_confidence.append(lc)

    for alias in ("analysis_summary", "review_notes", "summary"):  # 解释不丢，归入 evidence
        text = obj.get(alias)
        if isinstance(text, str) and text.strip():
            evidence.append({"source": "summary", "finding": text.strip()[:1000]})

    needs_review = obj.get("needs_review")
    if not isinstance(needs_review, bool):
        needs_review = True
    needs_review = needs_review or bool(low_confidence)

    result: dict[str, Any] = {
        "fields": fields,
        "sub_tables": _normalize_sub_tables(obj.get("sub_tables"), form_schema),
        "needs_review": needs_review,
    }
    if low_confidence:
        result["low_confidence"] = low_confidence
    if evidence:
        result["evidence"] = evidence
    form_id = obj.get("form_id")
    if not isinstance(form_id, str) and isinstance(form_schema, dict):
        form_id = form_schema.get("form_id")
    if isinstance(form_id, str):
        result["form_id"] = form_id
    return result


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
            # 围绕 form_schema 归一化：模型输出结构千变万化（fields 用对象索引 / confidence
            # 用文字 / sub_tables 用对象 / 多余顶层键 / 整体 None），统一按 schema 重构成契约
            # 结构后再校验——格式问题第一次就过，重试只兜真故障（网络 / 模型完全没出 JSON）。
            result = normalize_to_form_schema(_extract_json_object(raw), form_schema)
            jsonschema.validate(result, schema)
            return result
        except Exception as exc:  # 网络故障 / 模型完全没出 JSON：重跑一次降 flaky
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
