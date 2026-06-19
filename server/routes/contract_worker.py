"""Background task execution for contract review.

镜像 ``tender_worker``：信号量限并发 + 硬超时 + 任务状态机更新。区别是调
``/review-contract`` 内联命令，并在审查成功后复用 ``persist_contract_from_result``
把合同结构落入合同库（``extracted_data.contract``）。
"""

from __future__ import annotations

import asyncio
import logging
import os

from server.common.command_adapter import run_command_json
from server.common.contract import DEFAULT_OUTPUT_SCHEMA_NAME
from server.platform.logging_setup import logging_context
from server.stores.contract_store import persist_contract_from_result
from server.stores.contract_task_store import upsert_contract_task
from server.stores.request_store import utc_now
from server.stores.session_store import new_conversation_id

logger = logging.getLogger(__name__)

# 合同审查硬超时（秒）。合同体量一般小于标书，默认 300s。
CONTRACT_TIMEOUT_SEC = float(os.getenv("CONTRACT_TIMEOUT_SEC", "300"))

# 同时进行的合同审查上限，超额提交在信号量处排队（排队不计入超时）。
MAX_CONCURRENT_CONTRACT = int(os.getenv("MAX_CONCURRENT_CONTRACT", "2"))
_CONTRACT_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_CONTRACT)


async def _run_review(*, request_id: str, tenant: str, directory_path: str):
    return await run_command_json(
        "review-contract",
        directory_path,
        schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
        request_id=request_id,
        tenant=tenant,
        conversation_id=new_conversation_id(),
    )


async def execute_contract_review_task(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    source_mode: str = "directory",
) -> None:
    """Gate on the concurrency semaphore, then run the contract review task."""
    async with _CONTRACT_SEMAPHORE:
        await _execute_inner(
            request_id=request_id,
            tenant=tenant,
            directory_path=directory_path,
            source_mode=source_mode,
        )


async def _execute_inner(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    source_mode: str,
) -> None:
    started_at = utc_now()
    with logging_context(request_id=request_id, tenant=tenant):
        upsert_contract_task(
            {
                "request_id": request_id,
                "tenant": tenant,
                "status": "running",
                "mode": source_mode,
                "source_mode": source_mode,
                "case_path": directory_path,
                "claim_id": None,
                "result_file": None,
                "session_id": None,
                "error_detail": None,
                "progress_message": "合同审查 Agent 正在运行中",
                "started_at": started_at,
                "updated_at": started_at,
            }
        )
        try:
            payload, meta = await asyncio.wait_for(
                _run_review(
                    request_id=request_id,
                    tenant=tenant,
                    directory_path=directory_path,
                ),
                timeout=CONTRACT_TIMEOUT_SEC,
            )
            # 落库合同结构（best-effort：结论已归档 result_store，落库失败不应翻成任务 failed）。
            if isinstance(payload, dict):
                try:
                    persist_contract_from_result(
                        payload, request_id=request_id, tenant=tenant, source_path=directory_path
                    )
                except Exception as exc:
                    logger.warning(
                        "contract persistence failed (result archived): %s",
                        exc,
                        extra={"request_id": request_id, "tenant": tenant},
                    )
            finished_at = utc_now()
            upsert_contract_task(
                {
                    "request_id": request_id,
                    "tenant": tenant,
                    "status": "completed",
                    "mode": source_mode,
                    "source_mode": source_mode,
                    "case_path": directory_path,
                    "claim_id": payload.get("claim_id") if isinstance(payload, dict) else None,
                    "result_file": meta.result_file,
                    "session_id": meta.claude_session_id,
                    "error_detail": None,
                    "progress_message": "合同审查完成",
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                }
            )
        except asyncio.TimeoutError:
            logger.warning(
                "contract_review_timeout",
                extra={
                    "request_id": request_id,
                    "tenant": tenant,
                    "route": "/contract/review",
                    "timeout_sec": CONTRACT_TIMEOUT_SEC,
                },
            )
            finished_at = utc_now()
            upsert_contract_task(
                {
                    "request_id": request_id,
                    "tenant": tenant,
                    "status": "failed",
                    "mode": source_mode,
                    "source_mode": source_mode,
                    "case_path": directory_path,
                    "claim_id": None,
                    "result_file": None,
                    "session_id": None,
                    "error_detail": (
                        f"合同审查超时：超过 {int(CONTRACT_TIMEOUT_SEC)}s 未返回结果"
                        "（可能模型网关拥塞），请稍后重试"
                    ),
                    "progress_message": "合同审查超时",
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                }
            )
        except Exception as exc:
            logger.exception(
                "contract_review_failed",
                extra={"request_id": request_id, "tenant": tenant, "route": "/contract/review"},
            )
            finished_at = utc_now()
            upsert_contract_task(
                {
                    "request_id": request_id,
                    "tenant": tenant,
                    "status": "failed",
                    "mode": source_mode,
                    "source_mode": source_mode,
                    "case_path": directory_path,
                    "claim_id": None,
                    "result_file": None,
                    "session_id": None,
                    "error_detail": str(exc),
                    "progress_message": "合同审查失败",
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                }
            )


def schedule_contract_review_task(
    *,
    request_id: str,
    tenant: str,
    directory_path: str,
    source_mode: str,
) -> None:
    """Fire-and-forget: schedule the contract review task as an asyncio background task."""
    asyncio.create_task(
        execute_contract_review_task(
            request_id=request_id,
            tenant=tenant,
            directory_path=directory_path,
            source_mode=source_mode,
        )
    )
