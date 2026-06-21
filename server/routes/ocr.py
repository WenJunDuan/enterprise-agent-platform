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
from server.routes.deps import verify_tenant
from server.routes.upload_helpers import (
    collect_uploaded_files,
    materialize_ocr_upload,
    remove_submission_dir,
    validate_directory_case_path,
)
from server.platform.paths import PROJECT_ROOT
from server.stores.request_store import new_request_id

logger = logging.getLogger(__name__)

# 表单回填映射硬超时（秒）。映射是 asyncio 协程（HTTP 可干净取消），故保留请求级超时。
# 注：识别（to_thread）不设请求超时——工作线程不可取消，超时释放信号量会让并发闸失效；
# 改由 MAX_CONCURRENT_OCR 信号量 + OCR 引擎 / litellm 自身超时兜底（见各端点注释）。
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
    """同步纯识别：upload（multipart）或 directory（tenant 子树）→ {request_id, results, block}。"""
    tenant = verify_tenant(authorization)
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
        case_path = validate_directory_case_path(
            req_payload.directory_path, tenant, expected_domain="ocr"
        )
    elif content_type.startswith("multipart/form-data"):
        form_data = await request.form()
        case_path = await materialize_ocr_upload(
            request_id=request_id,
            tenant=tenant,
            files=collect_uploaded_files(form_data),
        )
        cleanup_path = case_path  # 上传件识别后清理，directory 模式不动用户目录
    else:
        raise HTTPException(status_code=415, detail="Unsupported Content-Type")

    try:
        # 识别在信号量内运行至完成：to_thread 工作线程不可取消，若用 wait_for 超时会释放
        # 名额但线程继续 → 重复请求绕过并发闸、堆积 OCR 任务。故识别不设请求级超时，靠
        # OCR 引擎 / litellm 自身超时兜底，MAX_CONCURRENT_OCR 由此严格生效。排队不计入超时。
        async with _OCR_SEMAPHORE:
            recognized = await run_doc_recognize(case_path, run_seal=run_seal)
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
    """解析 multipart 里的 form_schema 字段为 JSON 对象。

    缺失 / 空 → 返回 ``{}`` 走**自适应抽取**模式（字段集由文档内容决定）；非法 JSON / 非对象抛 400。
    """
    text = str(raw or "").strip()
    if not text:
        return {}
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
    tenant = verify_tenant(authorization)
    request_id = new_request_id()

    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("multipart/form-data"):
        raise HTTPException(status_code=415, detail="ocr fill requires multipart/form-data")
    form_data = await request.form()
    form_schema = _parse_form_schema(form_data.get("form_schema"))
    case_path = await materialize_ocr_upload(
        request_id=request_id,
        tenant=tenant,
        files=collect_uploaded_files(form_data),
    )

    try:
        async with _OCR_SEMAPHORE:
            # 识别不设请求超时（同 /extract，线程不可取消，保并发闸严格）。
            recognized = await run_doc_recognize(case_path, run_seal=run_seal)
            # 映射是 asyncio 协程，HTTP 请求可被干净取消，故保留请求级超时。
            fill = await asyncio.wait_for(
                map_extraction_to_form(
                    recognized["block"], form_schema, request_id=request_id, tenant=tenant
                ),
                timeout=OCR_FILL_TIMEOUT_SEC,
            )
    except asyncio.TimeoutError as exc:
        # 映射超时：识别已完成、映射协程已取消，删目录安全。
        remove_submission_dir(case_path)
        logger.warning("ocr_fill_timeout", extra={"request_id": request_id})
        raise HTTPException(status_code=504, detail="表单回填超时（模型映射阶段）") from exc
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
