"""评标回归闸的判定逻辑：YAML 子集解析、case 校验、语料指纹定位、四指标计算与报告渲染。

内容整体搬自 ``scripts/eval_tender_regression.py``（该文件曾 1,080 行，越过
coding-standards P0「文件 > 300 行必须拆分」），逐字下沉、零行为变更；脚本侧只留 CLI 与
HTTP 驱动，并逐名 re-export 本模块符号，既有 ``scripts.eval_tender_regression.X``
引用点不变。

**这里是四指标判定逻辑的单点**：墙钟 / manual_review 项数 / 跨文件缺陷召回 / 客观分准确率
的计算式只此一处。四指标是此后每一刀的裁决依据，判定逻辑存两份必然漂移——届时"数字变了"
分不清是链路变了还是尺子变了。本模块是纯逻辑，不连服务端、不发 HTTP，可直接单测。
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_CORPUS_ROOT = "knowledge/external"

# 页锚坐标系（与 server/common/corpus.py 的字符串协议同源）：original=原文档页，
# converted=Office→PDF 转换稿页。两套坐标系不可混算，否则页锚交集会假命中。
ARTIFACT_ORIGINAL = "original"
ARTIFACT_CONVERTED = "converted"
PageRef = tuple[str, int]

# 页区间锚展开上限。防的是「引一个 1-400 页的巨区间把所有缺陷页锚都蒙中」——
# design 风险表把"命中判定被钻空子"列为本闸的头号风险，这是它的机械封堵。
MAX_ANCHOR_RANGE_PAGES = 40

_SEVERITIES = frozenset({"P0", "P1"})
_CORPUS_ROLES = ("tender", "bid")

# 归因二分（纠偏令 v2.1 二节）。Step 5 结果的**唯一解读框架**：
#   列A `text`  —— 文本可达，agency 应治，达不达标直接算 agency 的账；
#   列B `pixel` —— 像素必需，vision-page 上线前结构性不可达，不变不计失败、变好另行归因。
# 两列禁止跨列记账：把列B 的漏检记到 agency 头上，等于用一个做不到的目标去否掉一条有效路径。
# 归因逐项登记在 ``expected.yaml`` 的可选字段 ``attribution``，缺省 = 未登记（报告显式标出）。
ATTRIBUTION_TEXT = "text"
ATTRIBUTION_PIXEL = "pixel"
_ATTRIBUTIONS = frozenset({ATTRIBUTION_TEXT, ATTRIBUTION_PIXEL})
_ATTRIBUTION_LABELS = {ATTRIBUTION_TEXT: "列A 文本可达", ATTRIBUTION_PIXEL: "列B 像素必需"}

# 任务记录里的补证工具调用数字段。**服务端今天不写它**：补证工具（``TENDER_AGENCY=1``
# 时开放的 Grep/Read，见 server/tender/corpus_materialize.py）的调用只落 session 事件
# JSONL（server/common/session_logging.py 写 ``event="tool_call"``），任务表
# ``TenderTaskStatusResponse`` 与结论体都没有该字段，故本列今天恒为 n/a。
# 读任务记录而不读结论体：结论体是模型自述，任务记录是服务端记账，只有后者可作证据。
TOOL_CALL_FIELD = "tool_call_count"

# 结论体量的 P0.6 复议阈值（纠偏令 v2.1 三节：该列数字连续两轮越线即触发复议）。
CONCLUSION_SIZE_REVIEW_THRESHOLD = 40_000

# 正确的待人工，不是链路退化：需要全部报价横比 / 需要现场答辩，本来就出不了分。
# 把它们计进 manual_review 劣化数，等于逼后续 Phase 去消灭本该待人工的项。
CORRECT_PENDING_REASONS = ("cross_bid", "live_event")


class YamlSubsetError(ValueError):
    """YAML 子集之外的语法。一律报错而不是猜——猜错就是静默改判据。"""


class CaseDefinitionError(ValueError):
    """金标准 case 定义自相矛盾或引用不存在的枚举。"""


# ── YAML 子集解析 ──────────────────────────────────────────────────────────────


def _strip_comment(text: str) -> str:
    """去掉行尾注释。引号内与流式列表内的 ``#`` 不算注释。"""
    if text[:1] in {'"', "'"}:
        end = text.find(text[0], 1)
        if end < 0:
            raise YamlSubsetError(f"引号未闭合：{text!r}")
        return text[: end + 1]
    if text.startswith("["):
        end = text.rfind("]")
        if end < 0:
            raise YamlSubsetError(f"流式列表未闭合：{text!r}")
        return text[: end + 1]
    return text.split("#", 1)[0].strip()


def _scalar(text: str, lineno: int) -> Any:
    """解析一个已去注释的标量。子集外的写法（锚点/多行/流式映射）直接报错。"""
    if not text:
        return None
    if text[0] in {"&", "*"}:
        raise YamlSubsetError(f"第 {lineno} 行使用了锚点/别名，本子集不支持：{text!r}")
    if text[0] in {"|", ">"}:
        raise YamlSubsetError(f"第 {lineno} 行使用了多行标量，本子集不支持：{text!r}")
    if text[0] == "{":
        raise YamlSubsetError(f"第 {lineno} 行使用了流式映射，本子集不支持：{text!r}")
    if text[0] == "[":
        try:
            return json.loads(text)
        except ValueError as exc:
            raise YamlSubsetError(f"第 {lineno} 行流式列表必须是 JSON 写法：{exc}") from exc
    if text[0] == '"':
        return json.loads(text)
    if text[0] == "'":
        return text[1:-1]
    lowered = text.lower()
    if lowered in {"null", "~"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    for cast in (int, float):
        try:
            return cast(text)
        except ValueError:
            continue
    return text


def _significant_lines(text: str) -> list[tuple[int, str, int]]:
    lines: list[tuple[int, str, int]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw:
            raise YamlSubsetError(f"第 {lineno} 行含制表符；YAML 缩进只允许空格")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((len(raw) - len(raw.lstrip(" ")), stripped, lineno))
    return lines


def _is_seq_item(content: str) -> bool:
    return content == "-" or content.startswith("- ")


def _is_mapping_entry(content: str) -> bool:
    if content[:1] in {"[", "{", '"', "'"}:
        return False
    key, sep, rest = content.partition(":")
    return bool(sep) and (rest == "" or rest.startswith(" ")) and bool(key.strip())


def _parse_block(lines: list[tuple[int, str, int]], i: int, indent: int) -> tuple[Any, int]:
    if _is_seq_item(lines[i][1]):
        return _parse_seq(lines, i, indent)
    return _parse_map(lines, i, indent)


def _parse_map(lines: list[tuple[int, str, int]], i: int, indent: int) -> tuple[dict, int]:
    out: dict[str, Any] = {}
    while i < len(lines) and lines[i][0] == indent and not _is_seq_item(lines[i][1]):
        _, content, lineno = lines[i]
        key, sep, rest = content.partition(":")
        if not sep:
            raise YamlSubsetError(f"第 {lineno} 行不是 `key: value`：{content!r}")
        key = key.strip()
        value = _strip_comment(rest.strip())
        if value:
            out[key] = _scalar(value, lineno)
            i += 1
            continue
        nxt = i + 1
        if nxt < len(lines) and lines[nxt][0] > indent:
            out[key], i = _parse_block(lines, nxt, lines[nxt][0])
        elif nxt < len(lines) and lines[nxt][0] == indent and _is_seq_item(lines[nxt][1]):
            # `key:` 后序列不额外缩进也是合法 YAML；不认它就会把 `- id: A` 读成键 `- id`。
            out[key], i = _parse_seq(lines, nxt, indent)
        else:
            out[key], i = None, nxt
    return out, i


def _parse_seq(lines: list[tuple[int, str, int]], i: int, indent: int) -> tuple[list, int]:
    out: list[Any] = []
    while i < len(lines) and lines[i][0] == indent and _is_seq_item(lines[i][1]):
        _, content, lineno = lines[i]
        item = content[1:].strip()
        if not item:
            if i + 1 < len(lines) and lines[i + 1][0] > indent:
                value, i = _parse_block(lines, i + 1, lines[i + 1][0])
            else:
                value, i = None, i + 1
            out.append(value)
        elif _is_mapping_entry(item):
            # `- id: D1` 的后续键与 `id` 同列（`- ` 占两字符）。合成一行喂给映射解析器，
            # 返回的消耗数正好等于本项在原行表里占的行数。
            child_indent = indent + 2
            value, consumed = _parse_map([(child_indent, item, lineno), *lines[i + 1 :]], 0, child_indent)
            out.append(value)
            i += consumed
        else:
            out.append(_scalar(_strip_comment(item), lineno))
            i += 1
    return out, i


def parse_yaml(text: str) -> Any:
    """解析 YAML 子集：映射 / 缩进序列 / 流式列表 / 标量 / 注释。其余语法报错。"""
    lines = _significant_lines(text)
    if not lines:
        return {}
    value, consumed = _parse_block(lines, 0, lines[0][0])
    if consumed != len(lines):
        raise YamlSubsetError(f"第 {lines[consumed][2]} 行缩进与上文不一致：{lines[consumed][1]!r}")
    return value


# ── 页锚 ────────────────────────────────────────────────────────────────────────

# 底稿里的锚是整行 `【第 N 页】`，但模型写进 evidence_chain[].source 的形态五花八门
# （`第5页` / `P.12-13` / `【转换稿第3页】`）。这里按**行内**形态抓，宽进严出：
# 抓到的页号进集合，坐标系不同的页号绝不混算。
_ANCHOR_RE = re.compile(
    r"(?:【\s*(?P<converted>转换稿)?第\s*(?P<a1>\d+)(?:\s*[-–~]\s*(?P<a2>\d+))?\s*页\s*】)"
    r"|(?:(?P<converted2>转换稿)?第\s*(?P<b1>\d+)(?:\s*[-–~]\s*(?P<b2>\d+))?\s*页)"
    r"|(?:\bP\.?\s*(?P<c1>\d{1,4})(?:\s*[-–~]\s*(?P<c2>\d{1,4}))?\b)"
)


def extract_page_refs(text: str, *, default_kind: str = ARTIFACT_ORIGINAL) -> frozenset[PageRef]:
    """从任意文本抓页锚 → ``{(坐标系, 页号)}``。

    Args:
        text: evidence 出处串 / basis / 期望里的锚点串。
        default_kind: 未显式写"转换稿"时归入哪个坐标系（evidence_chain 有 ``page_kind``
            字段时按它传，缺省 ``original``）。

    区间锚展开为逐页；超过 ``MAX_ANCHOR_RANGE_PAGES`` 的巨区间**只取起止两页**——
    引一个 1-400 页的区间不该等于把全书页锚都命中。
    """
    refs: set[PageRef] = set()
    for match in _ANCHOR_RE.finditer(text or ""):
        converted = match.group("converted") or match.group("converted2")
        kind = ARTIFACT_CONVERTED if converted else default_kind
        start = match.group("a1") or match.group("b1") or match.group("c1")
        end = match.group("a2") or match.group("b2") or match.group("c2")
        first = int(start)
        last = int(end) if end else first
        if last < first:
            first, last = last, first
        if last - first + 1 > MAX_ANCHOR_RANGE_PAGES:
            refs.update({(kind, first), (kind, last)})
        else:
            refs.update((kind, page) for page in range(first, last + 1))
    return frozenset(refs)


# ── 金标准 case ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Defect:
    """一条必须被召回的缺陷（匿名：角色代号 + 页锚 + 类别枚举）。

    ``attribution`` 是 v2.1 二节的归因列（``text`` / ``pixel`` / 未登记 None），只影响
    报告怎么记账，不参与命中判定。
    """

    id: str
    defect_class: str
    severity: str
    role: str
    refs: frozenset[PageRef]
    keywords: tuple[str, ...]
    must_include: tuple[str, ...]
    absence: bool
    attribution: str | None = None


@dataclass(frozen=True)
class ObjectiveScore:
    """一项客观分基线：项名用关键词族匹配，分值精确比对。

    ``attribution`` 同 :class:`Defect`：v2.1 二节的归因列，只用于报告记账。
    """

    item_class: str
    keywords: tuple[str, ...]
    expected: float
    max: float
    attribution: str | None = None


@dataclass(frozen=True)
class PriceCheck:
    total: float
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class CorpusFile:
    """语料指纹。**不记路径**：真实语料的目录名/文件名本身就是真实机构名。"""

    role: str
    sha256: str
    size: int
    pages: int | None
    note: str


@dataclass(frozen=True)
class GoldenCase:
    name: str
    project_title: str
    scenario: str
    defects: tuple[Defect, ...]
    objective_scores: tuple[ObjectiveScore, ...]
    price_check: PriceCheck
    corpus: tuple[CorpusFile, ...]
    corpus_root: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CaseDefinitionError(message)


def _read_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CaseDefinitionError(f"缺文件：{path}")
    data = parse_yaml(path.read_text(encoding="utf-8"))
    _require(isinstance(data, dict), f"{path.name} 顶层必须是映射")
    return data


def _str_tuple(value: Any, field: str) -> tuple[str, ...]:
    _require(isinstance(value, list), f"{field} 必须是列表，实际 {value!r}")
    _require(all(isinstance(v, str) and v for v in value), f"{field} 只能含非空字符串")
    return tuple(value)


def _attribution(raw: dict[str, Any], label: str) -> str | None:
    """可选的 v2.1 二节归因列。

    枚举外的写法一律报错而不是当未登记处理——静默吞掉一个写错的归因，等于替人做了
    跨列记账，而跨列记账正是二节明令禁止的那件事。
    """
    value = raw.get("attribution")
    if value is None:
        return None
    text = str(value).strip()
    _require(
        text in _ATTRIBUTIONS,
        f"{label} 的 attribution={value!r} 不在枚举内，只能是 text（列A 文本可达）"
        f" 或 pixel（列B 像素必需）",
    )
    return text


def _build_defect(raw: dict[str, Any], classes: dict[str, Any]) -> Defect:
    defect_id = str(raw.get("id") or "").strip()
    _require(bool(defect_id), f"缺陷缺 id：{raw!r}")
    defect_class = str(raw.get("class") or "").strip()
    _require(
        defect_class in classes,
        f"缺陷 {defect_id} 的 class={defect_class!r} 不在 defect_classes 枚举里",
    )
    severity = str(raw.get("severity") or "").strip()
    _require(severity in _SEVERITIES, f"缺陷 {defect_id} 的 severity 必须是 P0/P1，实际 {severity!r}")
    absence = bool(raw.get("absence", False))
    anchors = _str_tuple(raw.get("anchors") or [], f"缺陷 {defect_id} 的 anchors")
    refs: set[PageRef] = set()
    for anchor in anchors:
        parsed = extract_page_refs(anchor)
        _require(bool(parsed), f"缺陷 {defect_id} 的 anchors 项 {anchor!r} 解析不出页号")
        refs |= parsed
    _require(
        bool(refs) != absence,
        f"缺陷 {defect_id}：absence=true 的缺失类不能有 anchors，非缺失类必须有 anchors",
    )
    keywords = _str_tuple(classes[defect_class], f"defect_classes.{defect_class}")
    # 空关键词族 = 该类缺陷永远命不中，且不会有任何提示——本闸最该防的就是这种静默失准。
    _require(bool(keywords), f"类别 {defect_class} 的 keywords 关键词族为空，缺陷将永不可命中")
    return Defect(
        id=defect_id,
        defect_class=defect_class,
        severity=severity,
        role=str(raw.get("role") or ""),
        refs=frozenset(refs),
        keywords=keywords,
        must_include=_str_tuple(raw.get("must_include") or [], f"缺陷 {defect_id} 的 must_include"),
        absence=absence,
        attribution=_attribution(raw, f"缺陷 {defect_id}"),
    )


def _build_objective(raw: dict[str, Any]) -> ObjectiveScore:
    item_class = str(raw.get("item_class") or "").strip()
    _require(bool(item_class), f"客观分项缺 item_class：{raw!r}")
    expected, maximum = raw.get("expected"), raw.get("max")
    _require(
        isinstance(expected, (int, float)) and isinstance(maximum, (int, float)),
        f"客观分项 {item_class} 的 expected/max 必须是数值",
    )
    return ObjectiveScore(
        item_class=item_class,
        keywords=_str_tuple(raw.get("keywords") or [], f"客观分项 {item_class} 的 keywords"),
        expected=float(expected),
        max=float(maximum),
        attribution=_attribution(raw, f"客观分项 {item_class}"),
    )


def _build_corpus(pointer: dict[str, Any]) -> tuple[CorpusFile, ...]:
    rows = pointer.get("files")
    _require(isinstance(rows, list) and bool(rows), "corpus.pointer.yaml 的 files 必须是非空列表")
    files: list[CorpusFile] = []
    for raw in rows:
        role = str(raw.get("role") or "").strip()
        digest = str(raw.get("sha256") or "").strip()
        size = raw.get("bytes")
        _require(bool(role) and bool(digest), f"语料条目缺 role/sha256：{raw!r}")
        _require(isinstance(size, int) and size > 0, f"语料 {role} 的 bytes 必须是正整数")
        pages = raw.get("pages")
        _require(pages is None or isinstance(pages, int), f"语料 {role} 的 pages 必须是整数或 null")
        files.append(
            CorpusFile(role=role, sha256=digest, size=size, pages=pages, note=str(raw.get("note") or ""))
        )
    roles = [f.role for f in files]
    for required in _CORPUS_ROLES:
        _require(roles.count(required) == 1, f"corpus.pointer.yaml 必须且只能有一条 role={required}")
    return tuple(files)


def load_case(case_dir: Path) -> GoldenCase:
    """读 ``expected.yaml`` + ``corpus.pointer.yaml`` 并做完整性校验。

    Raises:
        CaseDefinitionError: 缺文件 / 引用不存在的类别枚举 / id 重复 / 语料角色不全等。
    """
    expected = _read_mapping(case_dir / "expected.yaml")
    pointer = _read_mapping(case_dir / "corpus.pointer.yaml")
    classes = expected.get("defect_classes") or {}
    _require(isinstance(classes, dict) and bool(classes), "expected.yaml 缺 defect_classes 枚举")
    raw_defects = expected.get("defects")
    _require(isinstance(raw_defects, list) and bool(raw_defects), "expected.yaml 缺 defects")
    defects = tuple(_build_defect(raw, classes) for raw in raw_defects)
    seen: set[str] = set()
    for defect in defects:
        _require(defect.id not in seen, f"缺陷 id 重复：{defect.id}")
        seen.add(defect.id)
    raw_scores = expected.get("objective_scores")
    _require(isinstance(raw_scores, list) and bool(raw_scores), "expected.yaml 缺 objective_scores")
    price = expected.get("price_check") or {}
    _require(isinstance(price, dict) and isinstance(price.get("total"), (int, float)), "price_check.total 必须是数值")
    return GoldenCase(
        name=str(expected.get("case") or case_dir.name),
        project_title=str(expected.get("project_title") or case_dir.name),
        scenario=str(expected.get("scenario") or "expert_assist"),
        defects=defects,
        objective_scores=tuple(_build_objective(raw) for raw in raw_scores),
        price_check=PriceCheck(
            total=float(price["total"]),
            keywords=_str_tuple(price.get("keywords") or [], "price_check.keywords"),
        ),
        corpus=_build_corpus(pointer),
        corpus_root=str(pointer.get("corpus_root") or DEFAULT_CORPUS_ROOT),
    )


# ── 语料定位（bytes 预筛 + sha256）──────────────────────────────────────────────


@dataclass(frozen=True)
class CorpusResolution:
    paths: dict[str, Path]
    absent: tuple[str, ...]
    mismatched: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.absent and not self.mismatched


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_corpus(files: list[CorpusFile] | tuple[CorpusFile, ...], root: Path) -> CorpusResolution:
    """在 ``root`` 下按 bytes 预筛、再算 sha256 定位每个角色的语料文件。

    指针不记路径（路径含真实机构名），故用指纹定位：改名/挪目录仍能找到，语料被换掉
    则落进 ``mismatched``（显式报错），完全不在则落进 ``absent``（显式 SKIP）。
    预筛只对**字节数相同**的候选算哈希，45MB 语料也只哈希一次。
    """
    by_size: dict[int, list[Path]] = {}
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if path.is_file():
                by_size.setdefault(path.stat().st_size, []).append(path)
    paths: dict[str, Path] = {}
    absent: list[str] = []
    mismatched: list[str] = []
    for spec in files:
        candidates = by_size.get(spec.size, [])
        if not candidates:
            absent.append(spec.role)
            continue
        hit = next((p for p in candidates if _sha256(p) == spec.sha256), None)
        if hit is None:
            mismatched.append(spec.role)
        else:
            paths[spec.role] = hit
    return CorpusResolution(paths=paths, absent=tuple(absent), mismatched=tuple(mismatched))


# ── 四指标 ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    """结论里一处可独立判定的论断。双键必须落在**同一条** finding 上才算命中。"""

    origin: str
    text: str
    refs: frozenset[PageRef]


def iter_findings(result: dict[str, Any]) -> list[Finding]:
    """把结论摊平成 finding 列表：解释 / reasons / 证据链 / 评分项 / 资格审查项。

    缺陷可能出现在其中任意一处（跨文件矛盾多在 evidence_chain，缺失类多在 reasons），
    只扫一处会低估召回。``page_kind=converted`` 的证据条目按转换稿坐标系解析页号。
    """
    findings: list[Finding] = []
    explanation = str(result.get("explanation") or "")
    if explanation:
        findings.append(Finding("explanation", explanation, extract_page_refs(explanation)))
    for index, reason in enumerate(result.get("reasons") or []):
        text = str(reason)
        findings.append(Finding(f"reasons[{index}]", text, extract_page_refs(text)))
    for index, entry in enumerate(result.get("evidence_chain") or []):
        kind = ARTIFACT_CONVERTED if entry.get("page_kind") == "converted" else ARTIFACT_ORIGINAL
        text = " ".join(str(entry.get(key) or "") for key in ("source", "finding", "conclusion"))
        findings.append(
            Finding(f"evidence_chain[{index}]", text, extract_page_refs(text, default_kind=kind))
        )
    data = result.get("extracted_data") or {}
    for index, item in enumerate(data.get("scoring") or []):
        text = " ".join(str(item.get(key) or "") for key in ("item", "basis", "pending_reason"))
        findings.append(Finding(f"scoring[{index}]", text, extract_page_refs(text)))
    for index, check in enumerate(data.get("eligibility_checks") or []):
        evidence = check.get("evidence") or {}
        parts = (check.get("check"), check.get("basis"), evidence.get("source"), evidence.get("quote"))
        text = " ".join(str(part or "") for part in parts)
        findings.append(Finding(f"eligibility_checks[{index}]", text, extract_page_refs(text)))
    return findings


@dataclass(frozen=True)
class DefectRecall:
    hits: dict[str, str]
    missed: tuple[str, ...]
    weak_key: tuple[str, ...]
    total: int

    @property
    def rate(self) -> float:
        return len(self.hits) / self.total if self.total else 0.0


def _defect_matches(defect: Defect, finding: Finding) -> bool:
    if not any(keyword in finding.text for keyword in defect.keywords):
        return False
    if any(term not in finding.text for term in defect.must_include):
        return False
    if defect.absence:
        return True  # 缺失类无页可锚：单键 + must_include，报告里标注弱键
    return bool(defect.refs & finding.refs)


def match_defects(defects: list[Defect] | tuple[Defect, ...], findings: list[Finding]) -> DefectRecall:
    """跨文件缺陷召回：页锚交集 ∧ 类别关键词，两把钥匙必须同时落在同一条 finding 上。"""
    hits: dict[str, str] = {}
    missed: list[str] = []
    for defect in defects:
        origin = next((f.origin for f in findings if _defect_matches(defect, f)), None)
        if origin is None:
            missed.append(defect.id)
        else:
            hits[defect.id] = origin
    return DefectRecall(
        hits=hits,
        missed=tuple(missed),
        weak_key=tuple(d.id for d in defects if d.absence),
        total=len(defects),
    )


@dataclass(frozen=True)
class ObjectiveOutcome:
    """客观分逐项比对结果。

    ``true_miss`` / ``matcher_miss`` 是 v2.1 五节要的**拆列**：前者是链路债（结论里没有
    这一项，或有这一项却没出分＝没证据），后者是度量债（项在结论里、只是项名漂移到关键词
    族之外）。混成一个 0/3 会把度量债当链路债去修。``matcher_miss`` 直接带出漂移的项名，
    下一轮扩同义词有据可依。
    """

    correct: tuple[str, ...]
    wrong: tuple[tuple[str, float, float | None], ...]
    unmatched: tuple[str, ...]
    ambiguous: dict[str, tuple[str, ...]]
    true_miss: tuple[str, ...]
    matcher_miss: dict[str, tuple[str, ...]]
    total: int

    @property
    def rate(self) -> float:
        return len(self.correct) / self.total if self.total else 0.0


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


# item_class → **度量侧**同义词族，在 case 自带 ``keywords`` 之外追加匹配（纠偏令 v2.1
# 五节明示：这是尺子不是链路，不受链路侧检索词表禁令约束）。附录B 基线 0/3 里业绩与负责人
# 是匹配器没匹配上、不是链路真漏，先修尺子再读数。
#
# **每条都必须是实跑里真出现过的项名形态或它们的最大公共子串，不许臆造**。逐条出处：
#   企业实力  ——「企业综合实力」（case-zj-live 参照报告评分表第 1 项）/「投标供应商实力」
#             （`knowledge/external/车辆管理系统/results-6e67cbd2-0818b3实跑-20260818.json`
#             的 `extracted_data.scoring[1].item`，满分 10）。两者与 case 已声明的
#             「综合实力 / 企业实力」的最大公共子串是「实力」，取它一条即覆盖四种形态。
#   类似业绩  ——「项目业绩」（同上 JSON `scoring[2].item`，满分 10）/「业绩」（同目录
#             `materials-server-pull-20260819.json` 的 `result_53f94fd0` 评分项）。公共
#             子串「业绩」。
#   项目负责人——「项目负责人陈述及答辩（暗标）」（同上 `result_53f94fd0`）与 case 声明的
#             「拟派项目负责人」的公共子串是「负责人」；「团队人员」（0818b3 JSON
#             `scoring[3].item`，满分 5）是同一评分类目（人员名单/职称/社保）在另一份标书
#             里的项名，与「负责人」无公共子串，故单列一条。
#
# 质保期**刻意不列**：0818b3 实跑的项名就是「质保期」，与 case 声明的 keywords 一致，
# 没有观测到漂移。没见过的形态不写进来，写了就是臆造。
_ITEM_CLASS_SYNONYMS: dict[str, tuple[str, ...]] = {
    "企业实力": ("实力",),
    "类似业绩": ("业绩",),
    "项目负责人": ("负责人", "团队人员"),
}


def _same_max_items(spec: ObjectiveScore, scoring: list[dict[str, Any]]) -> tuple[str, ...]:
    """结论里满分值与该项相同的项名。空 = 结论里根本没有这一项。

    用满分值判「项名漂移 vs 真的没这一项」，是因为本函数**已经**用它做多命中消歧——
    同一把尺子用两次，不引入新判据。满分值相同只是候选证据，故项名原样带出来给人复核。
    """
    return tuple(
        str(row.get("item") or "") for row in scoring if _as_float(row.get("max")) == spec.max
    )


def _matching_rows(spec: ObjectiveScore, scoring: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """项名命中该项关键词族的评分行。族 = case 声明的 keywords + 度量侧同义词。"""
    keywords = spec.keywords + _ITEM_CLASS_SYNONYMS.get(spec.item_class, ())
    return [row for row in scoring if any(kw in str(row.get("item") or "") for kw in keywords)]


def _pick_match(spec: ObjectiveScore, matches: list[dict[str, Any]]) -> dict[str, Any] | None:
    """多行都命中时按满分值收窄。仍不唯一 → ``None``，由调用方记 ambiguous，不猜一个。"""
    if len(matches) == 1:
        return matches[0]
    narrowed = [row for row in matches if _as_float(row.get("max")) == spec.max]
    return narrowed[0] if len(narrowed) == 1 else None


def match_objective_scores(
    expected: list[ObjectiveScore] | tuple[ObjectiveScore, ...],
    scoring: list[dict[str, Any]],
) -> ObjectiveOutcome:
    """客观分逐项比对。项名走关键词族（模型输出项名有措辞漂移，全名精确匹配必错）。

    匹配不上 → 进 ``unmatched`` 显式列出，**不静默算 0 分**；多项撞上且满分值也无法
    区分 → 进 ``ambiguous``，宁可报"分不清"也不猜一个。``unmatched`` 与"匹配上却没出分"
    再按 v2.1 五节拆成 ``true_miss``（链路债）与 ``matcher_miss``（度量债）。
    """
    correct: list[str] = []
    wrong: list[tuple[str, float, float | None]] = []
    unmatched: list[str] = []
    ambiguous: dict[str, tuple[str, ...]] = {}
    true_miss: list[str] = []
    matcher_miss: dict[str, tuple[str, ...]] = {}
    for spec in expected:
        matches = _matching_rows(spec, scoring)
        if not matches:
            unmatched.append(spec.item_class)
            drifted = _same_max_items(spec, scoring)
            if drifted:
                matcher_miss[spec.item_class] = drifted
            else:
                true_miss.append(spec.item_class)
            continue
        row = _pick_match(spec, matches)
        if row is None:
            ambiguous[spec.item_class] = tuple(str(m.get("item") or "") for m in matches)
            continue
        actual = _as_float(row.get("score"))
        if actual is None:
            # 项在结论里、却没给出分值 = 没证据。这是链路债，与项名漂移完全两回事。
            true_miss.append(spec.item_class)
            wrong.append((spec.item_class, spec.expected, None))
        elif abs(actual - spec.expected) < 1e-6:
            correct.append(spec.item_class)
        else:
            wrong.append((spec.item_class, spec.expected, actual))
    return ObjectiveOutcome(
        correct=tuple(correct),
        wrong=tuple(wrong),
        unmatched=tuple(unmatched),
        ambiguous=ambiguous,
        true_miss=tuple(true_miss),
        matcher_miss=matcher_miss,
        total=len(expected),
    )


@dataclass(frozen=True)
class PendingOutcome:
    degrading: dict[str, int] = field(default_factory=dict)
    expected_pending: dict[str, int] = field(default_factory=dict)
    unknown_reason: int = 0

    @property
    def degrading_total(self) -> int:
        return sum(self.degrading.values()) + self.unknown_reason


def count_pending(scoring: list[dict[str, Any]]) -> PendingOutcome:
    """``score is None`` 的项按 ``pending_reason`` 分列；正确待人工单列不计入劣化。

    没写 ``pending_reason`` 的 null 计进劣化：那是契约违反，放它一马会让"漏报越多、
    指标越好看"。
    """
    degrading: dict[str, int] = {}
    expected_pending: dict[str, int] = {}
    unknown = 0
    for row in scoring:
        if row.get("score") is not None:
            continue
        reason = str(row.get("pending_reason") or "").strip()
        if not reason:
            unknown += 1
        elif reason in CORRECT_PENDING_REASONS:
            expected_pending[reason] = expected_pending.get(reason, 0) + 1
        else:
            degrading[reason] = degrading.get(reason, 0) + 1
    return PendingOutcome(degrading=degrading, expected_pending=expected_pending, unknown_reason=unknown)


def _parse_timestamp(value: Any) -> datetime:
    # 任务表发的是 `...Z` 形态；fromisoformat 自 3.11 起原生认它（本仓 requires-python ≥3.12）。
    try:
        return datetime.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"任务时间戳不可解析：{value!r}") from exc


def wall_clock_seconds(task: dict[str, Any]) -> float:
    """墙钟 = ``finished_at − submitted_at``（任务表时间戳，天然含重试与排队）。"""
    submitted, finished = task.get("submitted_at"), task.get("finished_at")
    if not submitted or not finished:
        raise ValueError(
            f"任务缺时间戳（submitted_at={submitted!r} finished_at={finished!r}），不编墙钟数"
        )
    return (_parse_timestamp(finished) - _parse_timestamp(submitted)).total_seconds()


@dataclass(frozen=True)
class Aggregate:
    median: float
    low: float
    high: float


def aggregate(values: list[float]) -> Aggregate:
    """``--repeat N`` 的聚合：中位数抗 API 抖动，极差让抖动本身可见。"""
    if not values:
        raise ValueError("没有可聚合的样本")
    return Aggregate(median=statistics.median(values), low=min(values), high=max(values))


def check_price(price: PriceCheck, findings: list[Finding]) -> bool:
    """报价勾稽：复算后的合计数是否真的出现在结论里（做没做过勾稽）。"""
    return any(keyword in finding.text for finding in findings for keyword in price.keywords)


def count_evidence_tool_calls(task: dict[str, Any]) -> int | None:
    """任务记录里的补证工具调用数；服务端没发这个信号时返回 ``None``（报告渲染成 n/a）。

    **绝不回退成 0**：0 的语义是"跑了但一次没调"，``None`` 的语义是"这条信号还没接出来"。
    v2.1 二节把「工具调用日志显示空转」当作援引"失败也是产出"条款的前提——把 n/a 读成 0，
    一次根本没接信号的实验就会被判成模型空转，裁决据此走偏。

    Args:
        task: ``GET /tender/tasks/{request_id}`` 的响应体。

    Raises:
        ValueError: 字段在场但不是非负整数。任务记录来自 HTTP，是信任边界，形态不对当场
            炸而不是猜——猜出来的调用数会直接变成裁决依据。
    """
    value = task.get(TOOL_CALL_FIELD)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"任务记录的 {TOOL_CALL_FIELD} 必须是非负整数，实际 {value!r}")
    return value


@dataclass(frozen=True)
class ConclusionSize:
    """结论体量。字节与字数都留着：v2.1 三节的 P0.6 阈值以「字」计，报告列名却是「字节数」，
    只留一个必被读错（2026-08-18 实跑实测 27,716 字 / 53,310 字节，已越字节 40K 而未越
    字数 40K——同一份结论按两种单位读会得出相反结论）。"""

    bytes: int
    characters: int


def conclusion_size(result: dict[str, Any]) -> ConclusionSize:
    """结论体量。规范化序列化（不转义非 ASCII、键排序）后计 UTF-8 字节与字符数。

    序列化口径固定死是为了可复跑：键序或转义方式一变，同一份结论就会给出不同的数字，
    而这个数字要用来做"连续两轮 >40K"的趋势判定。
    """
    text = json.dumps(result, ensure_ascii=False, sort_keys=True)
    return ConclusionSize(bytes=len(text.encode("utf-8")), characters=len(text))


@dataclass(frozen=True)
class RunMetrics:
    """单次评标的指标快照：原四指标 + v2.1 五节新增的补证工具调用数与结论体量。"""

    request_id: str
    wall_clock: float
    recall: DefectRecall
    objective: ObjectiveOutcome
    pending: PendingOutcome
    price_ok: bool
    tool_calls: int | None
    conclusion: ConclusionSize


def evaluate_result(
    case: GoldenCase, task: dict[str, Any], result: dict[str, Any], *, request_id: str
) -> RunMetrics:
    """一份结论 + 它的任务记录 → 全部指标。纯函数，可脱离服务端单测。"""
    findings = iter_findings(result)
    scoring = (result.get("extracted_data") or {}).get("scoring") or []
    return RunMetrics(
        request_id=request_id,
        wall_clock=wall_clock_seconds(task),
        recall=match_defects(case.defects, findings),
        objective=match_objective_scores(case.objective_scores, scoring),
        pending=count_pending(scoring),
        price_ok=check_price(case.price_check, findings),
        tool_calls=count_evidence_tool_calls(task),
        conclusion=conclusion_size(result),
    )


# ── 报告 ────────────────────────────────────────────────────────────────────────


def _row(
    label: str, values: list[float], formula: str, *, unit: str = "", total: int | None = None
) -> str:
    """一行指标：中位 + 极差 + 计算式。``total`` 非空时中位列渲染成 `命中/总数 = 百分比`。"""
    agg = aggregate(values)
    middle = f"{agg.median:.0f}/{total} = {100 * agg.median / total:.0f}%" if total else (
        f"{agg.median:.0f}{unit}"
    )
    spread = "—" if agg.low == agg.high else f"{agg.low:.0f}–{agg.high:.0f}{unit}"
    return f"| {label} | {middle} | {spread} | {formula} |"


def _optional_row(label: str, values: list[int | None], formula: str, *, unit: str = "") -> str:
    """一行**可缺席**的指标。全缺渲染成 ``n/a``，绝不渲染成 0。

    0 与 n/a 在这张表上是两个结论：0 = 跑了但一次没触发，n/a = 这条信号还没接出来。
    部分缺席时按在场样本取中位，并把缺席数标在中位列旁——否则 n=3 里只有 1 个样本
    出数字，读起来和 n=3 全有一模一样。
    """
    present = [float(value) for value in values if value is not None]
    if not present:
        return f"| {label} | n/a | — | {formula} |"
    agg = aggregate(present)
    missing = len(values) - len(present)
    middle = f"{agg.median:,.0f}{unit}" + (f"（另 {missing} 跑 n/a）" if missing else "")
    spread = "—" if agg.low == agg.high else f"{agg.low:,.0f}–{agg.high:,.0f}{unit}"
    return f"| {label} | {middle} | {spread} | {formula} |"


def _core_metric_rows(case: GoldenCase, runs: list[RunMetrics]) -> list[str]:
    """原四指标 + 报价勾稽。计算式一字不改——尺子变了就分不清是链路变了还是尺子变了。"""
    return [
        _row("墙钟", [r.wall_clock for r in runs], "finished_at − submitted_at", unit="s"),
        _row(
            "manual_review 项数（计入劣化）",
            [float(r.pending.degrading_total) for r in runs],
            "score=null 且 pending_reason 非 cross_bid/live_event（无 reason 者也计入）",
        ),
        _row(
            "manual_review 项数（正确待人工）",
            [float(sum(r.pending.expected_pending.values())) for r in runs],
            "cross_bid / live_event —— 本就该待人工，单列不计入劣化",
        ),
        _row(
            "跨文件缺陷召回",
            [float(len(r.recall.hits)) for r in runs],
            "页锚交集 ∧ 类别关键词，双键须落在同一条 finding",
            total=runs[0].recall.total,
        ),
        _row(
            "客观分准确率",
            [float(len(r.objective.correct)) for r in runs],
            "关键词族匹配项名 + 分值精确比对",
            total=runs[0].objective.total,
        ),
        _row(
            "报价勾稽命中次数",
            [float(r.price_ok) for r in runs],
            f"合计 {case.price_check.total:,.2f} 是否出现在结论里",
        ),
    ]


def _v21_metric_rows(runs: list[RunMetrics]) -> list[str]:
    """纠偏令 v2.1 五节新增列：客观分拆二 + 补证工具调用数 + 结论字节数。"""
    return [
        _row(
            "客观分·真漏（结论无该项/无证据）",
            [float(len(r.objective.true_miss)) for r in runs],
            "结论里没有同满分值的项，或有该项却 score=null —— 链路债",
            total=runs[0].objective.total,
        ),
        _row(
            "客观分·匹配器未匹配（项名漂移）",
            [float(len(r.objective.matcher_miss)) for r in runs],
            "关键词族没命中，但结论里有同满分值的项 —— 度量债，先扩同义词再读数",
            total=runs[0].objective.total,
        ),
        _optional_row(
            "补证工具调用数",
            [r.tool_calls for r in runs],
            f"任务记录的 `{TOOL_CALL_FIELD}`；服务端未发该信号时显示 n/a（**不是 0**）",
        ),
        _row(
            "结论字节数",
            [float(r.conclusion.bytes) for r in runs],
            "结论体 JSON 规范化序列化（ensure_ascii=False, sort_keys=True）后的 UTF-8 字节数",
            unit="B",
        ),
    ]


@dataclass(frozen=True)
class _AttributionRow:
    """归因二分表的一行：一条缺陷或一个客观分项 + 它的归因列 + 本批命中跑数。"""

    name: str
    kind: str
    attribution: str | None
    hits: int


def _attribution_rows(case: GoldenCase, runs: list[RunMetrics]) -> list[_AttributionRow]:
    rows = [
        _AttributionRow(
            name=defect.id,
            kind="缺陷",
            attribution=defect.attribution,
            hits=sum(1 for run in runs if defect.id in run.recall.hits),
        )
        for defect in case.defects
    ]
    rows += [
        _AttributionRow(
            name=item.item_class,
            kind="客观分",
            attribution=item.attribution,
            hits=sum(1 for run in runs if item.item_class in run.objective.correct),
        )
        for item in case.objective_scores
    ]
    return rows


def _attribution_table(case: GoldenCase, runs: list[RunMetrics]) -> list[str]:
    """归因二分表（v2.1 二节）：Step 5 结果的唯一解读框架，逐项标列A/列B 并分列合计。"""
    rows = _attribution_rows(case, runs)
    total_runs = len(runs)
    lines = [
        "",
        "**归因二分表（纠偏令 v2.1 二节 · Step 5 结果的唯一解读框架，禁跨列记账）**",
        "",
        "| 项 | 类型 | 归因列 | 命中 |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {row.name} | {row.kind} | {_ATTRIBUTION_LABELS.get(row.attribution, '未登记')} |"
        f" {row.hits}/{total_runs} |"
        for row in rows
    ]
    tallies = []
    for key in (ATTRIBUTION_TEXT, ATTRIBUTION_PIXEL, None):
        group = [row for row in rows if row.attribution == key]
        if group:
            all_runs_hit = sum(1 for row in group if row.hits == total_runs)
            label = _ATTRIBUTION_LABELS.get(key, "未登记")
            tallies.append(f"{label} 全跑命中 {all_runs_hit}/{len(group)} 项")
    lines.append("")
    lines.append(
        "、".join(tallies)
        + "。列B 在 vision-page 上线前不变不计失败、变好另行归因（v2.1 二节）。"
    )
    return lines


def _run_details(runs: list[RunMetrics]) -> list[str]:
    """逐跑明细：数字降了要能一眼看出降在哪一条上。"""
    lines: list[str] = []
    for index, run in enumerate(runs, start=1):
        tool_calls = "n/a" if run.tool_calls is None else str(run.tool_calls)
        lines.append(
            f"- run{index} `{run.request_id}`：墙钟 {run.wall_clock:.0f}s"
            f" · 补证工具调用 {tool_calls}"
            f" · 结论 {run.conclusion.bytes:,} 字节 / {run.conclusion.characters:,} 字"
        )
        lines.append(f"  - 缺陷命中 {sorted(run.recall.hits)}；未命中 {list(run.recall.missed)}")
        if run.recall.weak_key:
            lines.append(f"  - 弱键判定（缺失类无页锚，仅关键词 + must_include）：{list(run.recall.weak_key)}")
        if run.objective.wrong:
            lines.append(f"  - 客观分不符 {[(c, e, a) for c, e, a in run.objective.wrong]}")
        if run.objective.true_miss:
            lines.append(f"  - 客观分**真漏**（结论无该项/无证据，属链路债）：{list(run.objective.true_miss)}")
        if run.objective.matcher_miss:
            lines.append(
                f"  - 客观分**匹配器未匹配**（项名漂移，属度量债；括号内为同满分值的实际项名）："
                f"{run.objective.matcher_miss}"
            )
        if run.objective.ambiguous:
            lines.append(f"  - 客观分项名有歧义，未采信：{run.objective.ambiguous}")
        if run.pending.degrading or run.pending.unknown_reason:
            lines.append(
                f"  - 待定分列 {run.pending.degrading}"
                f"（无 pending_reason 的 null：{run.pending.unknown_reason}）"
            )
    return lines


def render_report(case: GoldenCase, *, mode: str, runs: list[RunMetrics], notes: list[str]) -> str:
    """指标单表 + 归因二分表 + 逐跑明细（markdown）。

    表头永久标注 case 与样本量 n——单 case 过拟合是已知风险。
    """
    threshold = f"{CONCLUSION_SIZE_REVIEW_THRESHOLD // 1000}K"
    # 阈值与单位一起写进报告：不写阈值，读数字的人无从判定该不该复议；不写单位差异，
    # 一份 27,716 字 / 53,310 字节的结论会被同一张表读出相反结论。
    footnote = (
        f"> **结论体量阈值（v2.1 三节）**：该列连续两轮 >{threshold} 即触发 P0.6 复议。"
        "v2.1 原文以「字」计而本列按 UTF-8 字节计（中文 1 字 = 3 字节），两者不可直接比"
        "——判 P0.6 时以逐跑明细里的字数为准，本列只作体量对照。"
    )
    lines = [
        f"## 评标回归闸 · {case.name} · mode={mode} · n={len(runs)}",
        "",
        "| 指标 | 中位 | 极差 | 计算式 |",
        "|---|---|---|---|",
        *_core_metric_rows(case, runs),
        *_v21_metric_rows(runs),
        "",
        footnote,
        *_attribution_table(case, runs),
        "",
        *_run_details(runs),
    ]
    if notes:
        lines.extend(["", "**运行说明**"])
        lines.extend(f"- {note}" for note in notes)
    return "\n".join(lines)


# ── case 完整性（--dry-run）────────────────────────────────────────────────────

EXIT_OK = 0
EXIT_RUN_FAILED = 1
EXIT_CASE_INVALID = 2
EXIT_CORPUS_ABSENT = 3
EXIT_CORPUS_MISMATCH = 4


def check_case(case: GoldenCase, resolution: CorpusResolution) -> tuple[int, str]:
    """case 完整性报告 + 退出码。缺席 SKIP 与指纹不符必须是两个码，谁都不当通过。"""
    p0 = sum(1 for d in case.defects if d.severity == "P0")
    p1 = sum(1 for d in case.defects if d.severity == "P1")
    lines = [
        (
            f"case {case.name}：缺陷 {len(case.defects)} 条（P0 {p0} / P1 {p1}），"
            f"客观分 {len(case.objective_scores)} 项，报价勾稽 {case.price_check.total:,.2f}"
        ),
    ]
    for spec in case.corpus:
        path = resolution.paths.get(spec.role)
        pages = f"{spec.pages} 页" if spec.pages is not None else "页数不适用"
        state = f"命中 {path}" if path else "未定位"
        lines.append(f"  语料[{spec.role}] {spec.size:,} 字节 / {pages} / sha256 {spec.sha256[:12]}… → {state}")
    if resolution.mismatched:
        lines.append(
            f"指纹不符：{list(resolution.mismatched)} —— 字节数撞上但 sha256 对不上，"
            "语料已被替换。评测拒绝在错的对象上出数字。"
        )
        return EXIT_CORPUS_MISMATCH, "\n".join(lines)
    if resolution.absent:
        lines.append(
            f"SKIP：{list(resolution.absent)} 的语料不在 --corpus-root 下（CI / 未放置语料的机器属正常）。"
            "本脚本不产出假通过——要出数字请把语料放到该目录下再跑。"
        )
        return EXIT_CORPUS_ABSENT, "\n".join(lines)
    lines.append("case 完整，语料指纹全部对上。")
    return EXIT_OK, "\n".join(lines)
