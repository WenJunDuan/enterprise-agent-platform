"""判定时刻带图问答：给定（文件, 页, 问题）→ 渲染该页为图 → 带图问 VLM → 返回纯文本答案。

为何存在（纠偏令 v2 二节）：证书有效期 / 公章归属 / 大写金额 / 检测报告标识这类判定点是
**像素必需**的——扫描盖章页的 OCR 转写常为空或失真，"换姿势转写"（提 DPI / 印章产线 / 换引擎）
只是把图片降维成有损文字再去检索。本 skill 不转写，只在**判定时刻**就一个具体问题带图问一次。

与 ocr-page 的分工：要**整页文字**（核页锚、逐字引原文）用 ocr-page；要**一个判定结论**
（这页的章是谁的 / 有效期到哪天）用本 skill。答案是模型读图的结论，**不是可逐字回查的原文**，
故引证据时页码仍取底稿 `【第N页】` 锚点。

用法：
    uv run python .claude/skills/vision-page/vision.py <PDF绝对路径> --page N --question "问句"

只读：不写任何文件（渲染的临时单页 PDF 用完即删）、不改库；失败打印到 stderr 并以非 0 退出，
供 agent 据此回落（4=渲染失败 / 5=VLM 不可用 → 转写次选或按"读不清"降 manual_review）。
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path
from types import ModuleType

# 端点配置面。**刻意与 OCR 转写解耦**：OCR_CLOUD=1 的部署里 OCR_VL_SERVER_URL 是 aistudio
# 云 job API（异步 job-poll，不是 chat/completions），拿它带图问答会直接失败；且转写模型与
# 问答模型未必是同一个。未设这三项时回落 OCR_VL_*，OCR_CLOUD=0 的 litellm 部署零配置可用。
_URL_ENV = "VISION_PAGE_URL"
_MODEL_ENV = "VISION_PAGE_MODEL"
_API_KEY_ENV = "VISION_PAGE_API_KEY"

# 退出码：2=入参不合法，3=服务端包加载不了，4=渲染失败，5=VLM 未配置/调用失败。
# 分开是为了让 agent 能区分"这页取不到图"（回落转写）与"问答端点不可用"（整条 vision 路径不可用）。
_EXIT_BAD_INPUT = 2
_EXIT_DEPENDENCY = 3
_EXIT_RENDER_FAILED = 4
_EXIT_VLM_FAILED = 5

_PROMPT = (
    "这是待核验文件的第 {page} 页图像。只依据图中可见内容回答问题：不要推测，不要补充图中"
    "没有的信息；看不清或图中没有该信息时，直接回答「图中看不清」或「图中没有该信息」。"
    "只输出答案本身，不要复述问题、不要解释推理过程。\n问题：{question}"
)


class VisionPageError(Exception):
    """带退出码的结构化失败。

    边界纪律：本 skill 是 agent 的工具面，异常一律在 :func:`main` 归一成一行 ``[错误] …``，
    绝不把堆栈丢给模型（堆栈既无助于它决策，又会把服务端内部路径带进评标上下文）。
    """

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _load_backend() -> tuple[ModuleType, ModuleType, ModuleType]:
    """延迟加载服务端 OCR 包（本 skill 以独立脚本分发，不随服务端一起 import）。

    Returns:
        ``(cloud_chunk, engine, vlm_client)`` 三个模块。

    Raises:
        VisionPageError: 服务端包不可用（退出码 3），供 agent 回落人工。
    """
    try:
        return (
            importlib.import_module("server.ocr.cloud_chunk"),
            importlib.import_module("server.ocr.engine"),
            importlib.import_module("server.ocr.vlm_client"),
        )
    except Exception as exc:  # noqa: BLE001 - 工具面边界：明确报错供 agent 回落
        raise VisionPageError(f"无法加载服务端 OCR 包：{exc}", _EXIT_DEPENDENCY) from exc


def _validate_input(path: Path, page: int, question: str) -> None:
    """入参闸：文件在场、是 PDF、页号为正、问句非空。"""
    if not path.is_file():
        raise VisionPageError(f"文件不存在或非文件：{path}", _EXIT_BAD_INPUT)
    if path.suffix.lower() != ".pdf":
        raise VisionPageError(
            f"只支持 PDF 页渲染，收到 {path.suffix or '无扩展名'}；其它形态请用 ocr-page 转写",
            _EXIT_BAD_INPUT,
        )
    if page < 1:
        raise VisionPageError(f"页号必须是正整数，收到 {page}", _EXIT_BAD_INPUT)
    if not question.strip():
        raise VisionPageError("问句不能为空", _EXIT_BAD_INPUT)


def _render_page_data_url(engine: ModuleType, path: Path, page: int) -> str:
    """把第 ``page`` 页（1-based）渲染成 PNG data URL。

    先用 ``extract_pdf_subset`` 抽出单页临时 PDF，再交隔离渲染进程
    （``server.ocr.page_render_worker``，带像素/字节/超时上界）渲染——**只渲染这一页**：
    直接迭代整份会把前面所有页都渲染一遍，300 页的标书要等到第 300 页才拿到图。

    Raises:
        VisionPageError: 抽页或渲染失败（退出码 4）。
    """
    subset = engine.extract_pdf_subset(path, [page - 1])
    if subset is None:
        raise VisionPageError(
            f"抽不出第 {page} 页（文件不可读或缺 pymupdf）：{path.name}", _EXIT_RENDER_FAILED
        )
    try:
        rendered = list(engine._iter_pdf_pages(subset))
    except Exception as exc:  # noqa: BLE001 - 渲染层错误归一为一行诊断
        raise VisionPageError(f"第 {page} 页渲染失败：{exc}", _EXIT_RENDER_FAILED) from exc
    finally:
        try:
            subset.unlink()
        except OSError:
            pass
    if not rendered:
        raise VisionPageError(f"第 {page} 页渲染结果为空", _EXIT_RENDER_FAILED)
    frame = rendered[0]
    return engine._image_data_url(frame["content"], frame.get("mime_type") or "image/png")


def _ask_vlm(
    engine: ModuleType, vlm_client: ModuleType, *, data_url: str, page: int, question: str
) -> str:
    """带图发一次问答请求，返回答案文本。

    Raises:
        VisionPageError: 端点未配置或调用失败（退出码 5）。
    """
    url = (os.getenv(_URL_ENV) or engine.OCR_VL_SERVER_URL or "").strip()
    model = (os.getenv(_MODEL_ENV) or engine.OCR_VL_MODEL_NAME or "").strip()
    if not url or not model:
        raise VisionPageError(
            f"VLM 未配置：请设 {_URL_ENV} / {_MODEL_ENV} 指向 OpenAI 兼容的带图问答端点"
            "（未设时回落 OCR_VL_SERVER_URL / OCR_VL_MODEL_NAME）",
            _EXIT_VLM_FAILED,
        )
    try:
        answer = vlm_client.call_vlm(
            url=engine._chat_completions_url(url),
            model=model,
            api_key=os.getenv(_API_KEY_ENV) or engine.OCR_VL_API_KEY,
            data_url=data_url,
            prompt=_PROMPT.format(page=page, question=question),
            timeout=min(engine.OCR_VL_TIMEOUT, engine.OCR_PAGE_TIMEOUT_SEC),
            ssl_context=engine._SSL_CONTEXT,
        )
    except Exception as exc:  # noqa: BLE001 - 工具面边界：远端失败归一为一行诊断
        raise VisionPageError(f"VLM 调用失败：{exc}", _EXIT_VLM_FAILED) from exc
    return answer.strip()


def answer_page_question(path: Path, page: int, question: str) -> str:
    """渲染 ``path`` 的第 ``page`` 页并就 ``question`` 问一次 VLM，返回纯文本答案。

    Args:
        path: 待核验 PDF 的路径。
        page: 页号（1-based，取底稿 ``【第N页】`` 锚点）。
        question: 只问一个判定点的问句。

    Returns:
        VLM 的答案文本（已 strip）。

    Raises:
        VisionPageError: 入参不合法 / 依赖不可用 / 渲染失败 / VLM 不可用。
    """
    _validate_input(path, page, question)
    cloud_chunk, engine, vlm_client = _load_backend()
    page_count = cloud_chunk.pdf_page_count(path)
    if page_count is not None and page > page_count:
        raise VisionPageError(
            f"页码越界：{path.name} 共 {page_count} 页，请求第 {page} 页", _EXIT_BAD_INPUT
        )
    data_url = _render_page_data_url(engine, path, page)
    return _ask_vlm(engine, vlm_client, data_url=data_url, page=page, question=question)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="对指定 PDF 的指定页带图提问（判定时刻问答）")
    parser.add_argument("file", help="待核验 PDF 的绝对路径（评标目录内的真实文件）")
    parser.add_argument(
        "--page", type=int, required=True, help="页号（1-based，取底稿【第N页】锚点）"
    )
    parser.add_argument("--question", required=True, help="只问一个判定点的问句")
    args = parser.parse_args(argv)
    try:
        print(answer_page_question(Path(args.file), args.page, args.question))
    except VisionPageError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return exc.exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
