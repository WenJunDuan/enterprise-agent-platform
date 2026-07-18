"""D3 spike: expense prompt 投递机制三模式延迟对比 (设计见同 sprint route-note.md).

Mode A  = 生产现状: run_inline_directory_audit (AUDIT_INSTRUCTIONS 内联, setting_sources=[])
Mode B1 = command as-is: /audit <dir>, setting_sources=["project"], agent 自行 Glob/Read
Mode B2 = command + context 注入 (tender P4 形态): 指令来自 command 文件, 案件+规则内联

用法 (repo root): uv run python .ai_state/sprints/2026-07-18-prompt-single-source/spike/latency_spike.py
结果: 同目录 results.jsonl 逐 attempt 追加, 结束打印汇总。
评测工装, 非产品代码; server/ 零改动。
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# 重试统一由本 harness 控制 (三模式公平计次, 每 attempt 一条样本);
# 关掉 Mode A 生产路径的内部重试环, 否则 A 的墙钟里会混入不可见重试。
os.environ["AUDIT_CONTRACT_MAX_RETRY"] = "0"

from server.audit.runner import (  # noqa: E402
    build_inline_audit_prompt,
    load_case_block,
    load_expense_rules,
    run_inline_directory_audit,
)
from server.common.command_adapter import build_command_prompt, run_command_json  # noqa: E402
from server.core import DEFAULT_OUTPUT_SCHEMA_NAME  # noqa: E402
from server.platform.config import get_audit_settings  # noqa: E402

# 走规则路径的案件（出租车→expense_travel_005 明确不可报销→稳定 rejected+非空 policy_refs）。
# 不用 tests/eval_fixtures/placeholder-invoice：其数据真实性拒绝按 prompt 允许空 policy_refs，
# 会撞 _validate_audit_result 承重依据闸（prompt-闸矛盾，见 route-note.md 附录），污染时延样本。
CASE_DIR = ".ai_state/sprints/2026-07-18-prompt-single-source/spike/case-taxi"
ROUNDS = 3
MAX_ATTEMPTS = 2  # 1 正跑 + 1 重试, 三模式一致
ATTEMPT_TIMEOUT_SEC = 600
RESULTS = Path(__file__).with_name("results.jsonl")


def _b2_context() -> str:
    return (
        "## 本案材料(已内联, 无需再 Read/Glob)\n"
        + load_case_block(CASE_DIR)
        + "\n\n## 本地规则(已内联, 无需再 Read)\n"
        + load_expense_rules()
    )


async def _call(mode: str, tag: str):
    settings = get_audit_settings()
    if mode == "A":
        return await run_inline_directory_audit(
            CASE_DIR, request_id=tag, tenant=None, archive_to_results=False
        )
    if mode == "B1":
        # setting_sources 不传 → build_options 默认 ["project"] (载 CLAUDE.md + commands)
        return await run_command_json(
            "audit",
            CASE_DIR,
            schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
            structured=settings.structured_output,
            request_id=tag,
            tenant=None,
            archive_to_results=False,
            allowed_tools=["Read", "Glob"],
            max_turns=16,
        )
    return await run_command_json(
        "audit",
        CASE_DIR,
        schema_name=DEFAULT_OUTPUT_SCHEMA_NAME,
        structured=settings.structured_output,
        request_id=tag,
        tenant=None,
        archive_to_results=False,
        allowed_tools=settings.allowed_tools,
        max_turns=settings.inline_max_turns,
        context=_b2_context(),
    )


async def run_one(mode: str, rnd: int) -> bool:
    """跑一个 (mode, round), 失败重试一次; 返回是否最终成功。逐 attempt 落盘。"""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        tag = f"spike-{mode.lower()}-r{rnd}a{attempt}"
        started = time.monotonic()
        record: dict = {
            "mode": mode,
            "round": rnd,
            "attempt": attempt,
            "request_id": tag,
            "case": CASE_DIR,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            result, meta = await asyncio.wait_for(_call(mode, tag), ATTEMPT_TIMEOUT_SEC)
            record.update(
                ok=True,
                wall_s=round(time.monotonic() - started, 1),
                verdict=result.get("verdict"),
                manual_review_reason=result.get("manual_review_reason"),
                cost_usd=meta.cost_usd,
            )
        except Exception as exc:
            record.update(
                ok=False,
                wall_s=round(time.monotonic() - started, 1),
                error=f"{type(exc).__name__}: {exc}"[:300],
            )
        with RESULTS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(json.dumps(record, ensure_ascii=False), flush=True)
        if record.get("ok"):
            return True
    return False


def summarize() -> None:
    rows = [
        json.loads(line)
        for line in RESULTS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print("\n=== 汇总 (成功 attempt 墙钟秒) ===")
    for mode in ("A", "B1", "B2"):
        oks = [r["wall_s"] for r in rows if r["mode"] == mode and r.get("ok")]
        fails = sum(1 for r in rows if r["mode"] == mode and not r.get("ok"))
        verdicts = [r.get("verdict") for r in rows if r["mode"] == mode and r.get("ok")]
        if oks:
            print(
                f"{mode}: n={len(oks)} median={statistics.median(oks):.1f}s "
                f"min={min(oks):.1f}s max={max(oks):.1f}s "
                f"fail_attempts={fails} verdicts={verdicts}"
            )
        else:
            print(f"{mode}: 无成功样本 (fail_attempts={fails})")


async def main() -> int:
    settings = get_audit_settings()
    print(
        f"settings: lean_context={settings.lean_context} "
        f"structured={settings.structured_output} max_turns={settings.inline_max_turns} "
        f"model={os.environ.get('MODEL_NAME', '(unset)')}",
        flush=True,
    )
    print(
        f"prompt chars: A(inline)={len(build_inline_audit_prompt(CASE_DIR))} "
        f"B1(cmd)={len(build_command_prompt('audit', CASE_DIR))} "
        f"B2(cmd+context)={len(build_command_prompt('audit', CASE_DIR, context=_b2_context()))}",
        flush=True,
    )
    for rnd in range(1, ROUNDS + 1):
        for mode in ("A", "B1", "B2"):
            ok = await run_one(mode, rnd)
            if not ok and rnd == 1 and mode == "A":
                # return 而非 sys.exit: SystemExit 穿透事件循环会触发 SDK asyncgen aclose 噪音
                print("ABORT: 首轮 Mode A 两次尝试均失败, 判网关不可用, 终止整场。", flush=True)
                return 2
    summarize()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
