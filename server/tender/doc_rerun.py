"""评标入口的补底稿重跑：预算封顶、并发去重、失败不劣化（H3 KD2 的写侧）。

从 ``server.tender.doc_layer`` 拆出（review N4）：读层只回答"能不能用这份底稿"，
补跑是**写**动作（改 doc 行、起后台 OCR），两种职责混在一个文件里既撑破行数硬线，
也让"读层被 import 时会不会写库"变得不明显。

贯穿本模块的不变量（review N1，pass2 实测破口）：

    补跑是尽力补救，**结束时的 doc 行绝不能比补跑前更差**。

它不是自动成立的——``run_*_doc_ocr`` 自己吞异常并写 ``ocr_text=NULL, status=failed``，
补跑因此会"正常返回"却把可用的降级底稿清空。所以这里对每一段都做「快照 → 补跑 → 校验 →
不如快照就整段回滚（文本 + 状态 + 清单一起）」。
"""

from __future__ import annotations

import asyncio
import logging

from server.platform.config import get_ocr_concurrency_settings
from server.stores.tender_doc_store import (
    get_bid_doc,
    get_project_doc,
    set_doc_ocr_status,
    update_bid_doc_ocr,
    update_project_doc_ocr,
)
from server.tender.doc_layer import DOC_LAYER_IMPAIRED_STATUSES, doc_ocr_status

logger = logging.getLogger(__name__)

# 补底稿重跑最多占用等待上限的这个比例（F3：补跑不能和评标本身抢预算）。
_RERUN_BUDGET_RATIO = 0.2
# 底稿"好坏"排序：只有更好或持平的结果才保留，否则回滚快照（N1）。
# 与 pipeline.summarize_ocr_results 的既有序对齐（failed > partial > degraded > ready，
# 即 partial 整文件正文缺失严格劣于 degraded 仅引擎降级，pass3-F2）。
_STATUS_RANK = {"ready": 3, "degraded": 2, "partial": 1}


def rerun_budget_sec(*, spent_sec: float = 0.0) -> float:
    """补底稿重跑的时间预算（秒）。

    Args:
        spent_sec: 本次评标已经花掉的预算——**等预热的那段时间必须计入**（review N3）：
            等满上限后再放一段全尺寸补跑，等于把整单又往 TENDER_TIMEOUT 推一步。

    Returns:
        等待上限剩余量的一小片；下界 1s，防配置把它压成 0 后每次必超时。
    """
    cap = get_ocr_concurrency_settings(spent_sec=spent_sec).doc_layer_wait_cap_sec
    return max(1.0, cap * _RERUN_BUDGET_RATIO)


def mark_doc_rerunning(
    project_id: str, bid_id: str | None, tenant: str, *, project: bool, bid: bool
) -> None:
    """把将要重跑的 doc 行置回 ``running``（保留 ocr_text），让并发评标经 oracle 去重。"""
    if project:
        set_doc_ocr_status(project_id, None, tenant=tenant, status="running")
    if bid and bid_id:
        set_doc_ocr_status(project_id, bid_id, tenant=tenant, status="running")


def _snapshot(row: dict | None) -> dict:
    """记下补跑前的底稿快照（回滚素材）。"""
    row = row or {}
    return {
        "ocr_text": row.get("ocr_text"),
        "ocr_status": row.get("ocr_status"),
        "ocr_clarity": row.get("ocr_clarity"),
        "ocr_failed_files": row.get("ocr_failed_files"),
    }


def _is_not_worse(current: dict | None, snapshot: dict) -> bool:
    """补跑后的行是否"不劣于"快照。

    判据两条都要满足：状态档位不低于原值，且底稿文本还在（补跑把文本清空 = 变劣，
    哪怕状态字段看起来没变差）。未知/失败状态 rank=0，天然判为劣化。
    """
    current = current or {}
    if not (current.get("ocr_text") or "").strip():
        return False
    return _STATUS_RANK.get(current.get("ocr_status"), 0) >= _STATUS_RANK.get(
        snapshot.get("ocr_status"), 0
    )


def _restore_snapshot(
    project_id: str, bid_id: str | None, tenant: str, snapshot: dict, *, is_project: bool
) -> None:
    """把一段 doc 行整体写回快照（文本 + 状态 + 问题文件清单一起）。"""
    files = snapshot.get("ocr_failed_files")
    failed_files = None
    if files:
        import json

        try:
            parsed = json.loads(files)
            failed_files = [str(item) for item in parsed] if isinstance(parsed, list) else None
        except (ValueError, TypeError):
            failed_files = None
    status = snapshot.get("ocr_status")
    if not status:
        return  # 补跑前就没有可回滚的状态（不该发生；无快照可回滚时保持现状）
    if is_project:
        update_project_doc_ocr(
            project_id,
            tenant=tenant,
            ocr_text=snapshot.get("ocr_text"),
            ocr_clarity=snapshot.get("ocr_clarity"),
            status=status,
            failed_files=failed_files,
        )
    elif bid_id:
        update_bid_doc_ocr(
            project_id,
            bid_id,
            tenant=tenant,
            ocr_text=snapshot.get("ocr_text"),
            status=status,
            failed_files=failed_files,
        )


def _settle_segment(
    project_id: str, bid_id: str | None, tenant: str, snapshot: dict, *, is_project: bool
) -> None:
    """结算一段：读回最终行，劣于快照就整段回滚（N1 + N2 的逐段处置）。

    逐段结算天然覆盖 N2："已经补好的段"因为不劣于快照而被保留，"超时/失败的段"（行还停在
    running 或被写成 failed+NULL）才回滚——不会因为另一段超时就把补好的段一起刷回去。

    整段自防护（pass3-F3）：读回与回滚都在 try 内。补跑只是尽力补救，结算的 DB 故障
    不得冲出本函数拖垮整单评标，也不得牵连另一段的结算（段间独立成败）。
    """
    try:
        current = (
            get_project_doc(project_id, tenant)
            if is_project
            else get_bid_doc(project_id, bid_id, tenant)
        )
        if _is_not_worse(current, snapshot):
            return
        _restore_snapshot(project_id, bid_id, tenant, snapshot, is_project=is_project)
    except Exception:
        logger.warning(
            "tender_doc_layer_rerun_settle_failed",
            extra={
                "project_id": project_id,
                "bid_id": bid_id,
                "scope": "project" if is_project else "bid",
            },
            exc_info=True,
        )


async def rerun_prewarm_for_degraded_docs(
    project_id: str,
    bid_id: str,
    tenant: str,
    rows: tuple[dict | None, dict | None],
    *,
    spent_sec: float = 0.0,
) -> None:
    """对 degraded/partial 的 doc 重跑**一次**预热 OCR（H3 KD2）。

    "只重跑失败/降级文件"是 content-sha256 缓存的自然结果：成功文件命中缓存零成本，而降级/
    部分底稿本就不进缓存（``ocr.cache._is_low_fidelity``），必然重算。招标层重跑不触发
    criteria 抽取（那是一次 30-60s 的模型往返，与补底稿无关）。无 ``case_path``（H3 之前上传的
    老行）→ 跳过。

    三条护栏：**预算封顶**（``rerun_budget_sec``，含已耗预算）、**并发去重**（开跑前置
    ``running``，并发评标的 oracle 据此判"已经有人在补"）、**失败不劣化**（逐段快照 + 结算回滚，
    见模块 docstring 的不变量）。

    Args:
        project_id: 招标项目标识。
        bid_id: 当前被评标的投标文档标识。
        tenant: 租户作用域。
        rows: ``(招标层行, 投标层行)``，来自 ``doc_layer.read_doc_rows``。
        spent_sec: 本次评标已耗预算（等预热的实测耗时）。
    """
    # 局部 import 破环：doc_pipeline → runner → doc_layer/本模块 → doc_pipeline。
    from server.tender import doc_pipeline
    from server.tender.runner import TENDER_OCR_PURPOSE

    project_doc, bid_doc = rows
    rerun_project = doc_ocr_status(project_doc) in DOC_LAYER_IMPAIRED_STATUSES and bool(
        (project_doc or {}).get("case_path")
    )
    rerun_bid = doc_ocr_status(bid_doc) in DOC_LAYER_IMPAIRED_STATUSES and bool(
        (bid_doc or {}).get("case_path")
    )
    if not rerun_project and not rerun_bid:
        return
    project_snapshot = _snapshot(project_doc)
    bid_snapshot = _snapshot(bid_doc)

    async def _rerun() -> None:
        if rerun_project:
            await doc_pipeline.run_project_doc_ocr(
                project_id,
                project_doc["case_path"],
                tenant=tenant,
                purpose=TENDER_OCR_PURPOSE,
                run_info_extraction=False,
            )
        if rerun_bid:
            await doc_pipeline.run_bid_doc_ocr(
                project_id,
                bid_id,
                bid_doc["case_path"],
                tenant=tenant,
                purpose=TENDER_OCR_PURPOSE,
            )

    # 预算计算在 try 之外：它抛错属编程错误，应 fail-fast，不得混进"补跑失败"的
    # 外部失败语义被 blanket catch 降级成一行 warning（pass3-F5，F4 的空转测试即此坑）。
    budget = rerun_budget_sec(spent_sec=spent_sec)
    await asyncio.to_thread(
        mark_doc_rerunning, project_id, bid_id, tenant, project=rerun_project, bid=rerun_bid
    )
    try:
        await asyncio.wait_for(_rerun(), timeout=budget)
    except (TimeoutError, asyncio.TimeoutError):
        logger.warning(
            "tender_doc_layer_rerun_timeout", extra={"project_id": project_id, "bid_id": bid_id}
        )
    except Exception:
        logger.warning(
            "tender_doc_layer_rerun_failed",
            extra={"project_id": project_id, "bid_id": bid_id},
            exc_info=True,
        )
    finally:
        # 结算在 finally：成功、超时、抛错、**取消**四路都必须收拾 mark_doc_rerunning 置下的
        # running（pass3-F1——CancelledError 是 BaseException，try/except Exception 接不住；
        # 评标整单超时的 wait_for 取消正是常态触发路径）。结算故意用同步调用而非 to_thread：
        # 取消态下任何 await 点都会立刻再抛 CancelledError，同步 sqlite 微秒级写在 loop 线程
        # 是"取消安全"的必要代价（与 compare_worker._schedule_if_idle 同一权衡先例）。
        # ``run_*_doc_ocr`` 吞掉异常后会"正常返回"却已把行写成 failed + NULL 文本
        # （pass2 N1 的实测破口），只看异常判断不了结果好坏，故无条件结算。
        if rerun_project:
            _settle_segment(project_id, None, tenant, project_snapshot, is_project=True)
        if rerun_bid:
            _settle_segment(project_id, bid_id, tenant, bid_snapshot, is_project=False)
