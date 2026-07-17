"""Generic 底稿语料解析 + 匹配打分原语（F5 evidence 拆分，从 server/common/evidence_resolution.py
搬出的通用半）。

这些原语（切段 / file-level 索引 / 存在性匹配度 / page 精度细化 / 出处解析 / 双阈值分类）本身
不带任何 scoring/tender 语义——OCR / 未来的结构化检索（D7）都要复用。tender 专属的 resolve hook
（评分证据回查闸，含降级/verdict 一致性）落在 ``server/tender/evidence.py``，import 本模块的原语。

纯函数 + 无副作用，无 SDK / 网络依赖。
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any

# ── 配置（运行时动态读 env，便于灰度调参）──────────────────────────────────────


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
# 仅被本模块的 _classify（存在性三档分类）使用——不能想当然按"配置区都是 tender 的"分给
# server/tender/evidence.py，否则 _classify 会反向依赖 tender 模块。
def _resolve_threshold() -> float:
    return _f("EVIDENCE_RESOLVE_THRESHOLD", 0.65)


def _absent_threshold() -> float:
    return _f("EVIDENCE_ABSENT_THRESHOLD", 0.30)


def _page_window() -> int:
    # 仅被 page_status（本模块）使用——同上，跟随其调用方留 common。
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
# ``[⚠清晰度`` / ``[清晰度`` 处切，**不切文件名里的普通 ``[``**（如 file[1].pdf）。
_FILE_HEAD_SPLIT_RE = re.compile(r"\s*\(kind=|\s*\[(?:检出印章|⚠?清晰度)")


def _parse_file_head(head: str) -> tuple[str, str]:
    """从 ``### 文件:`` 头串解析 (纯文件名, clarity)。

    clarity: ``[⚠清晰度低`` → low；``[清晰度未知`` → unknown；否则 clear（供置信度消费）。
    """
    clarity = "low" if "清晰度低" in head else ("unknown" if "清晰度未知" in head else "clear")
    name = _FILE_HEAD_SPLIT_RE.split(head, maxsplit=1)[0].strip()
    return name, clarity


def _normalize_filename(s: str) -> str:
    """文件名规范化：basename + NFKC + lower + 去路径分隔，供 source 点名匹配。"""
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("\\", "/")
    return s.rsplit("/", 1)[-1].strip()


def parse_corpus(evidence_source: str) -> list[dict[str, Any]]:
    """把底稿切成 segments ``[{tier, file, page, text, clarity}]``（page 可为 None）。

    两态统一处理：有 ``=== …底稿 ===`` 外层标记（doc-layer）按它定 tier；无标记（inline OCR）
    按每个 ``### 文件:`` 文件名推断 tier。再在每文件块内按 ``【第 N 页】`` 切页。
    每段带所属文件 clarity（low/unknown/clear，供 confidence 消费）。
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
        # 规范化文件名 → clarity（low/unknown/clear），供 confidence 消费
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
        # （与 corpus_for('whole') 用全量语料对称，避免 whole 恒判 page_mismatch）
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


# ── 分类 ────────────────────────────────────────────────────────────────────────


def _classify(ratio: float) -> str:
    """双阈值三档：≥resolve→resolved；≤absent→unresolved；中间→weak_match（不降级）。"""
    if ratio >= _resolve_threshold():
        return "resolved"
    if ratio <= _absent_threshold():
        return "unresolved"
    return "weak_match"
