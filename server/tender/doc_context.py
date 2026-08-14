"""底稿层决策与完整性告警：预热底稿的取用，以及"底稿有洞"的两个消费面。

从 ``server/tender/runner.py`` 纯移动而来（2026-08-14，runner.py 419 行拆分）：整函数搬家 +
import 接线，函数体、命名、日志文案、注释语义逐字未改。runner.py 保留 ``run_tender_evaluation``
主流程（底稿获取 / 预算闸 / 模型调用 + 契约重试）与 ``_ocr_integrity_warnings`` 的 re-export。

一个变更理由：**底稿层（tender_doc_store 预热）的取用与降级表达**。同一批 warning 有两个消费面
——注入给模型的上下文块（``_ocr_warning_block``）与随结论落盘的字段（``_inject_ocr_warnings``）
——两者必须同源同文案，故同处一家。
"""

from __future__ import annotations

import asyncio
import time

from server.stores.tender_doc_store import decode_failed_files
from server.tender import doc_layer, doc_rerun


def _ocr_integrity_warnings(
    project_doc: dict | None, bid_doc: dict | None
) -> list[dict[str, object]]:
    """把"底稿降级/部分缺失"渲染成结构化 warning（H3 KD2：不静默）。

    Returns:
        每条形如 ``{"scope", "status", "files", "message"}``；无问题时空列表。
    """
    warnings: list[dict[str, object]] = []
    for scope, row in (("招标文件", project_doc), ("投标文件", bid_doc)):
        status = doc_layer.doc_ocr_status(row)
        if status not in doc_layer.DOC_LAYER_IMPAIRED_STATUSES:
            continue
        # 列解析走 store 的 decode（编解码同处一家）；"没记清单"与"清单为空"在 warning 里同义，
        # 故 None 归一成 []（warning 照发，只是不点名文件）。
        files = decode_failed_files((row or {}).get("ocr_failed_files")) or []
        detail = "部分文件识别失败或缺页" if status == "partial" else "含降级识别段（本地兜底引擎）"
        named = f"：{'、'.join(files)}" if files else ""
        warnings.append(
            {
                "scope": scope,
                "status": status,
                "files": files,
                "message": f"{scope}底稿{detail}{named}；依赖这些材料的评分项证据可能不完整。",
            }
        )
    return warnings


def _inject_ocr_warnings(payload: object, warnings: list[dict[str, object]]) -> None:
    """把底稿完整性 warning 强制写进结论（``extracted_data.ocr_warnings``）。

    落在 ``extracted_data`` 而非顶层：``audit-result.schema.json`` 顶层是
    ``additionalProperties: false``，而 ``extracted_data`` 显式允许自由字段——既不动共享 schema，
    也保证 warning 随结论一起持久化、可回溯。
    """
    if not warnings or not isinstance(payload, dict):
        return
    extracted = payload.get("extracted_data")
    if not isinstance(extracted, dict):
        extracted = {}
        payload["extracted_data"] = extracted
    existing = extracted.get("ocr_warnings")
    extracted["ocr_warnings"] = (existing if isinstance(existing, list) else []) + warnings


async def _resolve_doc_layer(
    project_id: str, bid_id: str | None, tenant: str
) -> tuple[str | None, list[dict[str, object]]]:
    """评标入口对预热底稿的完整决策（H3 KD2 + KD5）。

    顺序：等预热到终态（in-flight 才等，不再无条件超时回落 inline）→ 对 degraded/partial 自动
    重跑一次预热 → 复用底稿并按最终状态生成结论 warning。

    Returns:
        ``(doc 层底稿文本 | None, warnings)``；文本为 None 时调用方回落 inline OCR。
    """
    warnings: list[dict[str, object]] = []
    waited_from = time.monotonic()
    if bid_id:
        outcome = await doc_layer.wait_doc_layer_ready(project_id, bid_id, tenant)
        if outcome == "wait_cap_reached":
            warnings.append(
                {
                    "scope": "预热 OCR",
                    "status": "prewarm_timeout",
                    "files": [],
                    "message": "预热 OCR 在评标等待上限内未完成，已改用即时 OCR；底稿可能不完整。",
                }
            )
        elif outcome == "terminal":
            rows = await doc_layer.read_doc_rows(project_id, bid_id, tenant)
            if any(
                doc_layer.doc_ocr_status(row) in doc_layer.DOC_LAYER_IMPAIRED_STATUSES
                for row in rows
            ):
                # 等预热花掉的时间要计入补跑预算（review N3）——否则等满上限后还能再放一段
                # 全尺寸补跑，把整单继续往 TENDER_TIMEOUT 推。
                await doc_rerun.rerun_prewarm_for_degraded_docs(
                    project_id, bid_id, tenant, rows, spent_sec=time.monotonic() - waited_from
                )
    loader = (
        doc_layer.load_doc_layer_context_slim
        if doc_layer.slim_context_enabled()
        else doc_layer.load_doc_layer_context
    )
    doc_layer_text = await asyncio.to_thread(loader, project_id, bid_id, tenant)
    if doc_layer_text is not None and bid_id:
        # 重跑后重新读一次：warning 必须反映**最终**状态，重跑成功就不该再报警。
        project_doc, bid_doc = await doc_layer.read_doc_rows(project_id, bid_id, tenant)
        warnings.extend(_ocr_integrity_warnings(project_doc, bid_doc))
    return doc_layer_text, warnings


def _ocr_warning_block(warnings: list[dict[str, object]]) -> str:
    """把底稿完整性 warning 渲染进模型上下文——评分项据此走 evidence 缺失规则，而不是静默判低分。"""
    lines = "\n".join(f"- {warning['message']}" for warning in warnings)
    return (
        "\n\n=== 底稿完整性告警（本次识别底稿存在降级/缺失）===\n"
        f"{lines}\n"
        "依赖上述材料的评分项：证据不足时按现行 evidence 缺失规则处理（manual_review / 不得凭空判 0）。"
    )
