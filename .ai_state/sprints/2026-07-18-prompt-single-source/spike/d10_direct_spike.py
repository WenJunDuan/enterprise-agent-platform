"""D10① 直连 spike: anthropic SDK 直打网关, 绕开 claude-agent-sdk CLI 子进程.

Mode D  = 直连: build_inline_audit_prompt 同一产物作单条 user message, 一次网关往返;
          服务端同款抽取(contract._extract_json_object, 剥成对 <think>)+同款契约链
          (apply_schema_semantics)。无工具、无 CLI、无 agent loop。
Mode A-ctl = 生产 CLI 路径对照(各 case 1 次, 时段对齐控制组; A 完整基线=verify-results.jsonl 6 单)。

用法: uv run --with anthropic python .ai_state/sprints/2026-07-18-prompt-single-source/spike/d10_direct_spike.py
结果: 同目录 d10-results.jsonl。评测工装非产品代码; server/ 零改动。
_extract_json_object 是私有名——评测工装刻意绑定生产实际行为, 与产品代码同仓同步演进。
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from server.audit.runner import build_inline_audit_prompt, run_inline_directory_audit
from server.common.contract import _extract_json_object, apply_schema_semantics
from server.core import DEFAULT_OUTPUT_SCHEMA_NAME
from server.platform.config import configure_claude_runtime_env

CASES = {
    "placeholder": "tests/eval_fixtures/placeholder-invoice",
    "taxi": ".ai_state/sprints/2026-07-18-prompt-single-source/spike/case-taxi",
}
ROUNDS = 3
MAX_ATTEMPTS = 2  # 1 正跑 + 1 重试, 与 A 侧 harness 口径一致
ATTEMPT_TIMEOUT_SEC = 600
MAX_TOKENS = 16000  # 文本模式含 <think> 草稿, 给足余量防 max_tokens 截断
OUT = Path(__file__).with_name("d10-results.jsonl")


def _make_client() -> tuple[anthropic.AsyncAnthropic, str]:
    env = configure_claude_runtime_env()
    base_url = env["anthropic_base_url"]
    model = env["anthropic_model"]
    if not base_url or not model:
        print("ABORT: 网关未配置(anthropic_base_url/model 为空), 检查 .env", flush=True)
        sys.exit(2)
    kwargs: dict = {"base_url": base_url}
    if env["anthropic_auth_token"]:
        kwargs["auth_token"] = env["anthropic_auth_token"]
    elif env["anthropic_api_key"]:
        kwargs["api_key"] = env["anthropic_api_key"]
    return anthropic.AsyncAnthropic(**kwargs), model


async def _call_direct(client: anthropic.AsyncAnthropic, model: str, case_dir: str, tag: str) -> dict:
    prompt = build_inline_audit_prompt(case_dir)
    started = time.monotonic()
    resp = await client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    wall = time.monotonic() - started
    text = "".join(b.text for b in resp.content if b.type == "text")
    parsed = _extract_json_object(text)
    if parsed is None:
        raise ValueError(f"直连响应无可抽取 JSON (stop={resp.stop_reason}, text_len={len(text)})")
    result = apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, parsed, request_id=tag)
    return {
        "wall_s": round(wall, 1),
        "verdict": result.get("verdict"),
        "policy_refs": result.get("policy_refs"),
        "manual_review_reason": result.get("manual_review_reason"),
        "stop_reason": resp.stop_reason,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    }


async def _call_cli_control(case_dir: str, tag: str) -> dict:
    started = time.monotonic()
    result, meta = await run_inline_directory_audit(
        case_dir, request_id=tag, tenant=None, archive_to_results=False
    )
    return {
        "wall_s": round(time.monotonic() - started, 1),
        "verdict": result.get("verdict"),
        "policy_refs": result.get("policy_refs"),
        "manual_review_reason": result.get("manual_review_reason"),
        "cost_usd": meta.cost_usd,
    }


async def run_one(mode: str, case: str, rnd: int, call) -> None:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        tag = f"d10-{mode.lower()}-{case}-r{rnd}a{attempt}"
        rec: dict = {
            "mode": mode,
            "case": case,
            "round": rnd,
            "attempt": attempt,
            "request_id": tag,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        started = time.monotonic()
        try:
            rec.update(ok=True, **(await asyncio.wait_for(call(tag), ATTEMPT_TIMEOUT_SEC)))
        except anthropic.RateLimitError as exc:
            rec.update(ok=False, wall_s=round(time.monotonic() - started, 1), error=f"RateLimitError: {exc}"[:300])
        except anthropic.APIStatusError as exc:
            rec.update(ok=False, wall_s=round(time.monotonic() - started, 1), error=f"APIStatusError {exc.status_code}: {exc.message}"[:300])
        except anthropic.APIConnectionError as exc:
            rec.update(ok=False, wall_s=round(time.monotonic() - started, 1), error=f"APIConnectionError: {exc}"[:300])
        except Exception as exc:
            rec.update(ok=False, wall_s=round(time.monotonic() - started, 1), error=f"{type(exc).__name__}: {exc}"[:300])
        with OUT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        if rec.get("ok"):
            return


async def main() -> int:
    client, model = _make_client()
    print(f"direct spike: model={model} cases={list(CASES)} rounds={ROUNDS}", flush=True)
    # 控制组: 生产 CLI 路径各 case 1 次(时段对齐)
    for case, case_dir in CASES.items():
        await run_one("A-ctl", case, 0, lambda tag, d=case_dir: _call_cli_control(d, tag))
    # 直连: 各 case × 3 轮交错
    for rnd in range(1, ROUNDS + 1):
        for case, case_dir in CASES.items():
            await run_one("D", case, rnd, lambda tag, d=case_dir: _call_direct(client, model, d, tag))
    # 汇总
    rows = [json.loads(line) for line in OUT.read_text(encoding="utf-8").splitlines() if line.strip()]
    print("\n=== 汇总 ===", flush=True)
    for mode in ("A-ctl", "D"):
        oks = [r for r in rows if r["mode"] == mode and r.get("ok")]
        fails = sum(1 for r in rows if r["mode"] == mode and not r.get("ok"))
        walls = sorted(r["wall_s"] for r in oks)
        med = walls[len(walls) // 2] if walls else None
        print(
            f"{mode}: n_ok={len(oks)} median={med}s fails={fails} "
            f"verdicts={[(r['case'], r['verdict']) for r in oks]}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
