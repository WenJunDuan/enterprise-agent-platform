#!/usr/bin/env python3
"""实测 S5/KD6 三条验收标准（AC9 出处保真 / AC10 证据取满 / AC11 去重），可复跑。

    uv run python scripts/measure_tender_evidence.py <投标底稿.txt> [招标底稿.txt]

底稿 = ``draft_render.render_body`` 的产物（带 ``【第N页】`` 页锚）。三条 AC 的基线均取自
2026-08-17 第四轮实测（`.ai_state/sprints/2026-08-15-tender-context-pipeline/evidence/
dry-run-2026-08-17.md`），门槛写在 :data:`THRESHOLDS`。

**不接受构造语料**：出处谎报、父子重复、命中块只有标题这三种形态都由真实标书的排版方式
产生（十进制编号小节、DFS 父子 span 嵌套、项名只出现在标题行），构造语料要么复现不出、
要么由构造直接保证，量出来的不是被交付的那条链路。
"""

from __future__ import annotations

import pathlib
import sqlite3
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# 事故项目（招标人ZJ直播间建设）的真实评分项，第四轮实测用的就是这 9 项。
# 换标书时整体替换——项名必须来自该次 criteria，不得凭印象编。
ITEMS = [
    {"item": "企业综合实力", "max": 6},
    {"item": "类似业绩", "max": 9},
    {"item": "拟派项目负责人", "max": 3},
    {"item": "技术参数指标", "max": 25},
    {"item": "直播间总体方案设计", "max": 15},
    {"item": "实施方案", "max": 5},
    {"item": "培训方案", "max": 3},
    {"item": "售后服务", "max": 4},
    {"item": "报价", "max": 30},
]

# 门槛与基线（第四轮实测 → 目标）。改动门槛必须同步改 design.md 的 AC9/AC10/AC11。
THRESHOLDS = {
    "label_match_rate": 1.0,  # AC9：自带小节标题的块，出处必须以它结尾（基线 0/4）
    "largest_item_chars": 3_000,  # AC10：技术参数指标 221 → ≥3,000
    "total_chars": 20_000,  # AC10：全项合计 3,480 → ≥20,000
}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    sys.path.insert(0, str(REPO_ROOT))
    from server.tender import evidence_index as ev
    from server.tender import evidence_retrieval as er
    from server.tender.evidence_chunks import build_chunks, slice_heading

    bid_text = pathlib.Path(argv[1]).read_text(encoding="utf-8", errors="replace")
    tender_text = (
        pathlib.Path(argv[2]).read_text(encoding="utf-8", errors="replace")
        if len(argv) > 2
        else "（未提供招标底稿）"
    )

    # ── AC11：去重 + 文档顺序 ────────────────────────────────────────────────
    started = time.perf_counter()
    chunks = build_chunks(bid_text, file_name=ev.BID_FILE, tag=ev.BID_TAG)
    elapsed = time.perf_counter() - started
    texts = [chunk["chunk_text"] for chunk in chunks]
    pages = [chunk["page_start"] for chunk in chunks if chunk["page_start"] is not None]
    unique_ok = len(texts) == len(set(texts))
    order_ok = pages == sorted(pages)
    print(f"[AC11] {len(chunks)} chunk / {elapsed:.2f}s（底稿 {len(bid_text):,} 字）")
    print(f"       正文无重复: {unique_ok}（不同正文 {len(set(texts))}）")
    print(f"       rowid 即文档顺序: {order_ok}")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ev.build_evidence_index(
        conn, tender_text=tender_text, bid_text=bid_text, project_id="measure"
    )

    # ── AC10：逐项证据量 ────────────────────────────────────────────────────
    # 逐项单独跑但**按全项数算预算**，否则单项独占全部额度，量出来的不是真实注入形态。
    print(f"[AC10] 逐项注入字数（预算按 {len(ITEMS)} 项分配）")
    per_item: dict[str, int] = {}
    for item in ITEMS:
        single = er.retrieve_evidence(
            {"items": [item]}, conn=conn, query_count_hint=len(ITEMS)
        )
        chars = sum(len(block.text) for block in single.blocks)
        per_item[item["item"]] = chars
        state = "unresolved" if single.unresolved else f"{len(single.blocks)} 块"
        print(f"       {item['item']:<12} {chars:>7,} 字  ({state})")

    result = er.retrieve_evidence({"items": ITEMS}, conn=conn)
    total_chars = sum(len(block.text) for block in result.blocks)
    budget = result.plan.evidence_tokens
    print(
        f"       合计 {len(result.blocks)} 块 / {total_chars:,} 字"
        f" = 额度 {budget:,} 的 {100 * total_chars / budget:.1f}%"
    )
    print(f"       unresolved={[u.item for u in result.unresolved]} truncated={result.truncated}")

    # ── AC9：出处保真 ────────────────────────────────────────────────────────
    labelled = matched = 0
    mismatches: list[str] = []
    for block in result.blocks:
        heading = slice_heading(block.text.splitlines())
        if heading is None:
            continue
        labelled += 1
        if block.chapter_path.endswith(heading):
            matched += 1
        else:
            mismatches.append(f"{block.chapter_path} ≠ {heading}")
    rate = matched / labelled if labelled else 1.0
    print(f"[AC9]  自带小节标题的块 {labelled} 个，出处相符 {matched} 个 = {100 * rate:.0f}%")
    for line in mismatches[:5]:
        print(f"       不符: {line}")

    conn.close()

    largest = per_item.get("技术参数指标", 0)
    checks = {
        "AC9 出处保真": rate >= THRESHOLDS["label_match_rate"],
        "AC10 单项取满": largest >= THRESHOLDS["largest_item_chars"],
        "AC10 全项取满": total_chars >= THRESHOLDS["total_chars"],
        "AC10 闭式账目": result.total_tokens <= budget,
        "AC11 去重": unique_ok,
        "AC11 文档顺序": order_ok,
    }
    for name, ok in checks.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
