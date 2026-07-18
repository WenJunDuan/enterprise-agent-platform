"""D10② 多模态附件预嵌 POC(评测工装, 非产品代码; server/ 零改动).

背景: D10①直连路径丢了 claude-agent-sdk 的 Read 工具面(见 design.md 风险表:「直连丢
工具面(Read 附件)」)。若要在直连路径里内联发票/行程等图片附件, 需确认目标网关的
anthropic 协议端点是否支持 image content block(而非仅文本)。本脚本是最小可行探测,
不是预嵌正式实现。

做法: 构造一张含清晰文字「AI42」的小 PNG(base64 预置常量, 见下方 ``_TEST_IMAGE_PNG_B64``
——本仓库未装 pillow, 故不现场生成; 常量本身由本地一次性 pure-stdlib 脚本(struct+zlib,
不依赖 pillow)离线生成后固化, 可复现), 按 anthropic Messages API 的 image content block
格式发一次请求, 要求模型读出图中文字。

终止条件(design.md T4, critic F6 修订; 覆盖本次 POC 执行的两种可能结果, 两者都算 T4
完成, 不悬置):
  - 支持: 网关返回 200 且回答文本引用了图内文字(如包含 "AI42" / "AI" 与 "42"两者)
    → 记档本次调用摘要(wall_s/status/回答原文), 预嵌正式实施在后续任务另立。
  - 不支持: 网关返回 4xx(不支持 image block 类型), 或 200 但回答明确读不出图片内容
    (未引用图内文字, 如答"我看不到图片"/答案与文字无关)
    → 记档为降级 backlog, 直连路径的附件读取需求继续留给 T4 风险表里的兜底
    (「需读附件的案件走 CLI 路径」)。

用法(真网关执行, 由主 agent 验收时跑; 本 subagent 不打网关):
    uv run python .ai_state/sprints/2026-07-18-prompt-single-source/spike/d10_vision_poc.py

依赖: 仅 stdlib + 已在 pyproject 声明的 anthropic SDK(D10① T2 引入)。不需要 pillow。
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from server.platform.config import configure_claude_runtime_env

# 「AI42」白底黑字, 216x88 px 8-bit 灰度 PNG。离线生成(struct+zlib 手搓 PNG 编码器,
# 不依赖 pillow), 固化为常量供本 POC 反复复现使用, 不在运行时现场画图。
_TEST_IMAGE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAANgAAABYCAAAAACy+2bpAAAAqElEQVR42u3aSQ6AIAwAQP7/ab2bIFCtEZheWaeXhoZyLBoFDAwMDAwMDAwMDAxsUlipRO+81rraPk/vAwYGBga2N6z3gOh468JvnQcGBgYGBpYJu84bTQgYGBgYGNgdLPpwDBfUYGEffmiCgYGBgW0ByyrQ2YkDAwMDAwP7smGa1ogFAwMDAwMbaHRmfWCJ7g8GBgYGtidslQADAwMDAwMDAwMDA/t5nEufyGc4rit4AAAAAElFTkSuQmCC"
)

# 图中实际文字, 用于判定「回答是否引用了图内文字」(终止条件的机器可判定近似)。
_EXPECTED_TEXT = "AI42"

OUT = Path(__file__).with_name("d10-vision-poc-result.jsonl")


def _build_client() -> tuple[anthropic.AsyncAnthropic, str]:
    """构造直连 client; 复刻 server/audit/direct.py 的 trust_env=False 修复(D10① T2 实测:
    anthropic SDK 自带 DefaultAsyncHttpxClient 无视 trust_env 无条件读环境代理, sandbox/
    内网常见 SOCKS 代理环境变量下会直接 ImportError——POC 同样要绕开这个坑)。
    """
    import httpx

    env = configure_claude_runtime_env()
    base_url = env["anthropic_base_url"]
    model = env["anthropic_model"]
    if not base_url or not model:
        print("ABORT: 网关未配置(anthropic_base_url/model 为空), 检查 .env", flush=True)
        sys.exit(2)
    kwargs: dict = {"base_url": base_url, "http_client": httpx.AsyncClient(trust_env=False)}
    if env["anthropic_auth_token"]:
        kwargs["auth_token"] = env["anthropic_auth_token"]
    elif env["anthropic_api_key"]:
        kwargs["api_key"] = env["anthropic_api_key"]
    return anthropic.AsyncAnthropic(**kwargs), model


def _judge(response_text: str) -> str:
    """按终止条件把回答文本归类为 supported / unsupported / inconclusive。

    machine 近似: 回答里同时出现字母段("AI")与数字段("42")视为读出了图内文字。
    人工复核仍应过一遍原文(见落盘的 response_text), 这里只做粗判避免脚本悬置。
    """
    lowered = response_text.lower()
    has_letters = "ai" in lowered
    has_digits = "42" in lowered
    if has_letters and has_digits:
        return "supported"
    if not response_text.strip():
        return "inconclusive"
    return "unsupported"


async def main() -> int:
    client, model = _build_client()
    print(f"vision POC: model={model}", flush=True)

    image_block = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": _TEST_IMAGE_PNG_B64,
        },
    }
    text_block = {
        "type": "text",
        "text": (
            "图片里有一段白底黑字的文字/数字。只回答图片里写的内容, "
            "不要输出其它解释。"
        ),
    }

    record: dict = {
        "at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "expected_text": _EXPECTED_TEXT,
    }
    started = time.monotonic()
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=256,
            messages=[{"role": "user", "content": [image_block, text_block]}],
        )
    except anthropic.APIStatusError as exc:
        # 终止条件「不支持」分支之一: 网关对 image block 类型直接 4xx/5xx。
        record.update(
            ok=False,
            wall_s=round(time.monotonic() - started, 1),
            status_code=exc.status_code,
            error=f"APIStatusError {exc.status_code}: {exc.message}"[:500],
            verdict="unsupported",
        )
        _finish(record)
        return 0
    except Exception as exc:  # 传输类异常(连接/超时): POC 不区分, 一律记录为不可判定
        record.update(
            ok=False,
            wall_s=round(time.monotonic() - started, 1),
            error=f"{type(exc).__name__}: {exc}"[:500],
            verdict="inconclusive",
        )
        _finish(record)
        return 0

    wall_s = round(time.monotonic() - started, 1)
    response_text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )
    verdict = _judge(response_text)
    record.update(
        ok=True,
        wall_s=wall_s,
        stop_reason=response.stop_reason,
        response_text=response_text,
        verdict=verdict,
    )
    _finish(record)
    return 0


def _finish(record: dict) -> None:
    with OUT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)
    verdict = record.get("verdict")
    if verdict == "supported":
        print(
            "\n=== 终止条件: 支持 === 网关认得 image content block 且读出了图内文字"
            "（记档见上, 预嵌正式实施另立任务）。",
            flush=True,
        )
    elif verdict == "unsupported":
        print(
            "\n=== 终止条件: 不支持 === 降级 backlog"
            "（直连路径需读附件的案件继续走 CLI 路径, 见 design.md 风险表）。",
            flush=True,
        )
    else:
        print(
            "\n=== 不可判定 === 网络/超时类异常或空回答, 非「网关是否支持」的结论;"
            " 建议重跑一次而非据此下结论。",
            flush=True,
        )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
