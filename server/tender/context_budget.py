"""底稿注入预算：默认上限推导 + **内容优先**截断（2026-08-14 P0 事故 Bug A）。

事故现场：``tender_context_truncated original_bytes=103335 kept_bytes=63999 limit_bytes=64000``。
两个独立缺陷：

1. 默认上限硬编码 64,000 B（≈2 万 token），是按"最小窗口模型 64K token"这个**错误前提**反推的；
   实际部署 ``MODEL_CONTEXT_WINDOW=1048576``（1M 窗口），64 KB 只占窗口 2%。
2. 截断是"保留前 N 字节"的盲截。招标文件的评标办法/评分标准**总在后部章节**，盲截把
   「第四章 评审方法和程序」整章砍掉 → 模型反复 Read 原文件找评分标准 → 耗尽 30 轮 →
   ``result_subtype=error_max_turns`` → 整单无结论。

本模块只做纯计算（读 env 的配置解析除外），无 IO / 无模型调用。截断策略：识别关键评审章节
（``KEY_SECTION_KEYWORDS``）的行区段并优先足额分配预算，其余区段按剩余预算均分，被削减处留
可见省略标记。``server.tender.context_slim`` 复用同一份关键词表与选区逻辑（DRY 单点）。
"""

from __future__ import annotations

from server.common.corpus import parse_page_anchor
from server.ocr.docstructure import chapter_heading
from server.platform.config import resolve_model_context_window, resolve_model_max_output_tokens

# 关键评审章节关键词（单点定义，context_slim 首抽瘦身与本模块的预算闸共用）。
# 「评审方法」「评审程序」是 2026-08-14 事故补入的：事故章节标题是「第四章 评审方法和程序」，
# 旧表只有「评审办法」，一个字之差整章漏判 → 被当成普通正文截掉。
KEY_SECTION_KEYWORDS: tuple[str, ...] = (
    "评标办法",
    "评分标准",
    "评分细则",
    "评审办法",
    "评审方法",
    "评审程序",
    "资格审查",
    "资格评审",
    "资格要求",
    "初步评审",
    "符合性审查",
    "响应性审查",
    "废标",
    "否决",
)

# ── 默认预算推导 ────────────────────────────────────────────────────────────────
#
# 中文 OCR 底稿按 UTF-8 3 字节/汉字、1 汉字≈1 token 估（与 context_slim 的 1 字符≈1 token 同源
# 假设，只是这里的预算单位是字节）。
_BYTES_PER_TOKEN = 3
# 单次评标脚手架：实测提示词 55,439 B ≈ 18,500 token，再加 criteria 注入块 + 底稿告警块 +
# 估算误差余量 → 取整 30,000 token
# （见 compound/2026-08-14-learning-prompt-budget-must-be-per-session.md）。
_SCAFFOLD_RESERVE_TOKENS = 30_000
# 评标是**多轮** agent 循环（默认 30 轮）：模型还会 Read 原文件、重识别低清页、扩展思考，
# 这些都在同一窗口里累积。底稿不得独占整窗，按窗口的 1/4 留给循环自身。
_AGENT_LOOP_MARGIN_DIVISOR = 4
# 两 env 都缺失（部署未声明模型窗口/输出预算）时的保守常量。取 256,000 B ≈ 8.5 万 token：
# 足以容纳一份完整招标文件底稿（事故当天 103 KB），又远低于任何主流部署窗口。
FALLBACK_MAX_BYTES = 256_000


def derive_default_max_bytes(model: str | None = None) -> int:
    """Derive the OCR-draft byte budget from the deployed model's window.

    Args:
        model: 本次评标实际使用的模型名；``None`` 走全局默认模型配置。

    Returns:
        底稿注入的字节上限。窗口/输出预算任一未声明、或声明值自相矛盾（扣完预留后无余量）时，
        回落 ``FALLBACK_MAX_BYTES``——不猜某个模型的窗口，也不放任无上限注入。
    """
    window = resolve_model_context_window(model=model)
    reserved_output = resolve_model_max_output_tokens(model=model)
    if window <= 0 or reserved_output is None:
        return FALLBACK_MAX_BYTES
    available = (
        window
        - reserved_output
        - _SCAFFOLD_RESERVE_TOKENS
        - window // _AGENT_LOOP_MARGIN_DIVISOR
    )
    if available <= 0:
        return FALLBACK_MAX_BYTES
    return available * _BYTES_PER_TOKEN


# ── 关键节选区 ──────────────────────────────────────────────────────────────────


def first_heading_index(lines: list[str]) -> int | None:
    """Return the line index of the first recognizable chapter heading, or ``None``."""
    for index, raw in enumerate(lines):
        if raw.strip().startswith("### 文件:"):
            continue
        if chapter_heading(raw) is not None:
            return index
    return None


def _headings(lines: list[str]) -> list[tuple[int, str, int]]:
    """Return ``(line_index, title, level)`` for every recognizable heading."""
    found: list[tuple[int, str, int]] = []
    for index, raw in enumerate(lines):
        if raw.strip().startswith("### 文件:"):
            continue
        heading = chapter_heading(raw)
        if heading is not None:
            title, level = heading
            found.append((index, title, level))
    return found


def _keyword_windows(lines: list[str]) -> list[tuple[int, int]]:
    """Return small line windows around review-related OCR hits.

    OCR 常丢标题标记但保留关键词本身；无可识别章节结构时按命中行的局部窗口兜底，
    以免整份退化成"没有关键节"。
    """
    hits = [
        index
        for index, line in enumerate(lines)
        if any(keyword in line for keyword in KEY_SECTION_KEYWORDS)
    ]
    windows: list[list[int]] = []
    for index in hits:
        start, end = max(0, index - 40), min(len(lines), index + 81)
        if windows and start <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], end)
        else:
            windows.append([start, end])
    return [(start, end) for start, end in windows]


def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def select_review_spans(lines: list[str]) -> list[tuple[int, int]]:
    """Return merged ``[start, end)`` line spans covering the review-critical sections.

    章节级：标题命中关键词 → 整章（到下一个同级/更高级标题为止）都算关键节，评分表在标题
    之后几十页也不会被切掉。无任何可识别标题时回落关键词窗口。

    Args:
        lines: 底稿按行切分的结果。

    Returns:
        升序、互不重叠的行区段；无命中返回空列表。
    """
    headings = _headings(lines)
    selected: list[tuple[int, int]] = []
    for position, (heading_index, title, level) in enumerate(headings):
        if not any(keyword in title for keyword in KEY_SECTION_KEYWORDS):
            continue
        end = len(lines)
        for next_index, _next_title, next_level in headings[position + 1 :]:
            if next_level <= level:
                end = next_index
                break
        selected.append((heading_index, end))
    if not selected:
        selected = _keyword_windows(lines)
    return _merge(selected)


# ── 内容优先截断 ────────────────────────────────────────────────────────────────

_OMISSION_MARKER = "\n...[已省略{note}约 {size} 字节；评标办法/评分标准/资格审查等关键章节已优先保留]...\n"


def _head_bytes(text: str, limit: int) -> str:
    """Cut ``text`` to at most ``limit`` UTF-8 bytes on a character boundary."""
    if limit <= 0:
        return ""
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    # errors="ignore" 丢掉上限处被切开的半个多字节字符 —— 产物严格 UTF-8 可解码。
    return raw[:limit].decode("utf-8", errors="ignore")


def _page_note(lines: list[str]) -> str:
    """Describe the page range a chunk covers, for the omission marker."""
    pages = [anchor[0] for raw in lines if (anchor := parse_page_anchor(raw)) is not None]
    if not pages:
        return ""
    if min(pages) == max(pages):
        return f"原第 {min(pages)} 页"
    return f"原第 {min(pages)}-{max(pages)} 页"


def _file_spans(lines: list[str]) -> list[tuple[int, int]]:
    """按 ``### 文件:`` 分隔符切出每份文件的 ``[start, end)`` 行区段。

    底稿是多文件拼接的（招标文件 + 一到多份投标材料）。没有分隔符时整份视作一个区段。
    """
    starts = [index for index, raw in enumerate(lines) if raw.strip().startswith("### 文件:")]
    if not starts:
        return [(0, len(lines))]
    bounds = starts if starts[0] == 0 else [0, *starts]
    return [
        (start, bounds[position + 1] if position + 1 < len(bounds) else len(lines))
        for position, start in enumerate(bounds)
    ]


def rule_source_spans(lines: list[str]) -> list[tuple[int, int]]:
    """Return the file spans that carry the evaluation rules (评分标准/评标办法/资格审查).

    为什么按**文件**而不只按章节区分优先级：2026-08-15 实测事故——投标材料体量远大于招标
    文件且通篇是"投标/技术参数"等词，关键词命中密度高，按文档顺序分配预算时把额度吃光，
    排在其后的**招标文件整份被删**（784KB→136KB，截后只剩投标文件），模型手里没有评分
    标准，只能判 insufficient_evidence。评标的刚性前提是规则必须在场，证据可以按项截取。

    判定不依赖文件名（各家命名千差万别：招标/采购/谈判/询价/磋商文件…），而看该文件区段内
    是否出现关键评审章节信号——规则写在哪份文件里，哪份就是规则源。
    """
    rule_spans: list[tuple[int, int]] = []
    for start, end in _file_spans(lines):
        section = lines[start:end]
        if select_review_spans(section):
            rule_spans.append((start, end))
    return rule_spans


def _chunks(
    lines: list[str],
    spans: list[tuple[int, int]],
    extra_bounds: tuple[int, ...] = (),
) -> list[tuple[list[str], bool]]:
    """Slice the draft into document-order ``(lines, is_key)`` chunks around the key spans.

    Args:
        lines: 底稿全部行。
        spans: 关键评审区段。
        extra_bounds: 额外的强制切分点（文件起始行）。**必须在文件边界处断开**，否则一个
            chunk 会横跨"投标材料尾部 + 招标文件头部"，按头部截断时会把后一份文件的
            文件头连同其前置章节一起丢掉（2026-08-15 实测：评分标准保住了但文件头没了，
            模型失去出处锚点）。
    """
    chunks: list[tuple[list[str], bool]] = []
    cursor = 0
    for start, end in spans:
        for bound in extra_bounds:
            if cursor < bound < start:
                chunks.append((lines[cursor:bound], False))
                cursor = bound
        if start > cursor:
            chunks.append((lines[cursor:start], False))
        chunks.append((lines[start:end], True))
        cursor = end
    for bound in extra_bounds:
        if cursor < bound < len(lines):
            chunks.append((lines[cursor:bound], False))
            cursor = bound
    if cursor < len(lines):
        chunks.append((lines[cursor:], False))
    return chunks


def _allocate(sizes: list[int], tiers: list[int], budget: int) -> list[int]:
    """Allocate the budget tier by tier; within the last tier split evenly by document order.

    Args:
        sizes: 各 chunk 的字节数。
        tiers: 各 chunk 的优先级（数字越小越优先）——
            0=规则源文件的关键评审章节（评分标准所在，必须完整）、
            1=规则源文件其余内容、2=其它文件的关键节、3=其余证据材料。
        budget: 可分配字节总额。

    Returns:
        与 ``sizes`` 等长的分配量。高优先级层足额取用，额度耗尽后低优先级层按剩余均分——
        保证"规则在场"优先于"证据齐全"，因为缺规则会让整单无法评分，缺部分证据只影响个别项。
    """
    allocation = [0] * len(sizes)
    left = budget
    ordered = sorted(set(tiers))
    for tier in ordered[:-1]:
        for index, value in enumerate(tiers):
            if value == tier:
                allocation[index] = min(sizes[index], left)
                left -= allocation[index]
    last = [index for index, value in enumerate(tiers) if value == ordered[-1]]
    for position, index in enumerate(last):
        share = left // (len(last) - position)
        allocation[index] = min(sizes[index], share)
        left -= allocation[index]
    return allocation


def bound_draft_by_content(text: str, *, limit_bytes: int) -> str:
    """Fit the OCR draft into ``limit_bytes`` while keeping the review-critical sections.

    Args:
        text: OCR/直读底稿全文（可含多文件、页锚）。
        limit_bytes: 字节上限；返回值保证不超过该值。

    Returns:
        截断后的底稿。识别不出任何关键节（或预算小到连省略标记都放不下）时回落"保留开头"——
        无内容信号可用时开头仍是最优选择，且与旧行为一致。
    """
    lines = text.splitlines()
    spans = select_review_spans(lines)
    if not spans:
        return _head_bytes(text, limit_bytes)

    # 在文件边界强制切分，保证每个 chunk 只属于一份文件（否则跨文件 chunk 会连累后一份的文件头）。
    rule_ranges = rule_source_spans(lines)
    chunks = _chunks(lines, spans, tuple(start for start, _ in _file_spans(lines) if start > 0))
    texts = ["\n".join(chunk_lines) for chunk_lines, _ in chunks]
    sizes = [len(chunk.encode("utf-8")) for chunk in texts]
    offsets: list[int] = []
    cursor = 0
    for chunk_lines, _ in chunks:
        offsets.append(cursor)
        cursor += len(chunk_lines)
    tiers = [
        (0 if key else 1)
        if any(start <= offset < end for start, end in rule_ranges)
        else (2 if key else 3)
        for offset, (_, key) in zip(offsets, chunks, strict=True)
    ]
    # 每个 chunk 最坏情况都会被削 → 先按"全削"预留标记开销，保证总量不越预算。
    # 用 chunk 全长渲染标记取长度上界（实际省略量 ≤ 全长 → 数字位数不会更多）。
    markers = [
        _OMISSION_MARKER.format(note=_page_note(chunk_lines), size=size)
        for (chunk_lines, _), size in zip(chunks, sizes, strict=True)
    ]
    # 预留 = 全部标记 + chunk 之间的换行分隔符（重新 join 时补回，必须计入预算）。
    reserve = sum(len(marker.encode("utf-8")) for marker in markers) + max(0, len(chunks) - 1)
    if reserve >= limit_bytes:
        return _head_bytes(text, limit_bytes)

    allocation = _allocate(sizes, tiers, limit_bytes - reserve)
    kept: list[str] = []
    for index, chunk in enumerate(texts):
        if allocation[index] >= sizes[index]:
            kept.append(chunk)
            continue
        kept.append(_head_bytes(chunk, allocation[index]) + markers[index])
    return "\n".join(kept)
