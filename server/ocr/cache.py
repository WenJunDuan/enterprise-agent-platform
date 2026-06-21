"""OCR/直读结果缓存：按文件内容 sha256 缓存 ``extract_one`` 产物，避免重评/重试重复识别。

格式无关（按内容 hash，数字 PDF / 扫描件 / Word / 图片一视同仁）；键含 purpose + run_seal
（二者影响识别结果，不可跨用）。落盘 ``data/ocr-cache/{key}.json``，跨重启 / 重评持久。
并发安全（临时文件 + 原子 rename 写，防 OCR 并行线程读到半截）。经 ``OCR_CACHE_ENABLED=0`` 关闭。
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from server.platform.paths import DATA_ROOT

OCR_CACHE_ENABLED = os.getenv("OCR_CACHE_ENABLED", "1").lower() in {"1", "true", "yes"}
_CACHE_DIR = DATA_ROOT / "ocr-cache"
# 缓存 schema 版本：产物结构变更时 bump，使旧缓存自动失效。
_CACHE_VERSION = "v1"


def _engine_fingerprint() -> str:
    """OCR 后端/模型指纹——换 backend/model/pipeline 时缓存自动失效（codex P1-2）。

    否则切 OCR_CLOUD、换 VL 模型或本地 pipeline 后，会静默复用旧后端的识别产物。
    """
    return "|".join(
        [
            _CACHE_VERSION,
            os.getenv("OCR_CLOUD", "0"),
            os.getenv("OCR_VL_MODEL_NAME", ""),
            os.getenv("OCR_VL_USE_PADDLE_PIPELINE", "0"),
        ]
    )


def _cache_key(content: bytes, purpose: str | None, run_seal: bool) -> str:
    """文件内容 + 引擎指纹 + purpose + run_seal 的复合指纹（识别条件不同则不复用缓存）。"""
    digest = hashlib.sha256(content)
    digest.update(b"|fp:" + _engine_fingerprint().encode("utf-8"))
    digest.update(b"|purpose:" + (purpose or "").encode("utf-8"))
    digest.update(b"|seal" if run_seal else b"|noseal")
    return digest.hexdigest()[:40]


def _read_bytes(path: Any) -> bytes | None:
    try:
        return Path(path).read_bytes()
    except OSError:
        return None


def get_cached(path: Any, *, purpose: str | None = None, run_seal: bool = False) -> dict | None:
    """命中返回缓存的识别产物 dict；未命中 / 未启用 / 读失败 → None。"""
    if not OCR_CACHE_ENABLED:
        return None
    content = _read_bytes(path)
    if content is None:
        return None
    cache_file = _CACHE_DIR / f"{_cache_key(content, purpose, run_seal)}.json"
    try:
        loaded = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def put_cached(
    path: Any, *, purpose: str | None = None, run_seal: bool = False, result: dict
) -> None:
    """写缓存（临时文件 + 原子 rename，并发安全）。任何失败静默——缓存绝不拖垮主识别流程。"""
    if not OCR_CACHE_ENABLED:
        return
    content = _read_bytes(path)
    if content is None:
        return
    cache_file = _CACHE_DIR / f"{_cache_key(content, purpose, run_seal)}.json"
    tmp_path: str | None = None
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=_CACHE_DIR, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False)
        os.replace(tmp_path, cache_file)  # 原子替换，防并行线程读到半截写入
        tmp_path = None
    except Exception:  # noqa: BLE001 - json.dump 对非 JSON 对象(Paddle layout)抛 Type/ValueError；
        # 缓存写失败绝不能向上抛(否则 ThreadPoolExecutor.map 重抛会 abort 整批 extract_dir，codex P1-3)。
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
