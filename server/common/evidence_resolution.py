"""Evidence-resolution gate: deterministically verify that every cited source in a
tender verdict actually exists in this case's OCR/底稿 (anti-fabrication + 定位回查).

业务背景：评标结论里模型引用的每条出处 ``(文件, 第N页, 原文 quote)``，此前**无任何代码**
回查它是否真在本案底稿里——靠提示词自检不可靠（8636 页远超模型可核实范围，会脑补页码/原文）。
本模块在结论后处理（``apply_schema_semantics`` 的 ``resolve`` hook）拿到本案底稿，对每条出处的
逐字 quote 做确定性回查，分四档（resolved / page_mismatch / weak_match / unresolved），仅
``unresolved`` 降级承重评分项为 ``manual_review``，把"定位不准/引文不实"从静默通过变成可抓、可降级。

设计哲学（对齐 [[learning-absence-is-not-zero]] / 校验层兜底）：
- **存在性=主信号**：「原文是否在该 tier 底稿里」是抗编造的稳健硬信号（与具体文件无关）；
  file/page 精度只作细化标注，绝不单独支撑 resolved（19 家投标各自 ``【第N页】`` 从 1 重置，
  按 ``(tier, page)`` 索引会跨文件误命中 → 必须 file 级）。
- **宁漏勿误杀**：双阈值 + 中间带 ``weak_match`` 不降级（模型转述非逐字易触发，先漏报勿误杀）。
- **失败安全**：任何异常 → 原样返回结论，绝不因回查崩掉评标。

纯函数 + 无副作用（除原地标注传入的 output），无 SDK / 网络依赖。
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)

# ── 配置（运行时动态读 env，便于 dogfood 灰度调参，对齐 tender_worker 既有 env 模式）──────


def _enabled() -> bool:
    """Whole gate on/off (``TENDER_EVIDENCE_RESOLUTION``, default on)."""
    return os.getenv("TENDER_EVIDENCE_RESOLUTION", "1").lower() in {"1", "true", "yes"}


def _downgrade_enabled() -> bool:
    """是否对 unresolved 承重项降级 + 升 verdict（``EVIDENCE_RESOLUTION_DOWNGRADE``, default on）。

    首轮 dogfood 可设 0 看纯标注命中率/假阴性率，调好阈值再开降级。
    """
    return os.getenv("EVIDENCE_RESOLUTION_DOWNGRADE", "1").lower() in {"1", "true", "yes"}


def _annotate_resolved() -> bool:
    """resolved 项是否也写 ``resolution`` 标注（默认开，便于 dogfood 统计；0 = 只标异常）。"""
    return os.getenv("RESOLUTION_ANNOTATE_RESOLVED", "1").lower() in {"1", "true", "yes"}


def _f(env: str, default: float) -> float:
    """Read a float env with a safe fallback (非法值回落默认，不崩)。"""
    try:
        return float(os.getenv(env, str(default)))
    except (TypeError, ValueError):
        return default


def _i(env: str, default: int) -> int:
    try:
        return int(os.getenv(env, str(default)))
    except (TypeError, ValueError):
        return default


# 匹配阈值（k-gram 覆盖率 / 逐字命中）。verbatim 命中恒 1.0；中间带不降级。
def _resolve_threshold() -> float:
    return _f("EVIDENCE_RESOLVE_THRESHOLD", 0.65)


def _absent_threshold() -> float:
    return _f("EVIDENCE_ABSENT_THRESHOLD", 0.30)


def _min_quote_chars() -> int:
    return _i("EVIDENCE_MIN_QUOTE_CHARS", 8)


def _page_window() -> int:
    return _i("EVIDENCE_PAGE_WINDOW", 1)


def _kgram() -> int:
    return _i("EVIDENCE_KGRAM", 6)


def _max_corpus_chars() -> int:
    # k-gram 兜底语料上限（防病态成本）。底稿本身已被 build_extraction_block 截到 ~200k/文件，
    # 故默认放宽到 4M（≈20 文件），超限按首尾各半截（绝不只取前 N，避免重蹈 BOQ 尾部丢失）。
    return _i("EVIDENCE_MAX_CORPUS_CHARS", 4_000_000)


# ── 底稿解析（file-level 索引）──────────────────────────────────────────────────

# tier 外层标记（doc-layer 路径有：``=== 招标文件底稿 ===`` / ``=== 投标文件（X）底稿 ===``）
_TIER_RE = re.compile(r"^\s*={2,}\s*(.+?)\s*={2,}\s*$")
# 文件头（两路径都有，build_extraction_block）：``### 文件: <name> (kind=..., route=...)``
_FILE_RE = re.compile(r"^\s*#{2,}\s*文件[:：]\s*(.+?)\s*$")
# 页锚点（_page_anchor 产 ``【第 N 页】``，带空格 → 正则吃空白）
_PAGE_RE = re.compile(r"^\s*【第\s*(\d+)\s*页】\s*$")


def _tier_of(label: str) -> str:
    """从 tier 标记或文件名推断业务层：招标→tender / 投标→bid / 否则→whole。"""
    if "招标" in label:
        return "tender"
    if "投标" in label:
        return "bid"
    return "whole"


def normalize_text(text: str) -> str:
    """激进规范化（治模型转述/全半角/标点/空白差异）：NFKC 全角→半角 + 小写 + 去所有空白
    + 去标点/符号（含 ``【】《》()，。`` 等装饰）。quote 与底稿用**同一套**。"""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).lower()
    out: list[str] = []
    for ch in text:
        if ch.isspace():
            continue
        cat = unicodedata.category(ch)
        if cat[0] in {"P", "S", "C"}:  # 标点/符号/控制字符 → 去掉
            continue
        out.append(ch)
    return "".join(out)


# 文件头切分：纯文件名 = 首个 ``(kind=`` 或 **已知方括号标记** 之前。只在 ``[检出印章`` /
# ``[⚠清晰度`` / ``[清晰度`` 处切，**不切文件名里的普通 ``[``**（如 file[1].pdf，reviewer F2）。
_FILE_HEAD_SPLIT_RE = re.compile(r"\s*\(kind=|\s*\[(?:检出印章|⚠?清晰度)")


def _parse_file_head(head: str) -> tuple[str, str]:
    """从 ``### 文件:`` 头串解析 (纯文件名, clarity)。

    clarity: ``[⚠清晰度低`` → low；``[清晰度未知`` → unknown；否则 clear（R3 confidence 消费）。
    """
    clarity = "low" if "清晰度低" in head else ("unknown" if "清晰度未知" in head else "clear")
    name = _FILE_HEAD_SPLIT_RE.split(head, maxsplit=1)[0].strip()
    return name, clarity


def _normalize_filename(s: str) -> str:
    """文件名规范化：basename + NFKC + lower + 去路径分隔（codex#4，供 source 点名匹配）。"""
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("\\", "/")
    return s.rsplit("/", 1)[-1].strip()


def parse_corpus(evidence_source: str) -> list[dict[str, Any]]:
    """把底稿切成 segments ``[{tier, file, page, text, clarity}]``（page 可为 None）。

    两态统一处理：有 ``=== …底稿 ===`` 外层标记（doc-layer）按它定 tier；无标记（inline OCR）
    按每个 ``### 文件:`` 文件名推断 tier。再在每文件块内按 ``【第 N 页】`` 切页。
    每段带所属文件 clarity（R3：low/unknown/clear，供 confidence 消费）。
    """
    segments: list[dict[str, Any]] = []
    cur_tier: str | None = None  # None = 隐式（由文件名推断）
    cur_file: str | None = None
    cur_clarity: str = "clear"
    cur_page: int | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        if cur_file is not None and buf:
            text = "\n".join(buf).strip()
            if text:
                tier = cur_tier if cur_tier is not None else _tier_of(cur_file)
                segments.append(
                    {
                        "tier": tier,
                        "file": cur_file,
                        "page": cur_page,
                        "text": text,
                        "clarity": cur_clarity,
                    }
                )
        buf = []

    for line in evidence_source.splitlines():
        m_tier = _TIER_RE.match(line)
        if m_tier:
            flush()
            cur_tier = _tier_of(m_tier.group(1))
            cur_file = None
            cur_clarity = "clear"
            cur_page = None
            continue
        m_file = _FILE_RE.match(line)
        if m_file:
            flush()
            cur_file, cur_clarity = _parse_file_head(m_file.group(1))
            cur_page = None
            continue
        m_page = _PAGE_RE.match(line)
        if m_page:
            flush()
            cur_page = int(m_page.group(1))
            continue
        buf.append(line)
    flush()
    return segments


class CorpusIndex:
    """本案底稿的 file-level 索引 + 各 tier 规范化全文（供存在性主信号 + page 细化）。"""

    def __init__(self, segments: list[dict[str, Any]]):
        # tier -> file -> page(int, None→0) -> 规范化页文本
        self.tier_files: dict[str, dict[str, dict[int, str]]] = {}
        # R3：规范化文件名 → clarity（low/unknown/clear），供 confidence 消费
        self.clarity_map: dict[str, str] = {}
        parts: dict[str, list[str]] = {}
        for seg in segments:
            tier, file, page = seg["tier"], seg["file"], seg["page"]
            clarity = seg.get("clarity", "clear")
            if file:
                norm_name = _normalize_filename(file)
                # 同文件多段 clarity 一致；非 clear 优先记（low/unknown 是风险信号）
                if norm_name not in self.clarity_map or clarity != "clear":
                    self.clarity_map[norm_name] = clarity
            norm = normalize_text(seg["text"])
            if not norm:
                continue
            key = page if page is not None else 0
            files = self.tier_files.setdefault(tier, {}).setdefault(file, {})
            files[key] = (files.get(key, "") + norm) if key in files else norm
            parts.setdefault(tier, []).append(norm)
        self.tier_corpus: dict[str, str] = {t: "".join(p) for t, p in parts.items()}
        self.whole_corpus: str = "".join(self.tier_corpus.values())

    def low_clarity_files(self) -> list[dict[str, str]]:
        """非 clear 文件列表 [{file, clarity}]（low + unknown，供结论可见性 emit）。"""
        return [
            {"file": name, "clarity": c}
            for name, c in self.clarity_map.items()
            if c in {"low", "unknown"}
        ]

    def source_names_low_clarity_file(self, source: str | None) -> str | None:
        """source 文本是否点名了某 **low**（confirmed 低置信，不含 unknown）文件 → 返回该文件名。

        匹配：低置信文件完整名或 stem(≥4 字符) 出现在规范化 source 里（不反向短子串）。
        unknown（云 OCR 常态）不参与降级，仅可见性。
        """
        if not source:
            return None
        # source 常是"投标文件2.07资料.pdf第6页"——直接对原串 NFKC+lower 匹配（不取 basename）
        nsrc_full = unicodedata.normalize("NFKC", source).lower()
        for name, clarity in self.clarity_map.items():
            if clarity != "low":
                continue
            stem = name.rsplit(".", 1)[0]
            if (name and name in nsrc_full) or (len(stem) >= 4 and stem in nsrc_full):
                return name
        return None

    def corpus_for(self, tier: str) -> str:
        """该 tier 规范化全文；tier 不可定（whole）或缺该 tier → 用全量。"""
        if tier in self.tier_corpus:
            return self.tier_corpus[tier]
        return self.whole_corpus


# ── 匹配 ────────────────────────────────────────────────────────────────────────


def _cap_corpus(corpus: str, limit: int) -> str:
    """超限按首尾各半截（绝不只取前 N，避免尾部证据被丢致真引文误判 unresolved）。"""
    if len(corpus) <= limit:
        return corpus
    half = limit // 2
    return corpus[:half] + corpus[-half:]


def existence_ratio(norm_quote: str, corpus: str) -> float:
    """存在性匹配度：逐字子串命中→1.0；否则 k-gram 覆盖率（连续片段在底稿出现的比例）作软度量。

    逐字命中是抗编造的强信号；k-gram 覆盖率近似"原文有多少在底稿里"，区分转述(中)与编造(近0)。
    全程 C 级 ``str.find``（``in``），有界、亚秒级。
    """
    if not norm_quote or not corpus:
        return 0.0
    if norm_quote in corpus:
        return 1.0
    k = _kgram()
    if len(norm_quote) <= k:
        return 0.0  # 太短且非逐字命中 → 视为不在
    capped = _cap_corpus(corpus, _max_corpus_chars())
    grams = [norm_quote[i : i + k] for i in range(len(norm_quote) - k + 1)]
    if not grams:
        return 0.0
    found = sum(1 for g in grams if g in capped)
    return found / len(grams)


def page_status(index: CorpusIndex, tier: str, page: int | None, norm_quote: str) -> str:
    """file/page 精度细化（仅当存在性已 resolved 才有意义）：

    - ``no_page``：source 未给页码。
    - ``confirmed``：cited page ±window 切片里逐字命中（且仅一个文件命中）。
    - ``file_ambiguous``：该页号在该 tier 多文件都命中（source 未给确切文件 → 不强判）。
    - ``page_mismatch``：cited page 附近无此原文（但 tier 内别处有 → 仍 resolved，仅页不符）。
    """
    if page is None:
        return "no_page"
    window = _page_window()
    files = index.tier_files.get(tier)
    if files is None:
        # tier 不可定 / whole 无独立 key（doclayer 只有 tender/bid）→ 跨全部 tier 找
        # （与 corpus_for('whole') 用全量语料对称，reviewer F3：避免 whole 恒判 page_mismatch）
        files = {f: pg for t in index.tier_files.values() for f, pg in t.items()}
    hits: list[str] = []
    for fname, pages in (files or {}).items():
        for p, ptext in pages.items():
            if abs(p - page) <= window and norm_quote in ptext:
                hits.append(fname)
                break
    if len(hits) == 1:
        return "confirmed"
    if len(hits) > 1:
        return "file_ambiguous"
    return "page_mismatch"


# ── 出处解析 ──────────────────────────────────────────────────────────────────

_PAGE_IN_SOURCE_RE = re.compile(r"第\s*(\d+)\s*页")


def parse_source(source: str | None) -> tuple[str, int | None]:
    """从出处文本解析 ``(tier, page)``：含「招标」→tender / 「投标」→bid / 否则 whole；页码取「第N页」。"""
    if not source:
        return "whole", None
    tier = _tier_of(source)
    m = _PAGE_IN_SOURCE_RE.search(source)
    page = int(m.group(1)) if m else None
    return tier, page


# ── 主回查逻辑 ────────────────────────────────────────────────────────────────


def _classify(ratio: float) -> str:
    """双阈值三档：≥resolve→resolved；≤absent→unresolved；中间→weak_match（不降级）。"""
    if ratio >= _resolve_threshold():
        return "resolved"
    if ratio <= _absent_threshold():
        return "unresolved"
    return "weak_match"


def _check_one(
    *,
    container: dict[str, Any],
    source: str | None,
    quote: str | None,
    where: str,
    index: CorpusIndex,
    summary: dict[str, Any],
    high_severity: bool = False,
) -> str | None:
    """回查一条出处：原地给 ``container`` 写 ``resolution``，更新 summary，返回判定档（或 None=跳过）。"""
    norm_quote = normalize_text(quote or "")
    if len(norm_quote) < _min_quote_chars():
        return None  # 无逐字 quote / 太短 → 不可靠，不判（honesty：不谎称已核实）
    tier, page = parse_source(source)
    ratio = existence_ratio(norm_quote, index.corpus_for(tier))
    status = _classify(ratio)
    summary["checked"] += 1
    summary[status] = summary.get(status, 0) + 1

    annotation: dict[str, Any] = {"status": status}
    if status == "resolved":
        pstat = page_status(index, tier, page, norm_quote)
        annotation["page"] = pstat
        if pstat == "page_mismatch":
            summary["page_mismatch"] = summary.get("page_mismatch", 0) + 1
    if status != "resolved" or _annotate_resolved():
        container["resolution"] = annotation

    if status == "unresolved":
        ref = {
            "where": where,
            "source": source or "",
            "quote_preview": (quote or "")[:60],
            "severity": "high" if high_severity else "normal",
        }
        if high_severity:
            summary["high_severity_unresolved"].append(ref)
        else:
            summary["unresolved_refs"].append(ref)
    return status


def _hit_moves_score(hit: dict[str, Any], hits_key: str) -> bool:
    """该命中是否实际影响得分（award_hits 的 ``awarded`` / deduction_hits 的 ``deducted`` ≠ 0）。

    子项级降级（治"含一个 0 分未核实子项就把整项 manual"）：得 0 分的命中（如「无偏离」常规参数
    子项 awarded=0）没有可核验的"得分主张"，其出处即便 unresolved 也**不应**把同项里有检测报告
    支撑的有分子项（如性能参数 21 分 resolved）连带降人工。仅当一条**带非零分**的命中出处核不实，
    才说明"拿了不可核验的分"→ 触发降级。分值字段缺失 / 非数 → 保守视为移动得分（仍触发，不放松）。
    """
    points = hit.get("awarded") if hits_key == "award_hits" else hit.get("deducted")
    if points is None:
        return True  # 缺分值字段 → 保守仍触发（不削弱闸）
    if isinstance(points, bool) or not isinstance(points, (int, float)):
        return True
    return points != 0


def _check_hits(
    sitem: dict[str, Any],
    hits_key: str,
    where_prefix: str,
    index: CorpusIndex,
    summary: dict[str, Any],
) -> bool:
    """回查一个评分项的 ``deduction_hits``/``award_hits``；任一**带非零分**命中 unresolved → True（触发降级）。

    子项级：得 0 分的命中（无得分主张）出处 unresolved 不触发降级——避免有检测报告支撑的有分子项
    被同项里的 0 分未核实子项连带 manual（F02：技术参数「无偏离」常规子项拖累性能参数 21 分）。
    """
    has_unresolved = False
    hits = sitem.get(hits_key)
    if not isinstance(hits, list):
        return False
    for hi, hit in enumerate(hits):
        if not isinstance(hit, dict):
            continue
        ev = hit.get("evidence")
        if not isinstance(ev, dict):
            continue
        status = _check_one(
            container=ev,
            source=ev.get("source"),
            quote=ev.get("quote"),
            where=f"{where_prefix}.{hits_key}[{hi}]",
            index=index,
            summary=summary,
        )
        if status == "unresolved" and _hit_moves_score(hit, hits_key):
            has_unresolved = True
    return has_unresolved


_DOWNGRADE_NOTE = " ⚠ 出处未在底稿核实（evidence_unresolved），已降人工复核"
_LOW_CLARITY_NOTE = " ⚠ 出处文件 OCR 低置信，『读不清≠没提供』，已降人工复核（R3）"


def _downgrade_scoring_item(
    sitem: dict[str, Any],
    *,
    note: str,
    resolution_status: str,
    summary: dict[str, Any],
) -> bool:
    """scored → manual_review（仅迁移一次，幂等）。返回 True 当且仅当本次发生真实状态迁移。

    R1（unresolved）与 R3（low_clarity）共用，保证同项双触发不重复降级 / 不重复 basis（codex#3）。
    """
    cur_basis = str(sitem.get("basis") or "")
    if sitem.get("status") == "scored":
        sitem["status"] = "manual_review"
        sitem["score"] = None
        sitem["basis"] = cur_basis + note
        sitem["resolution"] = {"status": resolution_status}
        summary["downgraded_items"].append(sitem.get("item"))
        return True
    # 已非 scored（如 R1 先降）：仅补本 note（不重复），不算新迁移
    if note.strip() not in cur_basis:
        sitem["basis"] = cur_basis + note
    return False


def _flag_low_clarity_sources(sitem: dict[str, Any], index: CorpusIndex) -> str | None:
    """扫 scoring 项的 evidence 命中 source + basis，是否点名某 low 文件；命中则给该 evidence 标
    独立字段 ``clarity_flag``（不碰 R1 的 resolution，codex#2），返回被点名的文件名或 None。"""
    named: str | None = None
    for hits_key in ("deduction_hits", "award_hits"):
        hits = sitem.get(hits_key)
        if not isinstance(hits, list):
            continue
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            ev = hit.get("evidence")
            if isinstance(ev, dict):
                f = index.source_names_low_clarity_file(ev.get("source"))
                if f:
                    ev["clarity_flag"] = "low"
                    named = named or f
    # absence 项常把文件写进 basis（无 evidence hit）→ 也扫 basis（仍需点名 low 文件，保守）
    f = index.source_names_low_clarity_file(sitem.get("basis"))
    return named or f


def resolve_audit_evidence(structured_output: Any, evidence_source: str) -> Any:
    """``resolve`` hook 入口：回查 audit-result 结论里所有出处 vs 本案底稿，标注 + 降级 + verdict 一致性回填。

    Args:
        structured_output: 已过 normalize/validate/enrich 的结论（dict）。
        evidence_source: 本案底稿（带 ``### 文件:`` + ``【第 N 页】`` 锚点，tender_worker 透传的 ocr_block）。

    Returns:
        原对象（原地标注）；任何异常或开关关闭 → 原样返回（绝不崩评标）。
    """
    try:
        if not isinstance(structured_output, dict) or not evidence_source or not _enabled():
            return structured_output
        segments = parse_corpus(evidence_source)
        if not segments:
            return structured_output
        index = CorpusIndex(segments)

        summary: dict[str, Any] = {
            "checked": 0,
            "resolved": 0,
            "weak_match": 0,
            "unresolved": 0,
            "page_mismatch": 0,
            "loc_only": 0,
            "downgraded_items": [],
            "high_severity_unresolved": [],
            "unresolved_refs": [],
            "low_clarity_files": index.low_clarity_files(),  # R3 可见性 emit
        }
        downgrade = _downgrade_enabled()
        any_new_manual = False

        # 1. evidence_chain（quote 固定 = finding，normalize 已剥到 {source,finding,conclusion}）
        chain = structured_output.get("evidence_chain")
        if isinstance(chain, list):
            for i, item in enumerate(chain):
                if isinstance(item, dict):
                    _check_one(
                        container=item,
                        source=item.get("source"),
                        quote=item.get("finding"),
                        where=f"evidence_chain[{i}]",
                        index=index,
                        summary=summary,
                    )

        extracted = structured_output.get("extracted_data")
        if isinstance(extracted, dict):
            # 2. scoring：deduction_hits/award_hits 逐字回查 → unresolved 降级该项
            scoring = extracted.get("scoring")
            if isinstance(scoring, list):
                for si, sitem in enumerate(scoring):
                    if not isinstance(sitem, dict):
                        continue
                    where = f"scoring[{si}]"
                    unresolved = _check_hits(sitem, "deduction_hits", where, index, summary)
                    unresolved |= _check_hits(sitem, "award_hits", where, index, summary)
                    has_structured_quote = bool(
                        sitem.get("deduction_hits") or sitem.get("award_hits")
                    )
                    # R3：是否点名 low 文件（同时给 evidence 打 clarity_flag）
                    low_clarity_named = _flag_low_clarity_sources(sitem, index)
                    # R3 G3 兜底触发：scored 且 score==0（"读不清却判 0"嫌疑）且点名 low 文件
                    g3_hit = (
                        low_clarity_named is not None
                        and sitem.get("status") == "scored"
                        and sitem.get("score") == 0
                    )
                    if downgrade and unresolved:
                        any_new_manual |= _downgrade_scoring_item(
                            sitem,
                            note=_DOWNGRADE_NOTE,
                            resolution_status="downgraded_unresolved",
                            summary=summary,
                        )
                    elif downgrade and g3_hit:
                        any_new_manual |= _downgrade_scoring_item(
                            sitem,
                            note=_LOW_CLARITY_NOTE,
                            resolution_status="downgraded_low_clarity",
                            summary=summary,
                        )
                    elif not has_structured_quote and sitem.get("status") in {
                        "scored",
                        "manual_review",
                        "rejected",
                    }:
                        # banded/formula/pass_fail 项无离散逐字 quote → 只标 loc_only（不谎称已核实，
                        # 不降级；codex P1：不宣称已覆盖全部承重依据）。
                        sitem.setdefault("resolution", {"status": "loc_only"})
                        summary["loc_only"] += 1
                    # R1+R3 同项双触发：R1(unresolved) 已降级走上面 if 分支、R3 elif 被跳过 → 此处补
                    # R3 低置信 note，保证降级原因完整不丢（reviewer F4）。
                    if (
                        downgrade
                        and unresolved
                        and g3_hit
                        and _LOW_CLARITY_NOTE.strip() not in str(sitem.get("basis") or "")
                    ):
                        sitem["basis"] = str(sitem.get("basis") or "") + _LOW_CLARITY_NOTE

            # 3. 废标/资格依据（高危，仅标注不动 verdict——废标 verdict 是高代价决定）
            for key in ("disqualification_hits", "eligibility_checks"):
                hits = extracted.get(key)
                if not isinstance(hits, list):
                    continue
                for di, hit in enumerate(hits):
                    if not isinstance(hit, dict):
                        continue
                    ev = hit.get("evidence")
                    if isinstance(ev, dict):
                        _check_one(
                            container=ev,
                            source=ev.get("source"),
                            quote=ev.get("quote"),
                            where=f"{key}[{di}]",
                            index=index,
                            summary=summary,
                            high_severity=True,
                        )

        # 4. verdict/result 一致性回填（codex P1）：降级新引入 manual_review 项 → 顶层须一致
        if any_new_manual and downgrade:
            verdict = structured_output.get("verdict")
            if verdict == "approved":
                structured_output["verdict"] = "manual_review"
                structured_output["manual_review_reason"] = "insufficient_evidence"
                # 惰性 import 避循环（output_contracts 末尾 import 本模块注册 hook）
                from server.common.output_contracts import enrich_audit_decision

                enrich_audit_decision(structured_output)  # 幂等重派生 result/conclusion
            elif verdict == "manual_review":
                structured_output.setdefault("manual_review_reason", "insufficient_evidence")
            # verdict == "rejected"：终局更强，不因单项未核实翻盘

        # 5. 摘要（有回查 或 有低置信文件即写——codex#1：勿因无 quote 吞掉 low_clarity_files）
        if isinstance(extracted, dict) and (summary["checked"] > 0 or summary["low_clarity_files"]):
            extracted["evidence_resolution"] = summary
        return structured_output
    except Exception:  # noqa: BLE001 - 失败安全：绝不因回查崩评标
        logger.warning("evidence_resolution failed; returning output unchanged", exc_info=True)
        return structured_output
