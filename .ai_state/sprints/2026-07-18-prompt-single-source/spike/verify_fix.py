"""fix(audit) 07f1dc8 真网关验收: 生产形态(内部 contract 重试开)复跑两条路径各 3 次.

- placeholder(tests/eval_fixtures/placeholder-invoice): 数据真实性路径, 修复前 flash 必挂
  (空 policy_refs 撞承重闸)。期望: rejected + 非空 policy_refs(引反虚报类规则), 或合法降级
  manual_review(data_conflict/invoice_invalid)——两者都算过闸, rejected 为佳。
- taxi(spike/case-taxi): 规则路径, 对照 spike 基线看 explanation 漏字段率是否改善。

用法 (repo root): uv run python .ai_state/sprints/2026-07-18-prompt-single-source/spike/verify_fix.py
结果: 同目录 verify-results.jsonl。评测工装, 非产品代码。
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from server.audit.runner import run_inline_directory_audit

CASES = {
    "placeholder": "tests/eval_fixtures/placeholder-invoice",
    "taxi": ".ai_state/sprints/2026-07-18-prompt-single-source/spike/case-taxi",
}
ROUNDS = 3
ATTEMPT_TIMEOUT_SEC = 600
OUT = Path(__file__).with_name("verify-results.jsonl")


async def main() -> int:
    fails = 0
    for rnd in range(1, ROUNDS + 1):
        for name, case_dir in CASES.items():
            tag = f"verify-{name}-r{rnd}"
            started = time.monotonic()
            rec: dict = {
                "case": name,
                "round": rnd,
                "request_id": tag,
                "at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                result, meta = await asyncio.wait_for(
                    run_inline_directory_audit(
                        case_dir, request_id=tag, tenant=None, archive_to_results=False
                    ),
                    ATTEMPT_TIMEOUT_SEC,
                )
                rec.update(
                    ok=True,
                    wall_s=round(time.monotonic() - started, 1),
                    verdict=result.get("verdict"),
                    policy_refs=result.get("policy_refs"),
                    manual_review_reason=result.get("manual_review_reason"),
                    cost_usd=meta.cost_usd,
                )
            except Exception as exc:
                fails += 1
                rec.update(
                    ok=False,
                    wall_s=round(time.monotonic() - started, 1),
                    error=f"{type(exc).__name__}: {exc}"[:300],
                )
            with OUT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(json.dumps(rec, ensure_ascii=False), flush=True)
    print(f"done fails={fails}", flush=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
