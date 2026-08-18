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
