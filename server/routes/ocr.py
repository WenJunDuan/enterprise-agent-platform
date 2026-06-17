"""OCR document recognition routes: POST /ocr/extract, POST /ocr/fill.

给外部系统单独调用的「纯识别」能力（/ocr/extract）+ 本平台 UI 演示「识别→回填」
（/ocr/fill）：上传文档（或指定 data/ 下目录）→ 同步返回结构化识别底稿。

与 /audit 的区别：纯确定性识别，**不做表单回填、不调模型**（/extract）；同步返回，
无异步任务。扫描件经 OCR 引擎（PaddleOCR-VL），每文件错误已在 pipeline 内隔离
（标 error），单个失败不拖垮整批。识别在线程池执行，不阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from server.ocr import OcrError
from server.ocr.runner import map_extraction_to_form, run_doc_recognize
from server.routes.upload_helpers import (
    materialize_ocr_upload,
    remove_submission_dir,
    validate_directory_case_path,
)
from server.platform.paths import PROJECT_ROOT
from server.stores.request_store import new_request_id

logger = logging.getLogger(__name__)

# 同步识别硬超时（秒）。扫描件经 PaddleOCR-VL 可能慢，给足余量但兜底防无限挂起。
OCR_EXTRACT_TIMEOUT_SEC = float(os.getenv("OCR_EXTRACT_TIMEOUT_SEC", "120"))
# 表单回填硬超时（秒）。含一次模型映射往返，给足余量（对齐 audit）。
OCR_FILL_TIMEOUT_SEC = float(os.getenv("OCR_FILL_TIMEOUT_SEC", "180"))
# 并发闸：每次识别可能拉起 OCR 引擎（CPU/GPU 重），无上限并发会打爆机器内存/算力。
# 超额提交在信号量处排队（排队时间不计入识别超时）。
MAX_CONCURRENT_OCR = int(os.getenv("MAX_CONCURRENT_OCR", "2"))
_OCR_SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_OCR)

router = APIRouter(tags=["ocr"])


class DirectoryExtractRequest(BaseModel):
    mode: Literal["directory"]
    directory_path: str


def _public_results(results: list[dict[str, Any]], base_dir: str) -> list[dict[str, Any]]:
    """出口投影：path 收窄为相对提交目录的路径，隐藏 host 绝对前缀且保留子目录区分。

    upload 模式文件平铺在 case_dir 下 → 相对路径即文件名；directory 模式可能有子目录
    （a/x.pdf、b/x.pdf）→ 保留相对路径以区分，避免 basename 塌成重名。越界兜底为文件名。
    """
    base = Path(base_dir).resolve()
    for item in results:
        path = item.get("path")
        if isinstance(path, str):
            try:
                item["path"] = str(Path(path).resolve().relative_to(base))
            except ValueError:
                item["path"] = Path(path).name
    return results


@router.post("/extract")
async def ocr_extract(
    request: Request,
    authorization: str | None = Header(None),
    run_seal: bool = Query(False, description="是否对扫描件追加印章识别"),
) -> dict[str, Any]:
    """同步纯识别：upload（multipart）或 directory（data/ 下）→ {request_id, results, block}。"""
    from server.api import verify_tenant  # lazy import breaks import cycle api↔routes

    verify_tenant(authorization)
    request_id = new_request_id()

    content_type = request.headers.get("content-type", "")
    cleanup_path: str | None = None
    if content_type.startswith("application/json"):
        try:
            raw_body = await request.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
        try:
            req_payload = DirectoryExtractRequest.model_validate(raw_body)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc
        case_path = validate_directory_case_path(req_payload.directory_path)
    elif content_type.startswith("multipart/form-data"):
        form_data = await request.form()
        case_path = await materialize_ocr_upload(
            request_id=request_id,
            files=form_data.getlist("files"),
        )
        cleanup_path = case_path  # 上传件识别后清理，directory 模式不动用户目录
    else:
        raise HTTPException(status_code=415, detail="Unsupported Content-Type")

    try:
        # 排队不计入识别超时：信号量在外，硬超时在 run_doc_recognize 内。
        async with _OCR_SEMAPHORE:
            recognized = await run_doc_recognize(
                case_path,
                run_seal=run_seal,
                timeout_sec=OCR_EXTRACT_TIMEOUT_SEC,
            )
    except asyncio.TimeoutError as exc:
        # 软超时：to_thread 工作线程无法强制取消、可能仍在读 case_dir。此处**不删**
        # 上传目录（避免与仍在跑的线程竞争），残留由 maintenance 按 retention 兜底清理。
        logger.warning(
            "ocr_extract_timeout",
            extra={"request_id": request_id, "timeout_sec": OCR_EXTRACT_TIMEOUT_SEC},
        )
        raise HTTPException(
            status_code=504,
            detail=f"识别超时：超过 {int(OCR_EXTRACT_TIMEOUT_SEC)}s 未完成",
        ) from exc
    except OcrError as exc:
        remove_submission_dir(cleanup_path)
        logger.warning("ocr_extract_failed", extra={"request_id": request_id})
        raise HTTPException(status_code=422, detail=f"识别失败：{exc}") from exc
    except Exception:
        remove_submission_dir(cleanup_path)
        raise

    remove_submission_dir(cleanup_path)
    base_abs = (Path(case_path) if Path(case_path).is_absolute() else PROJECT_ROOT / case_path).resolve()
    recognized["results"] = _public_results(recognized["results"], str(base_abs))
    return {"request_id": request_id, **recognized}


def _parse_form_schema(raw: Any) -> dict[str, Any]:
    """解析 multipart 里的 form_schema 字段为 JSON 对象；缺失 / 非法抛 400。"""
    text = str(raw or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="ocr fill requires form_schema (JSON object)")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="form_schema must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="form_schema must decode to a JSON object")
    return parsed


@router.post("/fill")
async def ocr_fill(
    request: Request,
    authorization: str | None = Header(None),
    run_seal: bool = Query(False, description="是否对扫描件追加印章识别"),
) -> dict[str, Any]:
    """同步识别 + 表单回填：upload + form_schema → {request_id, results, block, fill}。

    供本平台 UI 演示「识别 → 回填」全链路：先 run_doc_recognize（确定性识别，可拿底稿），
    再 map_extraction_to_form（一次模型映射 → form-fill 契约）。需配好模型网关；扫描件
    需 OCR serving。一次响应同时给底稿（results/block，左栏）与回填（fill，右栏）。
    """
    from server.api import verify_tenant  # lazy import breaks import cycle api↔routes

    tenant = verify_tenant(authorization)
    request_id = new_request_id()

    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("multipart/form-data"):
        raise HTTPException(status_code=415, detail="ocr fill requires multipart/form-data")
    form_data = await request.form()
    form_schema = _parse_form_schema(form_data.get("form_schema"))
    case_path = await materialize_ocr_upload(
        request_id=request_id,
        files=form_data.getlist("files"),
    )

    try:
        async with _OCR_SEMAPHORE:
            recognized = await run_doc_recognize(
                case_path, run_seal=run_seal, timeout_sec=OCR_EXTRACT_TIMEOUT_SEC
            )
            fill = await asyncio.wait_for(
                map_extraction_to_form(
                    recognized["block"], form_schema, request_id=request_id, tenant=tenant
                ),
                timeout=OCR_FILL_TIMEOUT_SEC,
            )
    except asyncio.TimeoutError as exc:
        # 软超时（同 /extract）：识别线程可能仍在跑，不删上传目录，留给 maintenance。
        logger.warning("ocr_fill_timeout", extra={"request_id": request_id})
        raise HTTPException(status_code=504, detail="识别或回填超时") from exc
    except OcrError as exc:
        remove_submission_dir(case_path)
        logger.warning("ocr_fill_recognize_failed", extra={"request_id": request_id})
        raise HTTPException(status_code=422, detail=f"识别失败：{exc}") from exc
    except Exception as exc:  # 映射阶段：模型不通 / 契约校验失败 → 上游问题
        remove_submission_dir(case_path)
        logger.exception("ocr_fill_mapping_failed", extra={"request_id": request_id})
        raise HTTPException(status_code=502, detail="表单回填失败（模型映射阶段）") from exc

    remove_submission_dir(case_path)
    base_abs = (Path(case_path) if Path(case_path).is_absolute() else PROJECT_ROOT / case_path).resolve()
    return {
        "request_id": request_id,
        "results": _public_results(recognized["results"], str(base_abs)),
        "block": recognized["block"],
        "fill": fill,
    }
