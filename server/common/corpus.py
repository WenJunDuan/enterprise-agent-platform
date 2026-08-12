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

# ── 页锚点字符串协议（本模块是**唯一**解析单点，H2 page-provenance KD0）─────────────
#
# 锚点是跨模块字符串协议（OCR 渲染端产、tender/boq/docstructure/context_slim 解析端消费）。
# 收拢前 pipeline._PAGE_ANCHOR_PATTERN / boq._PAGE_RE / context_slim._PAGE_ANCHOR_RE 各写一份，
# 加 ``【转换稿第 M 页】`` 变体时漏掉任何一处都会静默失准（漏 pipeline 那处 → 仅含转换稿锚的
# 空底稿被判有效假 ready）。故只在此定义，其余模块 import。
#
# 两种 artifact 坐标系：
# - ``original``：``【第 N 页】``，N 是用户可直接回查的原文档页号。
# - ``converted``：``【转换稿第 M 页】``，M 是 Office→PDF 转换稿的页号（LibreOffice 分页 ≠ Word
#   分页），原文档页号不可靠 → 一律不冒充。
# 区间锚 ``【第 3-5 页】``（RAG chunk 跨页时用）同属本协议，解析取**起始页**。
PAGE_ANCHOR_LINE_RE = re.compile(
    r"^\s*【(?:(?P<converted>转换稿)?第\s*(?P<page>\d+)(?:\s*-\s*(?P<page_end>\d+))?\s*页)】\s*$"
)
ARTIFACT_ORIGINAL = "original"
ARTIFACT_CONVERTED = "converted"


def page_anchor_text(
    page_no: int, *, artifact: str = ARTIFACT_ORIGINAL, page_end: int | None = None
) -> str:
    """页锚点字面量（不含换行）：渲染端唯一产出点，与 ``parse_page_anchor`` 互为逆。

    Args:
        page_no: 起始页号（在 ``artifact`` 坐标系里）。
        artifact: ``original``（原文档页）或 ``converted``（Office→PDF 转换稿页）。
        page_end: 跨页 chunk 的结束页；与 ``page_no`` 相同或 None → 渲染单页锚。
    """
    prefix = "转换稿" if artifact == ARTIFACT_CONVERTED else ""
    span = f"{page_no}-{page_end}" if page_end is not None and page_end != page_no else f"{page_no}"
    return f"【{prefix}第 {span} 页】"


def page_anchor(page_no: int) -> str:
    """原件页锚点行（含换行）：让模型 evidence/basis 能引到底稿真实页。"""
    return page_anchor_text(page_no) + "\n"


def converted_page_anchor(page_no: int) -> str:
    """转换稿页锚点行（含换行）：页号属于 Office→PDF 转换稿，非原文档页。"""
    return page_anchor_text(page_no, artifact=ARTIFACT_CONVERTED) + "\n"


def parse_page_anchor(line: str) -> tuple[int, str] | None:
    """解析一行是否为页锚点 → ``(页号, artifact)``；不是锚点行返回 ``None``。

    Args:
        line: 底稿中的单行文本（允许首尾空白）。

    Returns:
        ``(page_no, "original"|"converted")``，页号取该 artifact 坐标系里的值。
    """
    match = PAGE_ANCHOR_LINE_RE.match(line or "")
    if match is None:
        return None
    artifact = ARTIFACT_CONVERTED if match.group("converted") else ARTIFACT_ORIGINAL
    return int(match.group("page")), artifact


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
_FILE_HEAD_SPLIT_RE = re.compile(r"\s*\(kind=|\s*\[(?:检出印章|⚠?清晰度|⚠?页号存疑)")

# 页号不可靠标记（云 OCR 页数守卫命中，draft_render.page_confidence_note 产）
_PAGE_UNRELIABLE_MARK = "页号存疑"


def _parse_file_head(head: str) -> tuple[str, str, bool]:
    """从 ``### 文件:`` 头串解析 (纯文件名, clarity, 页号是否不可靠)。

    clarity: ``[⚠清晰度低`` → low；``[清晰度未知`` → unknown；否则 clear（供置信度消费）。
    页号不可靠（``[⚠页号存疑``，云 OCR 页数守卫命中）→ 回查闸把该文件证据全部降 page_unverified。
    """
    clarity = "low" if "清晰度低" in head else ("unknown" if "清晰度未知" in head else "clear")
    name = _FILE_HEAD_SPLIT_RE.split(head, maxsplit=1)[0].strip()
    return name, clarity, _PAGE_UNRELIABLE_MARK in head


def _normalize_filename(s: str) -> str:
    """文件名规范化：basename + NFKC + lower + 去路径分隔，供 source 点名匹配。"""
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("\\", "/")
    return s.rsplit("/", 1)[-1].strip()


def _anchor_line_offsets(text: str) -> list[tuple[int, str]]:
    """文本里所有页锚行的 ``(行首偏移, 锚行原文)``（按偏移升序）。"""
    offsets: list[tuple[int, str]] = []
    pos = 0
    for line in text.split("\n"):
        if parse_page_anchor(line) is not None:
            offsets.append((pos, line.strip()))
        pos += len(line) + 1
    return offsets


def text_has_page_anchor(text: str) -> bool:
    """文本里是否存在页锚行（无锚文件的截断只能按字符切，须在 marker 里如实注明）。"""
    return bool(_anchor_line_offsets(text))


def _snap_back(text: str, limit: int, anchors: list[tuple[int, str]]) -> int:
    """head 切点向前回退：优先到最近的页锚行首，退而求其次到行边界（锚行永不切半）。"""
    candidates = [pos for pos, _ in anchors if pos <= limit]
    if candidates:
        return max(candidates)
    newline = text.rfind("\n", 0, limit)
    return newline + 1 if newline >= 0 else limit


def _snap_forward(text: str, start: int, anchors: list[tuple[int, str]]) -> int:
    """tail 起点向后推进：优先到最近的页锚行首，退而求其次到行边界。"""
    candidates = [pos for pos, _ in anchors if pos >= start]
    if candidates:
        return min(candidates)
    newline = text.find("\n", start)
    return newline + 1 if newline >= 0 else start


def split_head_tail_on_anchors(
    text: str, head_n: int, tail_n: int
) -> tuple[str, str, str | None]:
    """按页锚行边界切出首尾两段，并算出尾段应重放的页锚（H2 KD3）。

    旧的按字符硬切有两个错挂源：① 锚行被切半；② tail 首段内容在模型视角归属 head 末锚
    （早得多的页）。本函数把切点吸附到锚行边界，并在尾段前重放其所属页锚。

    Args:
        text: 待切分文本（底稿块或 context 块）。
        head_n: 首段字符预算。
        tail_n: 尾段字符预算（含重放锚所占字符）。

    Returns:
        ``(head, tail, replay)``：``replay`` 是尾段应重放的锚行原文；尾段自带锚或全文无锚时为
        ``None``。保证 ``len(head) + len(tail) + len(replay)+1 <= head_n + tail_n``。
    """
    anchors = _anchor_line_offsets(text)
    head_cut = _snap_back(text, head_n, anchors) if head_n > 0 else 0
    replay: str | None = None
    tail_start = len(text)
    # 两轮：先按满额预算定位尾段以求出重放锚，再扣掉重放锚占位重新定位（锚只会后移不会前移，
    # 故一轮修正即收敛）；仍超预算则放弃重放（宁可少一个锚，也不越预算/不切半锚）。
    for reserve in (0, None):
        budget = tail_n if reserve == 0 else tail_n - (len(replay) + 1 if replay else 0)
        if budget <= 0:
            return text[:head_cut], "", None
        tail_start = max(head_cut, _snap_forward(text, max(0, len(text) - budget), anchors))
        anchored_start = any(pos == tail_start for pos, _ in anchors)
        before = [line for pos, line in anchors if pos < tail_start]
        replay = None if anchored_start or not before else before[-1]
    if len(text) - tail_start + (len(replay) + 1 if replay else 0) > tail_n:
        replay = None
    return text[:head_cut], text[tail_start:], replay


def _source_mentions_file(normalized_source: str, name: str) -> bool:
    """规范化 source 里是否点名了文件 ``name``：完整名或 stem(≥4 字符) 命中（不反向短子串）。"""
    stem = name.rsplit(".", 1)[0]
    return bool(name and name in normalized_source) or (
        len(stem) >= 4 and stem in normalized_source
    )


def parse_corpus(evidence_source: str) -> list[dict[str, Any]]:
    """把底稿切成 segments ``[{tier, file, page, artifact, artifact_page, text, clarity}]``。

    两态统一处理：有 ``=== …底稿 ===`` 外层标记（doc-layer）按它定 tier；无标记（inline OCR）
    按每个 ``### 文件:`` 文件名推断 tier。再在每文件块内按页锚点切页。
    每段带所属文件 clarity（low/unknown/clear，供 confidence 消费）。

    页溯源（H2 KD1）：``artifact_page`` 是页号在其 artifact 坐标系里的值；``page`` 是**用户可回查
    的原文档页号**——``original`` 锚两者相同，``converted``（Office→PDF 转换稿）锚 ``page=None``
    （原 docx/xls 无可靠页映射，如实置空不猜）。无锚段两者皆 None。
    """
    segments: list[dict[str, Any]] = []
    cur_tier: str | None = None  # None = 隐式（由文件名推断）
    cur_file: str | None = None
    cur_clarity: str = "clear"
    cur_page: int | None = None
    cur_artifact: str = ARTIFACT_ORIGINAL
    cur_page_unreliable: bool = False
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
                        "page": cur_page if cur_artifact == ARTIFACT_ORIGINAL else None,
                        "artifact": cur_artifact,
                        "artifact_page": cur_page,
                        "text": text,
                        "clarity": cur_clarity,
                        "page_unreliable": cur_page_unreliable,
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
            cur_artifact = ARTIFACT_ORIGINAL
            cur_page_unreliable = False
            continue
        m_file = _FILE_RE.match(line)
        if m_file:
            flush()
            cur_file, cur_clarity, cur_page_unreliable = _parse_file_head(m_file.group(1))
            cur_page = None
            cur_artifact = ARTIFACT_ORIGINAL
            continue
        anchor = parse_page_anchor(line)
        if anchor is not None:
            flush()
            cur_page, cur_artifact = anchor
            continue
        buf.append(line)
    flush()
    return segments


class CorpusIndex:
    """本案底稿的 file-level 索引 + 各 tier 规范化全文（供存在性主信号 + page 细化）。"""

    def __init__(self, segments: list[dict[str, Any]]):
        # tier -> file -> artifact_page(int, 无锚→0) -> 规范化页文本
        self.tier_files: dict[str, dict[str, dict[int, str]]] = {}
        # 规范化文件名 → clarity（low/unknown/clear），供 confidence 消费
        self.clarity_map: dict[str, str] = {}
        # 文件名（原样，与 tier_files 的 key 一致）→ artifact（original/converted），供页坐标系比对
        self.artifact_map: dict[str, str] = {}
        # 页号不可靠的文件（云 OCR 页数守卫命中）：其证据页号一律不认，见 page_unreliable_files
        self._page_unreliable: set[str] = set()
        parts: dict[str, list[str]] = {}
        for seg in segments:
            tier, file = seg["tier"], seg["file"]
            page = seg["artifact_page"]
            clarity = seg.get("clarity", "clear")
            if file:
                norm_name = _normalize_filename(file)
                # 同文件多段 clarity 一致；非 clear 优先记（low/unknown 是风险信号）
                if norm_name not in self.clarity_map or clarity != "clear":
                    self.clarity_map[norm_name] = clarity
                if seg.get("page_unreliable"):
                    self._page_unreliable.add(norm_name)
                if seg["artifact"] != ARTIFACT_ORIGINAL:
                    self.artifact_map[file] = seg["artifact"]
                else:
                    self.artifact_map.setdefault(file, ARTIFACT_ORIGINAL)
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

    def page_unreliable_files(self) -> list[str]:
        """页号不可靠的文件名列表（云 OCR 页数守卫命中，H2 KD1/KD5）。"""
        return sorted(self._page_unreliable)

    def source_names_page_unreliable_file(self, source: str | None) -> bool:
        """source 是否点名了某个页号不可靠的文件（匹配规则同低置信点名）。"""
        if not source:
            return False
        nsrc_full = unicodedata.normalize("NFKC", source).lower()
        return any(_source_mentions_file(nsrc_full, name) for name in self._page_unreliable)

    def source_names_file(self, source: str | None, file_name: str) -> bool:
        """出处是否点名了 ``file_name``（页号纠正必须限定在被点名的文件内，review pass1 F2）。"""
        if not source:
            return False
        nsrc_full = unicodedata.normalize("NFKC", source).lower()
        return _source_mentions_file(nsrc_full, _normalize_filename(file_name))

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
            if clarity == "low" and _source_mentions_file(nsrc_full, name):
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


def _files_for_tier(index: CorpusIndex, tier: str) -> dict[str, dict[int, str]]:
    """该 tier 的 file→pages 映射；tier 不可定（whole）时跨全部 tier 找。

    与 ``corpus_for('whole')`` 用全量语料对称，避免 whole 恒判 page_mismatch。
    """
    files = index.tier_files.get(tier)
    if files is not None:
        return files
    return {f: pg for t in index.tier_files.values() for f, pg in t.items()}


def page_status(index: CorpusIndex, tier: str, page: int | None, norm_quote: str) -> str:
    """file/page 精度细化（仅当存在性已 resolved 才有意义）：

    - ``no_page``：source 未给页码。
    - ``confirmed``：cited page ±window 切片里逐字命中（且仅一个文件命中）。
    - ``file_ambiguous``：该页号在该 tier 多文件都命中（source 未给确切文件 → 不强判）。
    - ``file_level``：命中的是**无页锚**文件（native word/excel 整份直读）→ 页号无从核实，
      按文件级判定即可；**绝不因 source 写了个页号就盖章 confirmed**（H2 KD5）。
    - ``page_mismatch``：cited page 附近无此原文（但 tier 内别处有 → 仍 resolved，仅页不符）。

    key=0 是"无页锚段"的哨兵，不是第 0 页——旧实现让它落进 ``abs(0 - 1) <= window`` 的窗口，
    于是无页锚文件的臆造"第 1 页"恒判 confirmed（AC5 要消灭的正是这条）。
    """
    if page is None:
        return "no_page"
    window = _page_window()
    files = _files_for_tier(index, tier)
    hits: list[str] = []
    file_level_hit = False
    for fname, pages in (files or {}).items():
        for p, ptext in pages.items():
            if p == 0:
                file_level_hit = file_level_hit or norm_quote in ptext
                continue
            if abs(p - page) <= window and norm_quote in ptext:
                hits.append(fname)
                break
    if len(hits) == 1:
        return "confirmed"
    if len(hits) > 1:
        return "file_ambiguous"
    return "file_level" if file_level_hit else "page_mismatch"


def locate_quote_pages(index: CorpusIndex, tier: str, norm_quote: str) -> list[tuple[str, int]]:
    """逐字 quote 在**带页锚**的页里出现在哪些 ``(文件, 页号)``（供页号就地纠正，H2 KD5）。"""
    return sorted(
        (fname, page)
        for fname, pages in (_files_for_tier(index, tier) or {}).items()
        for page, ptext in pages.items()
        if page != 0 and norm_quote in ptext
    )


def rewrite_source_page(source: str, page: int) -> str:
    """把出处里的页号改写成 ``page``（保留「转换稿」等 artifact 前缀与原有格式）。"""
    return _PAGE_IN_SOURCE_RE.sub(f"第 {page} 页", source, count=1)


# ── 出处解析 ──────────────────────────────────────────────────────────────────

_PAGE_IN_SOURCE_RE = re.compile(r"第\s*(\d+)\s*页")
_CONVERTED_IN_SOURCE_RE = re.compile(r"转换稿\s*第\s*\d+\s*页")


def source_page_kind(source: str | None) -> str:
    """出处引的是哪套页坐标：写「转换稿第M页」→ ``converted``，否则 ``original``。

    与 ``parse_source`` 分开而不改其返回元数（既有调用方按 2-tuple 解包），H2 KD2。
    """
    if source and _CONVERTED_IN_SOURCE_RE.search(source):
        return ARTIFACT_CONVERTED
    return ARTIFACT_ORIGINAL


def parse_source(source: str | None) -> tuple[str, int | None]:
    """从出处文本解析 ``(tier, page)``：含「招标」→tender / 「投标」→bid / 否则 whole；页码取「第N页」。

    页号是 artifact 坐标系里的值（「转换稿第M页」取 M）；哪套坐标见 ``source_page_kind``。
    """
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
