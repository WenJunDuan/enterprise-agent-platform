"""评标回归闸（Phase 0）的纯函数单测——不打模型、不起服务、不碰真实语料。

覆盖 `scripts/eval_tender_regression.py` 里全部判定逻辑：YAML 子集解析、case 定义校验、
语料指纹定位、页锚提取、缺陷双键命中、客观分项匹配、manual_review 分列、墙钟聚合。

**为什么这些必须有单测**：四指标是此后每一刀的裁决依据，判定逻辑自己错了，后面所有
数字都是错的且看不出来（design 风险表「缺陷命中判定被钻空子」）。真实评测要打真模型、
$1.4 一跑，不可能靠它回归判定逻辑。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts import eval_tender_regression as ev
from tests import test_no_real_corpus as guard

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CASE_DIR = PROJECT_ROOT / "eval" / "golden" / "case-zj-live"


# ── 守卫扩面：eval/ 下的金标准 yaml 必须进真实语料守卫的扫描面 ────────────────────


def test_real_corpus_guard_scans_golden_case_yaml() -> None:
    """守卫覆盖不到的匿名化纪律等于没有：两个金标准 yaml 必须在扫描面内。"""
    scanned = {p.relative_to(guard.PROJECT_ROOT) for p in guard._scan_files()}
    assert Path("eval/golden/case-zj-live/expected.yaml") in scanned
    assert Path("eval/golden/case-zj-live/corpus.pointer.yaml") in scanned


def test_golden_case_yaml_has_no_real_organization_names() -> None:
    """金标准文件本身过形态守卫（与 guard 主用例同一把尺子，出错时定位更快）。"""
    hits: dict[str, set[str]] = {}
    for path in sorted(CASE_DIR.glob("*.yaml")):
        found = {
            m.group(0)
            for m in guard._ORG_SHAPE.finditer(path.read_text(encoding="utf-8"))
            if m.group(0) not in guard._SYNTHETIC_ALLOWED
        }
        if found:
            hits[path.name] = found
    assert not hits, f"金标准 yaml 出现疑似真实机构名：{hits}"


# ── YAML 子集解析器 ─────────────────────────────────────────────────────────────
#
# 仓库无 PyYAML（不在基础依赖里，venv 里也没有），本次又不准引新依赖，故自带子集解析器。
# 它的存在价值全在「不认识的语法立刻炸」——静默误解析一条 anchors 就等于静默改判据。


def test_parse_yaml_reads_nested_maps_sequences_and_flow_lists() -> None:
    text = """
# 头注释
case: demo
count: 3
ratio: 1.5
missing: null
flag: true
nested:
  inner: 值
  deep:
    leaf: 1
items:
  - id: A
    tags: ["x", "y"]
  - id: B
    tags: []
"""
    data = ev.parse_yaml(text)
    assert data["case"] == "demo"
    assert data["count"] == 3
    assert data["ratio"] == pytest.approx(1.5)
    assert data["missing"] is None
    assert data["flag"] is True
    assert data["nested"] == {"inner": "值", "deep": {"leaf": 1}}
    assert data["items"] == [{"id": "A", "tags": ["x", "y"]}, {"id": "B", "tags": []}]


def test_parse_yaml_accepts_sequence_at_same_indent_as_its_key() -> None:
    """`key:` 后序列不额外缩进是合法 YAML；不支持它会把 `- id: A` 误读成键 `- id`。"""
    data = ev.parse_yaml("items:\n- id: A\n- id: B\n")
    assert data["items"] == [{"id": "A"}, {"id": "B"}]


def test_parse_yaml_keeps_hash_inside_quotes_and_strips_trailing_comment() -> None:
    data = ev.parse_yaml('a: "x # y"   # 注释\nb: 裸值 # 注释\n')
    assert data == {"a": "x # y", "b": "裸值"}


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("a:\n\tb: 1\n", "制表符"),
        ("a: {b: 1}\n", "流式映射"),
        ("a: |\n  多行\n", "多行标量"),
        ("a: &anchor 1\n", "锚点"),
        ("裸行没有冒号\n", "缺少冒号"),
    ],
)
def test_parse_yaml_rejects_unsupported_syntax(text: str, reason: str) -> None:
    with pytest.raises(ev.YamlSubsetError):
        ev.parse_yaml(text)


# ── case 定义加载与校验 ─────────────────────────────────────────────────────────


def test_load_case_reads_the_shipped_golden_case() -> None:
    case = ev.load_case(CASE_DIR)
    assert case.name == "case-zj-live"
    assert [d.id for d in case.defects] == ["D1", "D2", "D3", "D4", "D5", "D6", "D7"]
    assert sum(1 for d in case.defects if d.severity == "P0") == 3
    assert sum(1 for d in case.defects if d.severity == "P1") == 4
    # D2 是缺失类：无页可锚，退化为单键 + must_include 定向。
    d2 = next(d for d in case.defects if d.id == "D2")
    assert d2.absence is True
    assert d2.refs == frozenset()
    assert d2.must_include == ("投标函",)
    # 其余缺陷必须带页锚，否则双键判定退化成关键词蒙对。
    assert all(d.refs for d in case.defects if not d.absence)
    assert [o.item_class for o in case.objective_scores] == ["企业实力", "类似业绩", "项目负责人"]
    assert [(o.expected, o.max) for o in case.objective_scores] == [(6, 6), (9, 9), (3, 3)]
    assert case.price_check.total == pytest.approx(1316033.66)
    assert {f.role for f in case.corpus} == {"tender", "bid"}


def _write_case(tmp_path: Path, expected: str, pointer: str | None = None) -> Path:
    case_dir = tmp_path / "case-x"
    case_dir.mkdir()
    (case_dir / "expected.yaml").write_text(expected, encoding="utf-8")
    (case_dir / "corpus.pointer.yaml").write_text(
        pointer
        if pointer is not None
        else "case: case-x\nfiles:\n  - role: tender\n    sha256: aa\n    bytes: 1\n"
        "  - role: bid\n    sha256: bb\n    bytes: 2\n",
        encoding="utf-8",
    )
    return case_dir


_MINIMAL_EXPECTED = """
case: case-x
defect_classes:
  c1: ["矛盾"]
defects:
  - id: D1
    class: c1
    severity: P0
    role: 甲 vs 乙
    anchors: ["【第1页】"]
objective_scores:
  - item_class: 业绩
    keywords: ["业绩"]
    expected: 9
    max: 9
price_check:
  total: 1.0
  keywords: ["1.00"]
"""


def test_load_case_accepts_a_minimal_well_formed_case(tmp_path: Path) -> None:
    case = ev.load_case(_write_case(tmp_path, _MINIMAL_EXPECTED))
    assert case.defects[0].keywords == ("矛盾",)
    assert case.defects[0].refs == frozenset({("original", 1)})


@pytest.mark.parametrize(
    ("mutation", "replacement", "needle"),
    [
        ("class: c1", "class: 不存在的类别", "defect_classes"),
        ("anchors: [\"【第1页】\"]", "anchors: []", "anchors"),
        ("severity: P0", "severity: P9", "severity"),
    ],
)
def test_load_case_rejects_broken_definitions(
    tmp_path: Path, mutation: str, replacement: str, needle: str
) -> None:
    broken = _MINIMAL_EXPECTED.replace(mutation, replacement)
    with pytest.raises(ev.CaseDefinitionError, match=needle):
        ev.load_case(_write_case(tmp_path, broken))


def test_load_case_rejects_empty_keyword_family(tmp_path: Path) -> None:
    """空关键词族 = 该缺陷永远命不中且无任何提示，正是本闸最该防的静默失准。"""
    broken = _MINIMAL_EXPECTED.replace('c1: ["矛盾"]', "c1: []")
    with pytest.raises(ev.CaseDefinitionError, match="keywords"):
        ev.load_case(_write_case(tmp_path, broken))


def test_load_case_rejects_duplicate_defect_ids(tmp_path: Path) -> None:
    duplicate = """  - id: D1
    class: c1
    severity: P1
    role: 丙 vs 丁
    anchors: ["【第2页】"]
objective_scores:"""
    broken = _MINIMAL_EXPECTED.replace("objective_scores:", duplicate)
    with pytest.raises(ev.CaseDefinitionError, match="D1"):
        ev.load_case(_write_case(tmp_path, broken))


def test_load_case_rejects_pointer_without_both_roles(tmp_path: Path) -> None:
    pointer = "case: case-x\nfiles:\n  - role: tender\n    sha256: aa\n    bytes: 1\n"
    with pytest.raises(ev.CaseDefinitionError, match="bid"):
        ev.load_case(_write_case(tmp_path, _MINIMAL_EXPECTED, pointer=pointer))


# ── 归因二分表登记（纠偏令 v2.1 二节）──────────────────────────────────────────
#
# 列A=文本可达（agency 应治）/ 列B=像素必需（vision-page 上线前结构性不可达）。
# 登记进 expected.yaml 的可选字段 `attribution: text|pixel`，**只登记归因，不改期望值、
# 不改命中判定**——它决定 Step 5 的数字往哪一列记账，跨列记账等于把结论读反。


def test_load_case_reads_optional_attribution_on_defects_and_objective_items(
    tmp_path: Path,
) -> None:
    text = _MINIMAL_EXPECTED.replace(
        'anchors: ["【第1页】"]', 'anchors: ["【第1页】"]\n    attribution: text'
    ).replace("    max: 9", "    max: 9\n    attribution: pixel")
    case = ev.load_case(_write_case(tmp_path, text))
    assert case.defects[0].attribution == ev.ATTRIBUTION_TEXT
    assert case.objective_scores[0].attribution == ev.ATTRIBUTION_PIXEL


def test_load_case_treats_attribution_as_optional(tmp_path: Path) -> None:
    """字段是可选的：没登记就是 None，而不是默认塞一个列，默认值等于替人做归因。"""
    case = ev.load_case(_write_case(tmp_path, _MINIMAL_EXPECTED))
    assert case.defects[0].attribution is None
    assert case.objective_scores[0].attribution is None


@pytest.mark.parametrize(
    ("mutation", "replacement"),
    [
        pytest.param(
            'anchors: ["【第1页】"]',
            'anchors: ["【第1页】"]\n    attribution: 列A',
            id="缺陷侧写了枚举外的值",
        ),
        pytest.param("    max: 9", "    max: 9\n    attribution: image", id="客观分侧写了近义词"),
    ],
)
def test_load_case_rejects_attribution_outside_the_enum(
    tmp_path: Path, mutation: str, replacement: str
) -> None:
    """枚举外的写法一律报错。猜一个 = 静默替人做归因，正是 v2.1 二节禁的跨列记账。"""
    with pytest.raises(ev.CaseDefinitionError, match="attribution"):
        ev.load_case(_write_case(tmp_path, _MINIMAL_EXPECTED.replace(mutation, replacement)))


@pytest.mark.parametrize("case_name", ["case-zj-live", "case-2", "case-3"])
def test_every_shipped_golden_item_is_registered_in_the_attribution_table(case_name: str) -> None:
    """三个金标准 case 的每条缺陷 / 每个客观分项都必须有归因列，漏一条 Step 5 就无法记账。"""
    case = ev.load_case(PROJECT_ROOT / "eval" / "golden" / case_name)
    unregistered = [d.id for d in case.defects if d.attribution is None]
    unregistered += [o.item_class for o in case.objective_scores if o.attribution is None]
    assert not unregistered, f"{case_name} 未登记归因列的条目：{unregistered}"


def test_case_zj_live_attribution_transcribes_the_v21_section_two_table() -> None:
    """逐项对齐 v2.1 二节表：D1/D2/D4/D7 与客观分三项的归因是那张表原文，不是本档自拟。"""
    case = ev.load_case(CASE_DIR)
    assert {d.id: d.attribution for d in case.defects} == {
        "D1": "text",
        "D2": "text",
        "D3": "pixel",
        "D4": "text",
        "D5": "pixel",
        "D6": "pixel",
        "D7": "text",
    }
    assert {o.item_class: o.attribution for o in case.objective_scores} == {
        "企业实力": "pixel",
        "类似业绩": "pixel",
        "项目负责人": "pixel",
    }


def test_credential_triplet_of_case_2_and_3_is_registered_as_pixel_required() -> None:
    """v2.1 二节列B 收录「case-2/3 证书类三项判出率（59 页纯扫描）」——三项须逐条落 pixel。"""
    for case_name, triplet in (("case-2", ("A1", "A2", "A3")), ("case-3", ("B1", "B2", "B3"))):
        case = ev.load_case(PROJECT_ROOT / "eval" / "golden" / case_name)
        by_id = {d.id: d.attribution for d in case.defects}
        assert [by_id[i] for i in triplet] == ["pixel"] * 3, f"{case_name} 证书类三项归因不符"


# ── 语料指纹定位 ────────────────────────────────────────────────────────────────


def _corpus_file(role: str, payload: bytes) -> ev.CorpusFile:
    return ev.CorpusFile(
        role=role,
        sha256=hashlib.sha256(payload).hexdigest(),
        size=len(payload),
        pages=None,
        note="",
    )


def test_resolve_corpus_locates_files_by_size_then_hash(tmp_path: Path) -> None:
    """指针不记路径（路径含真名），故按 bytes 预筛 + sha256 定位——改名挪目录仍能找到。"""
    payload = b"tender-bytes"
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "renamed.doc").write_bytes(payload)
    resolution = ev.resolve_corpus([_corpus_file("tender", payload)], tmp_path)
    assert resolution.paths["tender"] == tmp_path / "sub" / "renamed.doc"
    assert resolution.absent == () and resolution.mismatched == ()
    assert resolution.ok is True


def test_resolve_corpus_reports_absent_role_without_pretending_pass(tmp_path: Path) -> None:
    resolution = ev.resolve_corpus([_corpus_file("bid", b"nowhere")], tmp_path)
    assert resolution.absent == ("bid",)
    assert resolution.ok is False


def test_resolve_corpus_flags_same_size_different_content_as_mismatch(tmp_path: Path) -> None:
    """语料被换（大小恰好相同）→ 显式报错，不能静默测错对象。"""
    (tmp_path / "swapped.pdf").write_bytes(b"BBBBBBBB")
    resolution = ev.resolve_corpus([_corpus_file("bid", b"AAAAAAAA")], tmp_path)
    assert resolution.mismatched == ("bid",)
    assert resolution.absent == ()
    assert resolution.ok is False


# ── 页锚提取 ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("投标.pdf 第5页 一、开标一览表", {("original", 5)}),
        ("【第12页】", {("original", 12)}),
        ("【转换稿第3页】", {("converted", 3)}),
        ("转换稿第 7 页", {("converted", 7)}),
        ("P.12-13", {("original", 12), ("original", 13)}),
        ("证据在 P.6 与 P.7", {("original", 6), ("original", 7)}),
        ("【第10-12页】", {("original", 10), ("original", 11), ("original", 12)}),
        ("没有任何页锚", set()),
    ],
)
def test_extract_page_refs_covers_the_shapes_models_actually_emit(
    text: str, expected: set[ev.PageRef]
) -> None:
    assert ev.extract_page_refs(text) == expected


def test_extract_page_refs_clips_oversized_range_to_its_endpoints() -> None:
    """引一个 1-400 页的巨区间不该等于把全书页锚都蒙中（design 头号风险的机械封堵）。"""
    refs = ev.extract_page_refs("【第1-400页】")
    assert refs == {("original", 1), ("original", 400)}


def test_extract_page_refs_honours_the_declared_coordinate_system() -> None:
    """converted 与 original 是两套坐标系，混算会假命中。"""
    assert ev.extract_page_refs("第5页", default_kind=ev.ARTIFACT_CONVERTED) == {("converted", 5)}
    assert ev.extract_page_refs("第5页") != ev.extract_page_refs(
        "第5页", default_kind=ev.ARTIFACT_CONVERTED
    )


# ── finding 汇集 ────────────────────────────────────────────────────────────────


def test_iter_findings_collects_every_place_a_defect_can_surface() -> None:
    result = {
        "explanation": "整体风险高",
        "reasons": ["投标函在第 3 页缺失"],
        "evidence_chain": [
            {"source": "投标.pdf 第12页 声明函", "finding": "两家数据雷同", "conclusion": "存疑"},
            {
                "source": "招标.doc 第2页",
                "finding": "评分办法",
                "conclusion": "记录",
                "page_kind": "converted",
            },
        ],
        "extracted_data": {
            "scoring": [{"item": "类似业绩", "basis": "见第 317 页合同", "score": 9}],
            "eligibility_checks": [
                {"check": "营业执照", "basis": "第10页", "evidence": {"quote": "副本齐全"}}
            ],
        },
    }
    findings = ev.iter_findings(result)
    origins = [f.origin for f in findings]
    assert any(o.startswith("evidence_chain") for o in origins)
    assert any(o.startswith("scoring") for o in origins)
    assert any(o.startswith("eligibility") for o in origins)
    assert any(o.startswith("reasons") for o in origins)
    assert any(o.startswith("explanation") for o in origins)
    first = next(f for f in findings if f.origin == "evidence_chain[0]")
    assert first.refs == {("original", 12)}
    assert "雷同" in first.text
    # page_kind=converted 的条目必须落在 converted 坐标系，不能冒充原件页。
    second = next(f for f in findings if f.origin == "evidence_chain[1]")
    assert second.refs == {("converted", 2)}


# ── 缺陷双键命中 ────────────────────────────────────────────────────────────────


def _defect(**over: object) -> ev.Defect:
    base = {
        "id": "D1",
        "defect_class": "cross_doc_contradiction",
        "severity": "P0",
        "role": "甲 vs 乙",
        "refs": frozenset({("original", 12), ("original", 13)}),
        "keywords": ("矛盾", "雷同"),
        "must_include": (),
        "absence": False,
    }
    base.update(over)
    return ev.Defect(**base)  # type: ignore[arg-type]


def _finding(text: str, refs: set[ev.PageRef], origin: str = "evidence_chain[0]") -> ev.Finding:
    return ev.Finding(origin=origin, text=text, refs=frozenset(refs))


def test_match_defects_needs_both_keys_on_the_same_finding() -> None:
    defect = _defect()
    hit = ev.match_defects([defect], [_finding("两家数据雷同", {("original", 12)})])
    assert hit.hits == {"D1": "evidence_chain[0]"}
    assert hit.missed == () and hit.rate == pytest.approx(1.0)


@pytest.mark.parametrize(
    "findings",
    [
        pytest.param([_finding("此项证据齐全", {("original", 12)})], id="只中页锚"),
        pytest.param([_finding("两家数据雷同", {("original", 99)})], id="只中类别"),
        pytest.param([_finding("两家数据雷同", set())], id="类别中但无页锚"),
        pytest.param(
            [
                _finding("此项证据齐全", {("original", 12)}, "evidence_chain[0]"),
                _finding("两家数据雷同", {("original", 99)}, "evidence_chain[1]"),
            ],
            id="两键分散在两条finding",
        ),
    ],
)
def test_match_defects_rejects_single_key_and_cross_finding_matches(
    findings: list[ev.Finding],
) -> None:
    outcome = ev.match_defects([_defect()], findings)
    assert outcome.hits == {}
    assert outcome.missed == ("D1",)
    assert outcome.rate == pytest.approx(0.0)


def test_match_defects_uses_keyword_only_for_absence_defects_and_marks_them_weak() -> None:
    """缺失类缺陷无页可锚，双键判定会让它永不可达——退化为单键 + must_include 定向。"""
    defect = _defect(
        id="D2",
        defect_class="required_document_missing",
        refs=frozenset(),
        keywords=("未见", "缺失"),
        must_include=("投标函",),
        absence=True,
    )
    hit = ev.match_defects([defect], [_finding("全文未见投标函与有效期承诺", set())])
    assert hit.hits == {"D2": "evidence_chain[0]"}
    assert hit.weak_key == ("D2",)


def test_match_defects_absence_defect_still_requires_must_include() -> None:
    defect = _defect(
        id="D2",
        refs=frozenset(),
        keywords=("未见", "缺失"),
        must_include=("投标函",),
        absence=True,
    )
    outcome = ev.match_defects([defect], [_finding("未见社保缴纳记录", set())])
    assert outcome.missed == ("D2",)


# ── 客观分逐项比对 ──────────────────────────────────────────────────────────────


def _objective(item_class: str, keywords: tuple[str, ...], expected: float, max_: float):
    return ev.ObjectiveScore(item_class=item_class, keywords=keywords, expected=expected, max=max_)


def test_match_objective_scores_matches_by_keyword_family_not_exact_name() -> None:
    outcome = ev.match_objective_scores(
        [_objective("企业实力", ("企业综合实力", "综合实力"), 6, 6)],
        [{"item": "1 企业综合实力（6分）", "max": 6, "score": 6, "status": "scored"}],
    )
    assert outcome.correct == ("企业实力",)
    assert outcome.rate == pytest.approx(1.0)


def test_match_objective_scores_reports_wrong_value_with_the_actual_score() -> None:
    outcome = ev.match_objective_scores(
        [_objective("类似业绩", ("业绩",), 9, 9)],
        [{"item": "类似项目业绩", "max": 9, "score": 6, "status": "scored"}],
    )
    assert outcome.wrong == (("类似业绩", 9.0, 6.0),)
    assert outcome.correct == ()


def test_match_objective_scores_treats_null_score_as_wrong_not_zero() -> None:
    """score=null 一律不等于 0 分（对接文档硬规则），但它确实没给出客观分。"""
    outcome = ev.match_objective_scores(
        [_objective("类似业绩", ("业绩",), 9, 9)],
        [{"item": "类似业绩", "max": 9, "score": None, "pending_reason": "evidence_unresolved"}],
    )
    assert outcome.wrong == (("类似业绩", 9.0, None),)


def test_match_objective_scores_lists_unmatched_instead_of_silently_scoring_zero() -> None:
    outcome = ev.match_objective_scores(
        [_objective("项目负责人", ("项目负责人",), 3, 3)],
        [{"item": "投标报价", "max": 30, "score": 30}],
    )
    assert outcome.unmatched == ("项目负责人",)
    assert outcome.correct == () and outcome.wrong == ()
    assert outcome.rate == pytest.approx(0.0)


def test_match_objective_scores_disambiguates_by_max_when_several_items_match() -> None:
    outcome = ev.match_objective_scores(
        [_objective("类似业绩", ("业绩",), 9, 9)],
        [
            {"item": "类似业绩", "max": 9, "score": 9},
            {"item": "业绩真实性核查", "max": 4, "score": 0},
        ],
    )
    assert outcome.correct == ("类似业绩",)
    assert outcome.ambiguous == {}


def test_match_objective_scores_flags_真ambiguity_rather_than_guessing() -> None:
    outcome = ev.match_objective_scores(
        [_objective("类似业绩", ("业绩",), 9, 9)],
        [{"item": "类似业绩", "max": 9, "score": 9}, {"item": "业绩加分", "max": 9, "score": 0}],
    )
    assert set(outcome.ambiguous) == {"类似业绩"}
    assert outcome.correct == () and outcome.wrong == ()


# ── 度量侧 item_class 同义词族（纠偏令 v2.1 五节）────────────────────────────────
#
# 附录B 基线 0/3 里业绩 / 负责人是**匹配器没匹配上**，不是链路真漏。先修尺子再读数，
# 否则会把度量债当链路债去修。同义词只准来自实跑里真出现过的项名形态，不许臆造。


def test_match_objective_scores_expands_item_class_synonyms_for_real_name_drift() -> None:
    """0818b3 实跑的项名与 case 声明的 keywords 对不上，度量侧同义词族必须接住。

    漂移样本出处：`knowledge/external/车辆管理系统/results-6e67cbd2-0818b3实跑-20260818.json`
    的 `extracted_data.scoring[].item`（投标供应商实力 / 项目业绩 / 团队人员）。
    """
    outcome = ev.match_objective_scores(
        [
            _objective("企业实力", ("企业综合实力", "综合实力", "企业实力"), 6, 10),
            _objective("类似业绩", ("类似业绩",), 9, 10),
            _objective("项目负责人", ("拟派项目负责人", "项目负责人"), 3, 5),
        ],
        [
            {"item": "投标供应商实力", "max": 10, "score": 6},
            {"item": "项目业绩", "max": 10, "score": 9},
            {"item": "团队人员", "max": 5, "score": 3},
        ],
    )
    assert outcome.correct == ("企业实力", "类似业绩", "项目负责人")
    assert outcome.unmatched == ()


def test_match_objective_scores_synonyms_do_not_leak_across_item_classes() -> None:
    """同义词族按 item_class 分族。跨族串味会把「负责人」判到「业绩」头上，比漏匹配更坏。"""
    outcome = ev.match_objective_scores(
        [_objective("项目负责人", ("拟派项目负责人",), 3, 5)],
        [{"item": "项目业绩", "max": 5, "score": 3}],
    )
    assert outcome.correct == ()
    assert outcome.unmatched == ("项目负责人",)


# ── 客观分列拆二：真漏 vs 匹配器未匹配（纠偏令 v2.1 五节）────────────────────────


def test_match_objective_scores_splits_true_miss_from_matcher_miss() -> None:
    """真漏（结论无该项/无证据）与匹配器未匹配（项名漂移）必须分列，不能混成一个 0/3。

    判别式沿用本函数**已有**的消歧信号——满分值：结论里有同满分值的项 = 该项大概率在场、
    只是名字对不上（度量债）；连同满分值的项都没有 = 结论里真没有这一项（链路债）。
    """
    outcome = ev.match_objective_scores(
        [
            # 匹配上了但没出分 → 「无证据」型真漏
            _objective("企业实力", ("企业综合实力",), 6, 6),
            # 项名对不上、但满分 9 的项在场 → 匹配器未匹配
            _objective("信用评价", ("投标人市场信用评价",), 9, 9),
            # 连满分 3 的项都没有 → 「结论无该项」型真漏
            _objective("演示环节", ("主要功能演示",), 3, 3),
        ],
        [
            {"item": "1 企业综合实力", "max": 6, "score": None, "pending_reason": "evidence_unresolved"},
            {"item": "市场信用", "max": 9, "score": 9},
        ],
    )
    assert outcome.unmatched == ("信用评价", "演示环节")
    assert outcome.true_miss == ("企业实力", "演示环节")
    # 漂移的项名要原样带出来，否则下一轮扩同义词还得靠人翻结论。
    assert outcome.matcher_miss == {"信用评价": ("市场信用",)}


def test_match_objective_scores_keeps_a_wrong_but_scored_item_out_of_both_miss_columns() -> None:
    """给了分只是给错了，既不是真漏也不是度量债——混进去会把两列都读虚。"""
    outcome = ev.match_objective_scores(
        [_objective("类似业绩", ("类似业绩",), 9, 9)],
        [{"item": "类似业绩", "max": 9, "score": 6}],
    )
    assert outcome.wrong == (("类似业绩", 9.0, 6.0),)
    assert outcome.true_miss == () and outcome.matcher_miss == {}


# ── manual_review 分列 ──────────────────────────────────────────────────────────


def test_count_pending_keeps_correct_manual_items_out_of_the_degradation_number() -> None:
    """cross_bid / live_event 是正确的待人工，不是链路退化，不能计进劣化数。"""
    outcome = ev.count_pending(
        [
            {"item": "投标报价", "score": None, "pending_reason": "cross_bid"},
            {"item": "现场答辩", "score": None, "pending_reason": "live_event"},
            {"item": "业绩", "score": None, "pending_reason": "evidence_unresolved"},
            {"item": "方案", "score": None, "pending_reason": "manual_mode"},
            {"item": "无理由项", "score": None},
            {"item": "已出分", "score": 5},
        ]
    )
    assert outcome.degrading == {"evidence_unresolved": 1, "manual_mode": 1}
    assert outcome.expected_pending == {"cross_bid": 1, "live_event": 1}
    assert outcome.unknown_reason == 1
    # 无 pending_reason 的 null 是契约违反，必须计进劣化（否则漏报越多分数越好看）。
    assert outcome.degrading_total == 3


# ── 墙钟与聚合 ──────────────────────────────────────────────────────────────────


def test_wall_clock_seconds_reads_the_task_table_timestamps() -> None:
    task = {"submitted_at": "2026-08-18T04:16:52Z", "finished_at": "2026-08-18T04:26:52Z"}
    assert ev.wall_clock_seconds(task) == pytest.approx(600.0)


@pytest.mark.parametrize(
    "task",
    [
        {"submitted_at": "2026-08-18T04:16:52Z", "finished_at": None},
        {"submitted_at": None, "finished_at": "2026-08-18T04:26:52Z"},
        {},
    ],
)
def test_wall_clock_seconds_refuses_to_invent_a_number(task: dict) -> None:
    with pytest.raises(ValueError, match="时间戳"):
        ev.wall_clock_seconds(task)


def test_aggregate_reports_median_and_spread() -> None:
    agg = ev.aggregate([3.0, 1.0, 2.0])
    assert (agg.median, agg.low, agg.high) == (2.0, 1.0, 3.0)
    single = ev.aggregate([7.5])
    assert (single.median, single.low, single.high) == (7.5, 7.5, 7.5)


def test_check_price_looks_for_the_reconciled_total_in_the_conclusion() -> None:
    price = ev.PriceCheck(total=1316033.66, keywords=("1,316,033.66", "1316033.66"))
    assert ev.check_price(price, [_finding("逐项复算合计 1,316,033.66 元", set())]) is True
    assert ev.check_price(price, [_finding("合计约 131 万元", set())]) is False


# ── 单次结论 → 四指标 ──────────────────────────────────────────────────────────


def _conclusion_hitting_d1() -> dict:
    """一份合成结论：命中 D1、企业实力给满分、业绩给错分、报价勾稽做过、1 项待横比。"""
    return {
        "explanation": "整体风险高",
        "reasons": ["声明函与报价明细互相矛盾"],
        "evidence_chain": [
            {
                "source": "投标.pdf 第12页 中小企业声明函",
                "finding": "两家制造商数据雷同",
                "conclusion": "声明不实风险",
            }
        ],
        "extracted_data": {
            "scoring": [
                {"item": "1 企业综合实力", "max": 6, "score": 6, "status": "scored"},
                {"item": "2 类似业绩", "max": 9, "score": 6, "status": "scored"},
                {"item": "3 拟派项目负责人", "max": 3, "score": 3, "status": "scored"},
                {"item": "投标报价", "max": 30, "score": None, "pending_reason": "cross_bid"},
                {
                    "item": "技术参数",
                    "max": 25,
                    "score": None,
                    "pending_reason": "evidence_unresolved",
                    "basis": "逐项复算合计 1,316,033.66 元，与一览表一致",
                },
            ]
        },
    }


# ── 补证工具调用数 / 结论体量（纠偏令 v2.1 三节 + 五节）────────────────────────


def test_count_evidence_tool_calls_returns_none_when_the_server_never_sent_the_signal() -> None:
    """缺信号必须是 None（渲染成 n/a），**不得回退成 0**。

    0 的语义是"跑了但一次没调"，n/a 的语义是"这条信号还没接出来"。v2.1 二节把「工具调用
    日志显示空转」当成援引"失败也是产出"的前提——把 n/a 读成 0 会直接把没接信号的实验
    判成模型空转。
    """
    assert ev.count_evidence_tool_calls({"submitted_at": "x", "finished_at": "y"}) is None


def test_count_evidence_tool_calls_reads_the_task_record_field() -> None:
    assert ev.count_evidence_tool_calls({ev.TOOL_CALL_FIELD: 0}) == 0
    assert ev.count_evidence_tool_calls({ev.TOOL_CALL_FIELD: 17}) == 17


@pytest.mark.parametrize("value", ["17", -1, 3.5, True])
def test_count_evidence_tool_calls_refuses_a_malformed_signal(value: object) -> None:
    """任务记录来自 HTTP，是信任边界：形态不对就当场炸，不猜也不静默降级。"""
    with pytest.raises(ValueError, match=ev.TOOL_CALL_FIELD):
        ev.count_evidence_tool_calls({ev.TOOL_CALL_FIELD: value})


def test_conclusion_size_counts_utf8_bytes_and_characters_of_the_whole_body() -> None:
    """两个数都要：阈值在 v2.1 里以「字」计，列名却是字节数，只留一个必被读错。"""
    size = ev.conclusion_size({"explanation": "中文"})
    # 规范化序列化后是 `{"explanation": "中文"}`：21 字符，其中 2 个汉字各占 3 字节 → 25 字节。
    assert size.characters == 21
    assert size.bytes == 25


def test_evaluate_result_composes_all_four_metrics_from_one_conclusion() -> None:
    case = ev.load_case(CASE_DIR)
    task = {"submitted_at": "2026-08-18T04:16:52Z", "finished_at": "2026-08-18T04:26:52Z"}
    metrics = ev.evaluate_result(case, task, _conclusion_hitting_d1(), request_id="r-1")
    assert metrics.wall_clock == pytest.approx(600.0)
    assert set(metrics.recall.hits) == {"D1"}
    assert metrics.recall.total == 7
    assert metrics.objective.correct == ("企业实力", "项目负责人")
    assert metrics.objective.wrong == (("类似业绩", 9.0, 6.0),)
    assert metrics.pending.expected_pending == {"cross_bid": 1}
    assert metrics.pending.degrading == {"evidence_unresolved": 1}
    assert metrics.price_ok is True


# ── 干跑（--dry-run）与退出码 ──────────────────────────────────────────────────


def test_check_case_maps_corpus_state_to_distinct_exit_codes() -> None:
    """缺席=SKIP、指纹不符=报错，两者退出码必须分开，谁都不许当成通过。"""
    case = ev.load_case(CASE_DIR)
    ready = ev.CorpusResolution(paths={"tender": CASE_DIR, "bid": CASE_DIR}, absent=(), mismatched=())
    assert ev.check_case(case, ready)[0] == ev.EXIT_OK
    assert ev.check_case(case, ev.CorpusResolution({}, ("bid",), ()))[0] == ev.EXIT_CORPUS_ABSENT
    assert ev.check_case(case, ev.CorpusResolution({}, (), ("bid",)))[0] == ev.EXIT_CORPUS_MISMATCH


def test_dry_run_on_absent_corpus_prints_skip_reason_and_never_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = ev.main(["prog", "--case", "case-zj-live", "--dry-run", "--corpus-root", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == ev.EXIT_CORPUS_ABSENT
    assert "SKIP" in out
    assert "tender" in out and "bid" in out
    # 完整性报告要把 case 收录量交代清楚，否则"干跑通过"看不出跑的是什么。
    assert "缺陷 7 条" in out
    assert "客观分 3 项" in out


def test_dry_run_requires_backend_only_for_real_runs(tmp_path: Path) -> None:
    """干跑不该逼用户编一个 backend 地址；真跑缺 backend 必须当场拒绝。"""
    with pytest.raises(SystemExit):
        ev.main(["prog", "--case", "case-zj-live"])


# ── 轮询 ────────────────────────────────────────────────────────────────────────


def test_wait_for_returns_the_terminal_state_it_saw() -> None:
    states = iter(["running", "running", "ready"])
    seen = ev.wait_for("招标 OCR", lambda: next(states), {"ready", "failed"}, timeout=5, interval=0)
    assert seen == "ready"


def test_wait_for_raises_on_timeout_instead_of_proceeding_with_a_half_baked_case() -> None:
    with pytest.raises(TimeoutError, match="招标 OCR"):
        ev.wait_for("招标 OCR", lambda: "running", {"ready"}, timeout=0.05, interval=0.01)


# ── 报告 ────────────────────────────────────────────────────────────────────────


def test_render_report_puts_four_metrics_and_the_sample_size_in_one_table() -> None:
    case = ev.load_case(CASE_DIR)
    task = {"submitted_at": "2026-08-18T04:16:52Z", "finished_at": "2026-08-18T04:26:52Z"}
    runs = [ev.evaluate_result(case, task, _conclusion_hitting_d1(), request_id=f"r-{i}") for i in range(2)]
    text = ev.render_report(case, mode="single", runs=runs, notes=["OCR 状态 degraded"])
    assert "n=2" in text
    assert "墙钟" in text and "manual_review" in text and "缺陷召回" in text and "客观分" in text
    assert "600" in text
    # 未命中缺陷与未匹配项必须逐条列出，否则数字降了也不知道降在哪。
    assert "D3" in text
    assert "OCR 状态 degraded" in text
    # 单 case 过拟合风险：表头永久标注样本量（design 风险表要求）。
    assert "case-zj-live" in text


def _report(task: dict, *, runs: int = 2) -> str:
    case = ev.load_case(CASE_DIR)
    metrics = [
        ev.evaluate_result(case, task, _conclusion_hitting_d1(), request_id=f"r-{i}")
        for i in range(runs)
    ]
    return ev.render_report(case, mode="single", runs=metrics, notes=[])


_TASK = {"submitted_at": "2026-08-18T04:16:52Z", "finished_at": "2026-08-18T04:26:52Z"}


def test_render_report_splits_the_objective_metric_into_true_miss_and_matcher_miss() -> None:
    """v2.1 五节：单一「客观分准确率」读不出 0/3 里哪几项该修链路、哪几项该修尺子。"""
    text = _report(_TASK)
    assert "真漏" in text and "结论无该项/无证据" in text
    assert "匹配器未匹配" in text and "项名漂移" in text
    # 合成结论里三项全部匹配上了（两对一错），两个 miss 列都应是 0/3。
    assert text.count("| 0/3 = 0% |") == 2


def _tool_call_cell(text: str) -> str:
    """补证工具调用数那一行的**中位列**。计算式列本身写着 n/a 的语义说明，不能连它一起断言。"""
    row = next(line for line in text.splitlines() if line.startswith("| 补证工具调用数"))
    return row.split("|")[2].strip()


def test_render_report_shows_na_not_zero_when_the_tool_call_signal_is_absent() -> None:
    text = _report(_TASK)
    assert "补证工具调用数" in text
    assert _tool_call_cell(text) == "n/a"


def test_render_report_reports_the_tool_call_count_when_the_task_carries_it() -> None:
    text = _report({**_TASK, ev.TOOL_CALL_FIELD: 17})
    assert _tool_call_cell(text) == "17"


def test_render_report_carries_the_conclusion_size_row_and_its_p06_threshold_footnote() -> None:
    """v2.1 三节：连续两轮 >40K 触发 P0.6 复议——阈值不写进报告，读数字的人无从判定。"""
    text = _report(_TASK)
    assert "结论字节数" in text
    assert str(ev.CONCLUSION_SIZE_REVIEW_THRESHOLD // 1000) + "K" in text
    assert "P0.6" in text
    # 单位陷阱必须写明：阈值以「字」计，本列以 UTF-8 字节计，两者不可直接比。
    assert "字节" in text and "字数" in text


def test_render_report_registers_every_item_in_the_v21_attribution_table() -> None:
    """归因二分表是 Step 5 的唯一解读框架（v2.1 二节），报告里必须逐项登记且分列合计。"""
    text = _report(_TASK)
    assert "归因二分表" in text
    assert "列A" in text and "文本可达" in text
    assert "列B" in text and "像素必需" in text
    rows = {
        line.split("|")[1].strip(): line
        for line in text.splitlines()
        if line.startswith("| ") and line.count("|") == 5
    }
    assert "列A" in rows["D1"] and "列B" in rows["D3"]
    assert "列B" in rows["企业实力"]
    # 合成结论 D1 双跑全中、D3 全漏：命中列要能反映出来。
    assert "2/2" in rows["D1"] and "0/2" in rows["D3"]
    assert "列B 在 vision-page 上线前" in text
