#!/usr/bin/env python3
"""实测双通道检索的召回率（AC0b，可复跑）。

    uv run python scripts/measure_tender_recall.py [底稿.txt]

判据定义（与 S0-B 一致）：对每个查询词，**Python 侧逐 chunk 子串匹配**的结果是 ground
truth（"原文里到底有没有"），检索层能否把它捞出来即为命中。命中率 = 有 ground truth 的
查询中被检索层捞到的比例；ground truth 本身为空的查询不计入分母（那是"真没有"，不是漏检）。

不传参数时用**等效构造**底稿（本机无部署机真实底稿）：查询词表取自 S0-B 用过的真实
criteria 项名与常见评分项名，2 字/≥3 字混合，覆盖该方案要防的失败形态。
"""

from __future__ import annotations

import pathlib
import sqlite3
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# S0-B 用过的真实 criteria 项名 + 评标常见项名。2 字词占比刻意偏高——它们正是裸用 FTS5 时
# 全军覆没的那一类（实测召回 38% 的主因）。
QUERIES = [
    "报价",
    "业绩",
    "工期",
    "资质",
    "质量",
    "工艺",
    "价格-最后报价",
    "投标报价",
    "施工组织设计",
    "项目负责人",
    "类似项目业绩",
    "企业信用",
    "安全生产许可证",
    "营业执照",
    "技术标",
    "商务标",
    "质量保证体系",
    "拟投入主要人员",
    "机械设备配置",
    "售后服务承诺",
]

# 等效构造底稿：章节结构 + 中文措辞贴近真实标书，覆盖上述查询词的自然出现形态。
_SECTIONS = [
    ("第一章 投标函", "投标报价：人民币壹佰贰拾万元整。工期 180 日历天。质量目标合格。"),
    ("第二章 商务标", "报价一览表如下，分部分项报价明细见附表。价格-最后报价以投标函为准。"),
    ("第三章 技术标", "施工组织设计详见本章。施工工艺流程、机械设备配置一览表附后。"),
    ("第四章 资格证明", "营业执照副本、安全生产许可证、企业信用报告扫描件附后。"),
    ("第五章 业绩证明", "类似项目业绩三项，项目负责人张三，均为近三年完工工程。"),
    ("第六章 人员配置", "拟投入主要人员名单、资质证书编号与在职证明附后。"),
    ("第七章 质量保证", "质量保证体系文件、售后服务承诺函见本章。"),
]


def _build_corpus() -> tuple[str, list[dict]]:
    """Return (full_text, chunks) for the equivalent-construction corpus."""
    chunks = []
    lines = []
    for index, (title, body) in enumerate(_SECTIONS):
        # 每章重复正文，把 chunk 拉到真实标书的量级（S0-B 中位 212 字、p90 3,453 字）。
        text = f"{title}\n" + (body + "\n") * 12
        lines.append(text)
        chunks.append(
            {
                "chunk_id": f"构造底稿.pdf#{index}",
                "file": "构造底稿.pdf",
                "chapter_path": title,
                "chapter_title": title,
                "tag": "bid",
                "page_start": index + 1,
                "page_end": index + 1,
                "page_artifact": "original",
                "chunk_text": text,
            }
        )
    return "\n".join(lines), chunks


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(REPO_ROOT))
    from server.ocr import rag
    from server.stores import rag_store
    from server.tender.evidence_chunks import build_chunks

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    if len(argv) > 1:
        # 走**生产路径**（章节切分 + 超长二次切分 + 页锚），不是另写一份简化流程——
        # 否则量的是脚本自己的实现，不是要交付的那条链路。
        body = pathlib.Path(argv[1]).read_text(encoding="utf-8", errors="replace")
        started = time.perf_counter()
        chunks = build_chunks(body, file_name="__bid__", tag="bid")
        rag_store.insert_rows(conn, chunks)
        conn.commit()
        elapsed = time.perf_counter() - started
        sizes = sorted(len(c["chunk_text"]) for c in chunks)
        print(
            f"索引 {len(chunks)} chunk / {elapsed:.2f}s（底稿 {argv[1]}，{len(body)} 字）；"
            f"chunk 字数 min {sizes[0]} / 中位 {sizes[len(sizes) // 2]} / max {sizes[-1]}"
        )
    else:
        _body, chunks = _build_corpus()
        rag_store.insert_rows(conn, chunks)
        print(f"索引 {len(chunks)} chunk（等效构造底稿；本机无部署机真实底稿）")

    scored = 0
    hit = 0
    control_hit = 0
    misses: list[str] = []
    control_misses: list[str] = []
    started = time.perf_counter()
    for query in QUERIES:
        truth = {c["chunk_id"] for c in chunks if query in c["chunk_text"]}
        if not truth:
            continue  # 原文真没有 → 不计入分母（那不是漏检）
        scored += 1
        found = {h["chunk_id"] for h in rag.search(query, conn=conn, limit=10)}
        if found & truth:
            hit += 1
        else:
            misses.append(query)
        # 对照组 = 改造前行为（裸走 FTS5）。没有它就无法判断本度量是真的在测东西，
        # 还是随便怎么实现都 100%。
        control_rows = rag_store.query_rows(
            conn, rag._escape_match_query(query), tag=None, limit=10
        )
        if {r["chunk_id"] for r in control_rows} & truth:
            control_hit += 1
        else:
            control_misses.append(query)
    elapsed_ms = (time.perf_counter() - started) * 1000

    rate = 100.0 * hit / scored if scored else 0.0
    print(f"召回 {hit}/{scored} = {rate:.0f}%  ({elapsed_ms:.1f}ms)")
    if misses:
        print(f"漏检: {', '.join(misses)}")
    print(f"对照组(仅 FTS5，改造前): {control_hit}/{scored} = {100.0 * control_hit / scored:.0f}%")
    if control_misses:
        print(f"对照组漏检: {', '.join(control_misses)}")

    fts_ids = {r[0] for r in conn.execute("SELECT chunk_id FROM rag_chunks")}
    scan_ids = {r[0] for r in conn.execute(f"SELECT chunk_id FROM {rag_store.SCAN_TABLE_NAME}")}
    print(f"两表 chunk_id 一致: {fts_ids == scan_ids} (fts={len(fts_ids)} scan={len(scan_ids)})")

    # AC0b 门槛 88%，取自 S0-B 实测；跌破即按 design「已调研方案」表升级 map-reduce。
    ok = rate >= 88.0 and fts_ids == scan_ids
    print("AC0b:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
