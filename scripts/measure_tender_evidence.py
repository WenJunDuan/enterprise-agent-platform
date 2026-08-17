#!/usr/bin/env python3
"""实测证据层的与文档无关不变量（AC9 出处保真 / AC10 取量 / AC11 去重 / AC13 回退），可复跑。

    uv run python scripts/measure_tender_evidence.py \
        --bid <投标底稿.txt> [--tender <招标底稿.txt>] --criteria <criteria.json>

- 底稿 = ``draft_render.render_body`` 的产物（带 ``【第N页】`` 页锚）。
- `criteria.json` = 该次评标的项目规则，形如 `.claude/contracts/tender/criteria.schema.json`
  （`items[]` + 可选 `eligibility_rules[]`），即 `/tender-evaluate` S1 的产物。

**本脚本不内置任何项目的评分项。** 评分项因标书而异，写死等于把一次测试当成产品配置；
要测哪个项目就把该项目的 criteria 传进来。判据也一律是**与文档无关的不变量**（出处是否相符、
是否有重复正文、首块是否来自投标层、账目是否闭合），逐项字数只**报告**不判定——绝对字数是
单份标书的产物，拿它当门槛会把下一份标书判错。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sqlite3
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bid", required=True, help="投标底稿 txt")
    parser.add_argument("--tender", help="招标底稿 txt（缺省则只测投标层）")
    parser.add_argument("--criteria", required=True, help="criteria.json（该次评标的项目规则）")
    parser.add_argument("--label", default="", help="报告里显示的项目名（仅用于输出）")
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    sys.path.insert(0, str(REPO_ROOT))
    from server.tender import evidence_index as ev
    from server.tender import evidence_retrieval as er
    from server.tender.evidence_chunks import build_chunks, slice_heading

    criteria = json.loads(pathlib.Path(args.criteria).read_text(encoding="utf-8"))
    items = criteria.get("items") or []
    bid_text = pathlib.Path(args.bid).read_text(encoding="utf-8", errors="replace")
    tender_text = (
        pathlib.Path(args.tender).read_text(encoding="utf-8", errors="replace")
        if args.tender
        else "（未提供招标底稿）"
    )
    print(f"### {args.label or args.bid} — {len(items)} 个评分项")

    # ── AC11：去重 + 文档顺序（与文档无关的不变量）─────────────────────────────
    started = time.perf_counter()
    chunks = build_chunks(bid_text, file_name=ev.BID_FILE, tag=ev.BID_TAG)
    elapsed = time.perf_counter() - started
    texts = [chunk["chunk_text"] for chunk in chunks]
    pages = [chunk["page_start"] for chunk in chunks if chunk["page_start"] is not None]
    unique_ok = len(texts) == len(set(texts))
    order_ok = pages == sorted(pages)
    print(
        f"[AC11] 投标 {len(chunks)} chunk / {elapsed:.2f}s（底稿 {len(bid_text):,} 字）"
        f" 无重复={unique_ok} rowid即文档顺序={order_ok}"
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ev.build_evidence_index(conn, tender_text=tender_text, bid_text=bid_text, project_id="measure")

    # ── 逐项：报告取量与首块出处；判定只看不变量 ──────────────────────────────
    print("[AC10/AC13] 逐项（预算按全项数分配）")
    tender_first: list[str] = []
    unresolved_without_trace: list[str] = []
    for item in items:
        name = (item.get("item") or "").strip()
        single = er.retrieve_evidence({"items": [item]}, conn=conn, query_count_hint=len(items))
        chars = sum(len(block.text) for block in single.blocks)
        if single.blocks:
            first = single.blocks[0]
            head = slice_heading(first.text.splitlines()) or first.chapter_path
            state = f"{len(single.blocks)} 块 / {first.scope}"
            if first.scope != "bid":
                tender_first.append(name)
        else:
            head, state = "—", "unresolved"
            # 零命中必须留下两轮痕迹（整串 + 部分重合），否则用户分不清哪一轮没中
            queries = single.unresolved[0].queries if single.unresolved else []
            if not any("部分重合" in query for query in queries):
                unresolved_without_trace.append(name)
        print(f"       {name[:16]:<18} {chars:>7,} 字  ({state:<14}) 首块={head[:34]}")

    result = er.retrieve_evidence(criteria, conn=conn)
    total_chars = sum(len(block.text) for block in result.blocks)
    budget = result.plan.evidence_tokens if result.plan else 0
    share = f"{100 * total_chars / budget:.1f}%" if budget else "n/a"
    print(f"       合计 {len(result.blocks)} 块 / {total_chars:,} 字 = 额度 {budget:,} 的 {share}")
    print(f"       unresolved={[u.item for u in result.unresolved]} truncated={result.truncated}")

    # ── AC9：出处保真（与文档无关）───────────────────────────────────────────
    labelled = matched = 0
    for block in result.blocks:
        heading = slice_heading(block.text.splitlines())
        if heading is None:
            continue
        labelled += 1
        matched += block.chapter_path.endswith(heading)
    rate = matched / labelled if labelled else 1.0
    print(f"[AC9]  自带小节标题的块 {labelled} 个，出处相符 {matched} = {100 * rate:.0f}%")
    conn.close()

    checks = {
        "AC9 出处保真(标签=切片自身标题)": rate >= 1.0,
        "AC10 闭式账目(注入 ≤ 额度)": result.total_tokens <= budget,
        "AC10 投标层优先(首块非招标侧)": not tender_first,
        "AC11 无重复正文": unique_ok,
        "AC11 rowid=文档顺序": order_ok,
        "AC13 零命中留两轮痕迹": not unresolved_without_trace,
    }
    for name, ok in checks.items():
        print(f"{name}: {'PASS' if ok else 'FAIL'}")
    if tender_first:
        print(f"  ↳ 首块来自招标层的项（招标评分表抢位）：{tender_first}")
    if unresolved_without_trace:
        print(f"  ↳ 零命中却无回退痕迹的项：{unresolved_without_trace}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
