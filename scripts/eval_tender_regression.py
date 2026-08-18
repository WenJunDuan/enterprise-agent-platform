#!/usr/bin/env python3
"""评标回归闸（Phase 0 "先造尺子"）：对一个金标准 case 端到端跑评标，出四指标。

    uv run python scripts/eval_tender_regression.py --case case-zj-live \\
        --backend http://127.0.0.1:9999 [--mode single] [--repeat 3]
    uv run python scripts/eval_tender_regression.py --case case-zj-live --dry-run

**为什么走 HTTP 而不是 import ``server.tender``**：评测对象是端到端行为（准入闸、上传
即 OCR、criteria 预抽、软超时都在这层），绕过 HTTP 就测不到它们。故本脚本只认
``/tender/*`` 公开接口，可整文件拷到部署机跑。

四指标（计算式机械可复跑，无自由裁量，见 design「方案 §2」）：

==================  ==========================================================
墙钟                ``finished_at − submitted_at``（任务表时间戳，含重试）；
                    ``--repeat N`` 取中位并附极差
manual_review 项数  ``scoring[]`` 中 ``score is None`` 的计数，按 ``pending_reason``
                    分列。``cross_bid`` / ``live_event`` **单列不计入劣化**——它们
                    是正确的待人工，不是链路退化
跨文件缺陷召回率    命中数 / ``expected.defects`` 总数。命中 = 结论中**同一条**
                    finding 的页锚 ∩ 缺陷页锚 ≠ ∅ **且**类别关键词命中（双键防蒙对）
客观分准确率        ``expected.objective_scores`` 与 ``scoring[]`` 逐项比对；项名用
                    关键词族匹配（模型输出的项名有措辞漂移），匹配不上的**显式列为
                    未匹配**，不静默算 0
==================  ==========================================================

退出码：0 通过 / 1 运行期失败 / 2 case 定义错误 / 3 语料缺席（SKIP）/ 4 语料指纹不符。

**本脚本不内置任何项目的评分项与缺陷**：它们随标书而异，写死等于把一次测试当产品配置
（沿用 ``scripts/measure_tender_evidence.py`` 立下的规矩）。要测哪个 case 就写哪个
``eval/golden/<case>/``。

YAML 子集自解析的由来：仓库基础依赖里没有 PyYAML（venv 里也没有），Phase 0 又不准引新
依赖。故内置一个只认「映射 / 缩进序列 / 流式列表 / 标量 / 注释」的解析器，**认不出的
语法一律报错**——静默误解析一条 anchors 等于静默改判据。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
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
    """一条必须被召回的缺陷（匿名：角色代号 + 页锚 + 类别枚举）。"""

    id: str
    defect_class: str
    severity: str
    role: str
    refs: frozenset[PageRef]
    keywords: tuple[str, ...]
    must_include: tuple[str, ...]
    absence: bool


@dataclass(frozen=True)
class ObjectiveScore:
    """一项客观分基线：项名用关键词族匹配，分值精确比对。"""

    item_class: str
    keywords: tuple[str, ...]
    expected: float
    max: float


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
    correct: tuple[str, ...]
    wrong: tuple[tuple[str, float, float | None], ...]
    unmatched: tuple[str, ...]
    ambiguous: dict[str, tuple[str, ...]]
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


def match_objective_scores(
    expected: list[ObjectiveScore] | tuple[ObjectiveScore, ...],
    scoring: list[dict[str, Any]],
) -> ObjectiveOutcome:
    """客观分逐项比对。项名走关键词族（模型输出项名有措辞漂移，全名精确匹配必错）。

    匹配不上 → 进 ``unmatched`` 显式列出，**不静默算 0 分**；多项撞上且满分值也无法
    区分 → 进 ``ambiguous``，宁可报"分不清"也不猜一个。
    """
    correct: list[str] = []
    wrong: list[tuple[str, float, float | None]] = []
    unmatched: list[str] = []
    ambiguous: dict[str, tuple[str, ...]] = {}
    for spec in expected:
        matches = [
            row
            for row in scoring
            if any(keyword in str(row.get("item") or "") for keyword in spec.keywords)
        ]
        if not matches:
            unmatched.append(spec.item_class)
            continue
        if len(matches) > 1:
            narrowed = [row for row in matches if _as_float(row.get("max")) == spec.max]
            if len(narrowed) != 1:
                ambiguous[spec.item_class] = tuple(str(row.get("item") or "") for row in matches)
                continue
            matches = narrowed
        actual = _as_float(matches[0].get("score"))
        if actual is not None and abs(actual - spec.expected) < 1e-6:
            correct.append(spec.item_class)
        else:
            wrong.append((spec.item_class, spec.expected, actual))
    return ObjectiveOutcome(
        correct=tuple(correct),
        wrong=tuple(wrong),
        unmatched=tuple(unmatched),
        ambiguous=ambiguous,
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


@dataclass(frozen=True)
class RunMetrics:
    """单次评标的四指标快照。"""

    request_id: str
    wall_clock: float
    recall: DefectRecall
    objective: ObjectiveOutcome
    pending: PendingOutcome
    price_ok: bool


def evaluate_result(
    case: GoldenCase, task: dict[str, Any], result: dict[str, Any], *, request_id: str
) -> RunMetrics:
    """一份结论 + 它的任务记录 → 四指标。纯函数，可脱离服务端单测。"""
    findings = iter_findings(result)
    scoring = (result.get("extracted_data") or {}).get("scoring") or []
    return RunMetrics(
        request_id=request_id,
        wall_clock=wall_clock_seconds(task),
        recall=match_defects(case.defects, findings),
        objective=match_objective_scores(case.objective_scores, scoring),
        pending=count_pending(scoring),
        price_ok=check_price(case.price_check, findings),
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


def render_report(case: GoldenCase, *, mode: str, runs: list[RunMetrics], notes: list[str]) -> str:
    """四指标单表（markdown）。表头永久标注 case 与样本量 n——单 case 过拟合是已知风险。"""
    lines = [
        f"## 评标回归闸 · {case.name} · mode={mode} · n={len(runs)}",
        "",
        "| 指标 | 中位 | 极差 | 计算式 |",
        "|---|---|---|---|",
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
        "",
    ]
    for index, run in enumerate(runs, start=1):
        lines.append(f"- run{index} `{run.request_id}`：墙钟 {run.wall_clock:.0f}s")
        lines.append(f"  - 缺陷命中 {sorted(run.recall.hits)}；未命中 {list(run.recall.missed)}")
        if run.recall.weak_key:
            lines.append(f"  - 弱键判定（缺失类无页锚，仅关键词 + must_include）：{list(run.recall.weak_key)}")
        if run.objective.wrong:
            lines.append(f"  - 客观分不符 {[(c, e, a) for c, e, a in run.objective.wrong]}")
        if run.objective.unmatched:
            lines.append(f"  - 客观分**未匹配**（不算 0 分，需人看项名漂移）：{list(run.objective.unmatched)}")
        if run.objective.ambiguous:
            lines.append(f"  - 客观分项名有歧义，未采信：{run.objective.ambiguous}")
        if run.pending.degrading or run.pending.unknown_reason:
            lines.append(
                f"  - 待定分列 {run.pending.degrading}"
                f"（无 pending_reason 的 null：{run.pending.unknown_reason}）"
            )
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


# ── HTTP 驱动（只认 /tender/* 公开面）──────────────────────────────────────────

_CRITERIA_TERMINAL = frozenset({"ready", "failed"})
_OCR_TERMINAL = frozenset({"ready", "degraded", "partial", "failed"})
_TASK_TERMINAL = frozenset({"completed", "failed"})
# 单请求超时：45MB 投标件上传是长尾，轮询 GET 反而很快。与 --timeout（整段等待预算）分开。
HTTP_TIMEOUT_SEC = 300.0


def wait_for(
    what: str,
    probe: Any,
    terminal: frozenset[str] | set[str],
    *,
    timeout: float,
    interval: float,
) -> str:
    """轮询到终态并返回它；超时抛错。

    超时**不**降级继续：拿一份 criteria 还没抽出来的项目去评标，出来的数字没有意义。
    """
    deadline = time.monotonic() + timeout
    while True:
        state = probe()
        if state in terminal:
            return state
        if time.monotonic() >= deadline:
            raise TimeoutError(f"{what} 等待超时（{timeout:.0f}s），最后状态 {state!r}")
        time.sleep(interval)


class TenderBackend:
    """``/tender/*`` 公开接口的薄客户端。

    刻意不 import ``server.tender``：评测对象是端到端行为（准入闸 / 上传即 OCR /
    criteria 预抽 / 软超时都在 HTTP 这层），绕过它就测不到。
    """

    def __init__(self, base_url: str, *, token: str | None) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), headers=headers, timeout=HTTP_TIMEOUT_SEC
        )

    def close(self) -> None:
        self._client.close()

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, **kwargs)
        if response.is_error:
            raise RuntimeError(f"{method} {path} → HTTP {response.status_code}：{response.text[:500]}")
        return response.json()

    def create_project(self, *, title: str, scenario: str) -> str:
        payload = {"scenario": scenario, "title": title}
        return str(self._call("POST", "/tender/projects", json=payload)["project_id"])

    def upload(self, path: Path, *, project_id: str, endpoint: str) -> dict[str, Any]:
        with path.open("rb") as handle:
            files = [("files", (path.name, handle, "application/octet-stream"))]
            return self._call("POST", f"/tender/projects/{project_id}/{endpoint}", files=files)

    def docs_status(self, project_id: str) -> dict[str, Any]:
        return self._call("GET", f"/tender/projects/{project_id}/docs-status")

    def submit_evaluation(self, project_id: str, bid_path: Path, bid_id: str) -> str:
        with bid_path.open("rb") as handle:
            data = {"mode": "upload", "form_json": json.dumps({"bid_id": bid_id})}
            files = [("files", (bid_path.name, handle, "application/octet-stream"))]
            body = self._call(
                "POST", f"/tender/projects/{project_id}/evaluate", data=data, files=files
            )
        return str(body["request_id"])

    def task(self, request_id: str) -> dict[str, Any]:
        return self._call("GET", f"/tender/tasks/{request_id}")

    def result(self, request_id: str) -> dict[str, Any]:
        return self._call("GET", f"/tender/tasks/{request_id}/result")


def _bid_ocr_status(backend: TenderBackend, project_id: str, bid_id: str) -> str:
    for row in backend.docs_status(project_id).get("bids") or []:
        if row.get("bid_id") == bid_id:
            return str(row.get("ocr_status") or "pending")
    return "pending"


def run_case(
    case: GoldenCase,
    backend: TenderBackend,
    resolution: CorpusResolution,
    *,
    repeat: int,
    poll_interval: float,
    timeout: float,
) -> tuple[list[RunMetrics], list[str]]:
    """建项目 → 传招标 → 等 criteria → 传投标 → 等 OCR → 评标 ×N → 取结论。

    ``--repeat`` 复用同一项目与同一 ``bid_id``：OCR 只跑一遍，重复的只是评标本身——
    墙钟指标的定义（``finished_at − submitted_at``）本就不含上传与预热。
    """
    notes: list[str] = []
    project_id = backend.create_project(title=case.project_title, scenario=case.scenario)
    notes.append(f"project_id={project_id}")
    backend.upload(resolution.paths["tender"], project_id=project_id, endpoint="tender-doc")
    criteria_state = wait_for(
        "招标文件 criteria 抽取",
        lambda: str(
            (backend.docs_status(project_id).get("tender_doc") or {}).get("criteria_status")
            or "pending"
        ),
        _CRITERIA_TERMINAL,
        timeout=timeout,
        interval=poll_interval,
    )
    if criteria_state != "ready":
        raise RuntimeError(f"criteria 抽取终态为 {criteria_state}：没有评分标准的评标不构成基线")
    bid_id = str(
        backend.upload(resolution.paths["bid"], project_id=project_id, endpoint="bids")["bid_id"]
    )
    ocr_state = wait_for(
        f"投标 OCR({bid_id})",
        lambda: _bid_ocr_status(backend, project_id, bid_id),
        _OCR_TERMINAL,
        timeout=timeout,
        interval=poll_interval,
    )
    if ocr_state == "failed":
        raise RuntimeError("投标 OCR 失败：无底稿可依，评标数字无意义")
    if ocr_state != "ready":
        notes.append(f"投标 OCR 终态为 {ocr_state}（非 ready）——本轮数字须带此前提读")
    runs: list[RunMetrics] = []
    for index in range(1, repeat + 1):
        request_id = backend.submit_evaluation(project_id, resolution.paths["bid"], bid_id)
        state = wait_for(
            f"评标 run{index}({request_id})",
            lambda rid=request_id: str(backend.task(rid).get("status") or ""),
            _TASK_TERMINAL,
            timeout=timeout,
            interval=poll_interval,
        )
        task = backend.task(request_id)
        if state != "completed":
            raise RuntimeError(f"评标 run{index} 终态 {state}：{task.get('error_detail')}")
        runs.append(
            evaluate_result(case, task, backend.result(request_id), request_id=request_id)
        )
    return runs, notes


# ── CLI ─────────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评标回归闸：金标准 case 端到端出四指标")
    parser.add_argument("--case", required=True, help="eval/golden/ 下的 case 目录名")
    parser.add_argument("--backend", help="服务端 base URL，如 http://127.0.0.1:9999（真跑必填）")
    parser.add_argument(
        "--mode",
        choices=("single", "itemized"),
        default="single",
        help="报告里的路径标签。**服务端走哪条路径由服务端自己决定**，本脚本改不了它；"
        "Phase 0 只存在 single 一条路径",
    )
    parser.add_argument("--repeat", type=int, default=1, help="重复评标次数，取中位并附极差")
    parser.add_argument("--corpus-root", help=f"语料根目录（默认取 pointer 的 {DEFAULT_CORPUS_ROOT}）")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="轮询间隔秒")
    parser.add_argument("--timeout", type=float, default=1800.0, help="单个等待阶段的超时秒")
    parser.add_argument("--dry-run", action="store_true", help="只校验 case 完整性与语料指纹")
    parser.add_argument("--out", help="把 markdown 报告另存到该文件")
    args = parser.parse_args(argv[1:])
    if not args.dry_run and not args.backend:
        parser.error("真跑必须给 --backend；只想校验 case 完整性请用 --dry-run")
    if args.repeat < 1:
        parser.error("--repeat 至少为 1")
    return args


def main(argv: list[str]) -> int:
    """入口。鉴权 token 走环境变量 ``TENDER_EVAL_TOKEN``，不做成命令行参数（免进 shell 历史）。"""
    args = _parse_args(argv)
    case_dir = REPO_ROOT / "eval" / "golden" / args.case
    try:
        case = load_case(case_dir)
    except (CaseDefinitionError, YamlSubsetError) as exc:
        print(f"case 定义错误（{case_dir}）：{exc}")
        return EXIT_CASE_INVALID
    root = Path(args.corpus_root) if args.corpus_root else REPO_ROOT / case.corpus_root
    resolution = resolve_corpus(case.corpus, root)
    code, report = check_case(case, resolution)
    print(report)
    if args.dry_run or code != EXIT_OK:
        return code

    backend = TenderBackend(args.backend, token=os.getenv("TENDER_EVAL_TOKEN"))
    try:
        runs, notes = run_case(
            case,
            backend,
            resolution,
            repeat=args.repeat,
            poll_interval=args.poll_interval,
            timeout=args.timeout,
        )
    except (RuntimeError, TimeoutError, ValueError, httpx.HTTPError) as exc:
        print(f"评测中止：{exc}")
        return EXIT_RUN_FAILED
    finally:
        backend.close()

    notes.append(f"mode 标签={args.mode}（服务端路径由服务端配置决定，本脚本只记录）")
    text = render_report(case, mode=args.mode, runs=runs, notes=notes)
    print()
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"\n报告已写入 {args.out}")
    # 只出数字不设门槛：附录 B 基线未回填前，任何阈值都是拍脑袋（同 measure_* 的做法）。
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
