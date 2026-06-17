"""OCR 引擎客户端：PaddleOCR-VL 完整 pipeline + PaddleX 印章产线。

⚠️ 引擎 API 签名以实际安装的 paddleocr / paddlex 版本与部署的 serving 为准
（见 .claude/skills/multi-ocr/references/engines.md + 官方文档）；POC 阶段须对真实
文件/端点核对返回结构后定稿。要点（官方）：必须用完整 pipeline，不要只打裸 VLM 端点，
否则易掉精度/幻觉。依赖在函数内导入，缺失抛 OcrDependencyError。

PaddleOCR-VL 文档: https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html
PaddleX 印章产线: https://paddlepaddle.github.io/PaddleX/latest/pipeline_usage/tutorials/ocr_pipelines/seal_recognition.html
"""

from __future__ import annotations

import os
from pathlib import Path

from server.ocr import OcrDependencyError

# PaddleOCR-VL-1.6：当前 OmniDocBench v1.6 SOTA；版本/后端经 env 可调
OCR_VL_MODEL = os.getenv("OCR_VL_MODEL", "PaddleOCR-VL-1.6")
OCR_VL_BACKEND_URL = os.getenv("OCR_VL_BACKEND_URL")  # 例 http://paddleocr-vl:8118/v1
OCR_SEAL_PIPELINE = os.getenv("OCR_SEAL_PIPELINE", "seal_recognition")


def _build_vl_pipeline():
    """构造 PaddleOCR-VL 完整 pipeline。参数名以安装版本为准。"""
    try:
        from paddleocr import PaddleOCRVL
    except ImportError as exc:
        raise OcrDependencyError(
            "缺少 paddleocr：在 OCR venv 内 pip install 'paddleocr[doc-parser]>=3.4.0'"
        ) from exc
    kwargs: dict = {}
    if OCR_VL_BACKEND_URL:
        # 用 vLLM/SGLang 后端加速；具体关键字以版本为准，POC 核对
        kwargs["vl_rec_backend_url"] = OCR_VL_BACKEND_URL
    return PaddleOCRVL(**kwargs)


def _build_seal_pipeline():
    try:
        from paddlex import create_pipeline
    except ImportError as exc:
        raise OcrDependencyError("缺少 paddlex：pip install paddlex（印章产线）") from exc
    return create_pipeline(pipeline=OCR_SEAL_PIPELINE)


def recognize(path: Path) -> dict:
    """扫描件 → 每页 markdown + layout（PaddleOCR-VL 完整 pipeline）。"""
    results = _build_vl_pipeline().predict(str(path))
    pages = []
    for res in results:
        data = res.json if hasattr(res, "json") else {}
        pages.append(
            {
                "markdown": getattr(res, "markdown", "") or data.get("markdown", ""),
                "layout": data.get("layout", data.get("parsing_res_list", [])),
            }
        )
    return {"kind": "ocr", "model": OCR_VL_MODEL, "pages": pages}


def recognize_seal(path: Path) -> dict:
    """印章 → [{bbox, shape, text, color, confidence}, ...]（字段以版本返回为准）。"""
    results = _build_seal_pipeline().predict(str(path))
    seals: list[dict] = []
    for res in results:
        data = res.json if hasattr(res, "json") else {}
        for item in data.get("seal_res_list") or data.get("rec_texts") or []:
            seals.append(item if isinstance(item, dict) else {"text": item})
    return {"kind": "seal", "seals": seals}
