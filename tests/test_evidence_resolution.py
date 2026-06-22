"""evidence-resolution 闸（R1）：回查模型引用的 (文件,页,quote) 是否真在本案底稿。

锁定：规范化 / file-level 索引两态解析 / 连续片段匹配 / 三档判定 / 标注降级 /
verdict 一致性回填 / 跨文件不误命中 / 短quote跳过 / 异常兜底 / 开关。
"""

from __future__ import annotations

import pytest

from server.common.evidence_resolution import (
    CorpusIndex,
    existence_ratio,
    normalize_text,
    parse_corpus,
    parse_source,
    resolve_audit_evidence,
)

# ── 底稿样例（两态）────────────────────────────────────────────────────────────

# inline OCR 路径：无 === 外壳，tier 由文件名推断
INLINE_CORPUS = """### 文件: 川姜花苑招标文件.pdf (kind=pdf_text, route=native)
【第 27 页】
第三章 评标办法 综合评估法 满分100分 价格分30分 技术分40分 信用分30分
【第 31 页】
项目负责人需现场答辩，由评标委员会现场打分。

### 文件: 二建投标-技术标.pdf (kind=pdf_text, route=native)
【第 6 页】
我公司承诺严格按照施工组织设计执行，配备塔吊两台、施工电梯一部。
【第 12 页】
拟派项目负责人张三，注册建造师证号 苏12345。
"""

# doc-layer 复用路径：有 === 外壳
DOCLAYER_CORPUS = """=== 招标文件底稿 ===
### 文件: 招标文件.pdf (kind=pdf_text, route=native)
【第 27 页】
评标办法 综合评估法 满分100分。

=== 投标文件（二建）底稿 ===
### 文件: 二建-商务标.pdf (kind=pdf_text, route=native)
【第 6 页】
投标报价人民币捌佰伍拾壹万捌佰捌拾陆元整。
"""


def _audit_result(**overrides) -> dict:
    base = {
        "claim_id": "T-1",
        "verdict": "approved",
        "explanation": "评分完成",
        "reasons": [],
        "policy_refs": ["tender_evalmethod_001"],
        "risk_score": 20,
        "extracted_data": {},
        "evidence_chain": [],
        "reviewed_by": "tender-evaluator",
        "timestamp": "2026-06-22T00:00:00Z",
        "result": True,
        "conclusion": "合规",
    }
    base.update(overrides)
    return base


# ── normalize_text ──────────────────────────────────────────────────────────


def test_normalize_strips_whitespace_punct_and_fullwidth():
    # 全角数字/标点 → 半角；空白/标点全去；大小写归一
    assert normalize_text("ＡＢ 12，３４。【x】") == "ab1234x"


def test_normalize_empty():
    assert normalize_text("") == ""
    assert normalize_text(None) == ""  # type: ignore[arg-type]


# ── parse_corpus 两态 ─────────────────────────────────────────────────────────


def test_parse_inline_tier_from_filename():
    segs = parse_corpus(INLINE_CORPUS)
    tiers = {(s["tier"], s["file"], s["page"]) for s in segs}
    assert ("tender", "川姜花苑招标文件.pdf", 27) in tiers
    assert ("bid", "二建投标-技术标.pdf", 6) in tiers
    assert ("bid", "二建投标-技术标.pdf", 12) in tiers


def test_parse_doclayer_tier_from_marker():
    segs = parse_corpus(DOCLAYER_CORPUS)
    tiers = {(s["tier"], s["page"]) for s in segs}
    assert ("tender", 27) in tiers
    assert ("bid", 6) in tiers


def test_file_meta_stripped_from_name():
    segs = parse_corpus("### 文件: foo.pdf (kind=pdf_text, route=native)\n【第 1 页】\nhello")
    assert segs[0]["file"] == "foo.pdf"


# ── existence_ratio ───────────────────────────────────────────────────────────


def test_existence_verbatim_is_one():
    corpus = normalize_text("配备塔吊两台、施工电梯一部")
    assert existence_ratio(normalize_text("配备塔吊两台施工电梯一部"), corpus) == 1.0


def test_existence_fabricated_near_zero():
    corpus = normalize_text("配备塔吊两台、施工电梯一部")
    r = existence_ratio(normalize_text("我方拥有专利技术五十项并获得国家科技进步奖"), corpus)
    assert r <= 0.30


def test_existence_short_nonverbatim_zero():
    assert existence_ratio("abcd", normalize_text("完全不相关的内容")) == 0.0


# ── parse_source ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "source,tier,page",
    [
        ("投标文件第6页《应答函》", "bid", 6),
        ("招标文件第27页 评标办法", "tender", 27),
        ("某文件无页码", "whole", None),
        ("投标文件第 12 页", "bid", 12),
    ],
)
def test_parse_source(source, tier, page):
    assert parse_source(source) == (tier, page)


# ── 三档判定（端到端 resolve）────────────────────────────────────────────────


def test_verbatim_quote_resolved_not_downgraded():
    out = resolve_audit_evidence(
        _audit_result(
            extracted_data={
                "scoring": [
                    {
                        "item": "技术",
                        "max": 40,
                        "score": 35,
                        "status": "scored",
                        "deduction_hits": [
                            {
                                "deduction_id": "d1",
                                "evidence": {
                                    "source": "投标文件第6页",
                                    "quote": "配备塔吊两台、施工电梯一部",
                                },
                            }
                        ],
                    }
                ]
            }
        ),
        INLINE_CORPUS,
    )
    sitem = out["extracted_data"]["scoring"][0]
    assert sitem["status"] == "scored"  # 未降级
    assert sitem["score"] == 35
    ev = sitem["deduction_hits"][0]["evidence"]
    assert ev["resolution"]["status"] == "resolved"
    assert out["verdict"] == "approved"


def test_fabricated_quote_unresolved_downgrades_and_escalates_verdict(monkeypatch):
    monkeypatch.setenv("EVIDENCE_RESOLUTION_DOWNGRADE", "1")
    out = resolve_audit_evidence(
        _audit_result(
            extracted_data={
                "scoring": [
                    {
                        "item": "技术",
                        "max": 40,
                        "score": 40,
                        "status": "scored",
                        "deduction_hits": [
                            {
                                "deduction_id": "d1",
                                "evidence": {
                                    "source": "投标文件第6页",
                                    "quote": "我方拥有五十项发明专利并通过欧盟CE认证及三千万元质量保证金",
                                },
                            }
                        ],
                    }
                ]
            }
        ),
        INLINE_CORPUS,
    )
    sitem = out["extracted_data"]["scoring"][0]
    assert sitem["status"] == "manual_review"  # unresolved → 降级
    assert sitem["score"] is None
    assert "未在底稿核实" in sitem["basis"]
    # verdict 一致性回填：approved → manual_review + 重派生 result/conclusion
    assert out["verdict"] == "manual_review"
    assert out["manual_review_reason"] == "insufficient_evidence"
    assert out["result"] is False
    assert out["conclusion"] == "待人工复核"
    assert out["extracted_data"]["evidence_resolution"]["unresolved"] == 1
    assert "技术" in out["extracted_data"]["evidence_resolution"]["downgraded_items"]


def test_downgrade_disabled_only_annotates(monkeypatch):
    monkeypatch.setenv("EVIDENCE_RESOLUTION_DOWNGRADE", "0")
    out = resolve_audit_evidence(
        _audit_result(
            extracted_data={
                "scoring": [
                    {
                        "item": "技术",
                        "max": 40,
                        "score": 40,
                        "status": "scored",
                        "deduction_hits": [
                            {
                                "evidence": {
                                    "source": "投标文件第6页",
                                    "quote": "我方拥有五十项发明专利并通过欧盟CE认证及三千万元质量保证金",
                                }
                            }
                        ],
                    }
                ]
            }
        ),
        INLINE_CORPUS,
    )
    sitem = out["extracted_data"]["scoring"][0]
    assert sitem["status"] == "scored"  # 关闭降级 → 不改
    assert out["verdict"] == "approved"
    assert sitem["deduction_hits"][0]["evidence"]["resolution"]["status"] == "unresolved"


def test_paraphrase_weak_match_not_downgraded():
    # 转述（共享部分片段，非逐字）→ weak_match，不降级（宁漏勿误杀）
    corpus = (
        "### 文件: 投标.pdf (kind=pdf_text)\n【第 6 页】\n"
        "我公司承诺严格按照施工组织设计执行配备塔吊两台施工电梯一部并设专职安全员\n"
    )
    out = resolve_audit_evidence(
        _audit_result(
            extracted_data={
                "scoring": [
                    {
                        "item": "技术",
                        "max": 40,
                        "score": 35,
                        "status": "scored",
                        "deduction_hits": [
                            {
                                "evidence": {
                                    "source": "投标文件第6页",
                                    # 一半逐字一半新增 → 介于双阈值之间
                                    "quote": "我公司承诺严格按照施工组织设计执行另投入智能监控平台与无人机巡检系统",
                                }
                            }
                        ],
                    }
                ]
            }
        ),
        corpus,
    )
    sitem = out["extracted_data"]["scoring"][0]
    res = sitem["deduction_hits"][0]["evidence"]["resolution"]["status"]
    assert res == "weak_match"
    assert sitem["status"] == "scored"  # 不降级


# ── 跨文件不误命中（codex P1）─────────────────────────────────────────────────


def test_cross_file_same_page_not_false_positive():
    # quote 真在 A 家第6页；B 家第6页无此文。source 只写"投标文件第6页"。
    # 存在性 resolved（A 家有），page 子状态 file_ambiguous 或 confirmed，绝不因 B 家误判。
    corpus = (
        "=== 投标文件（A）底稿 ===\n### 文件: A-技术标.pdf (kind=pdf_text)\n"
        "【第 6 页】\n甲方专用条款关键词ALPHA独有内容\n"
        "=== 投标文件（B）底稿 ===\n### 文件: B-技术标.pdf (kind=pdf_text)\n"
        "【第 6 页】\n乙方完全不同的内容BETA\n"
    )
    out = resolve_audit_evidence(
        _audit_result(
            extracted_data={
                "scoring": [
                    {
                        "item": "技术",
                        "max": 40,
                        "score": 35,
                        "status": "scored",
                        "deduction_hits": [
                            {
                                "evidence": {
                                    "source": "投标文件第6页",
                                    "quote": "甲方专用条款关键词ALPHA独有内容",
                                }
                            }
                        ],
                    }
                ]
            }
        ),
        corpus,
    )
    ev = out["extracted_data"]["scoring"][0]["deduction_hits"][0]["evidence"]
    assert ev["resolution"]["status"] == "resolved"  # A 家确有 → 不误判 unresolved
    assert out["extracted_data"]["scoring"][0]["status"] == "scored"  # 不降级


# ── 短 quote 跳过 ─────────────────────────────────────────────────────────────


def test_short_quote_skipped():
    out = resolve_audit_evidence(
        _audit_result(
            extracted_data={
                "scoring": [
                    {
                        "item": "技术",
                        "max": 40,
                        "score": 35,
                        "status": "scored",
                        "deduction_hits": [{"evidence": {"source": "投标文件第6页", "quote": "短"}}],
                    }
                ]
            }
        ),
        INLINE_CORPUS,
    )
    sitem = out["extracted_data"]["scoring"][0]
    assert "resolution" not in sitem["deduction_hits"][0]["evidence"]  # 太短跳过未标
    # 有 deduction_hits（仅 quote 太短不可判）→ 非 loc_only，也不降级，保持原状
    assert "resolution" not in sitem
    assert sitem["status"] == "scored"


# ── loc_only（banded/formula 无离散 quote）────────────────────────────────────


def test_banded_item_without_hits_marked_loc_only():
    out = resolve_audit_evidence(
        _audit_result(
            extracted_data={
                "scoring": [
                    {
                        "item": "信用",
                        "max": 30,
                        "score": 21,
                        "status": "scored",
                        "score_mode": "banded",
                        "basis": "良好档，见招标文件第27页",
                    }
                ]
            }
        ),
        INLINE_CORPUS,
    )
    sitem = out["extracted_data"]["scoring"][0]
    assert sitem["resolution"]["status"] == "loc_only"
    assert sitem["status"] == "scored"  # loc_only 绝不降级


# ── 废标依据高危标注（不动 verdict）────────────────────────────────────────────


def test_disqualification_unresolved_high_severity_not_change_verdict():
    out = resolve_audit_evidence(
        _audit_result(
            verdict="rejected",
            policy_refs=["tender_evalmethod_005"],
            result=False,
            conclusion="不合规",
            extracted_data={
                "disqualification_hits": [
                    {
                        "rule_id": "RR1",
                        "finding": "投错标",
                        "evidence": {
                            "source": "招标文件第27页",
                            "quote": "本工程要求投标人具备特级资质且近三年完成十个超高层项目",
                        },
                    }
                ]
            },
        ),
        INLINE_CORPUS,
    )
    assert out["verdict"] == "rejected"  # 不翻盘
    summary = out["extracted_data"]["evidence_resolution"]
    assert len(summary["high_severity_unresolved"]) == 1
    assert summary["high_severity_unresolved"][0]["severity"] == "high"


# ── verdict 已 manual_review 仅补 reason ───────────────────────────────────────


def test_existing_manual_review_only_fills_reason():
    out = resolve_audit_evidence(
        _audit_result(
            verdict="manual_review",
            result=False,
            conclusion="待人工复核",
            extracted_data={
                "scoring": [
                    {
                        "item": "技术",
                        "max": 40,
                        "score": 35,
                        "status": "scored",
                        "deduction_hits": [
                            {
                                "evidence": {
                                    "source": "投标文件第6页",
                                    "quote": "我方拥有五十项发明专利并通过欧盟CE认证及三千万元质量保证金",
                                }
                            }
                        ],
                    }
                ]
            },
        ),
        INLINE_CORPUS,
    )
    assert out["verdict"] == "manual_review"
    assert out["manual_review_reason"] == "insufficient_evidence"


# ── 失败安全 / 开关 / 空底稿 ──────────────────────────────────────────────────


def test_empty_evidence_source_passthrough():
    payload = _audit_result()
    assert resolve_audit_evidence(payload, "") is payload


def test_disabled_gate_passthrough(monkeypatch):
    monkeypatch.setenv("TENDER_EVIDENCE_RESOLUTION", "0")
    payload = _audit_result(
        extracted_data={"scoring": [{"item": "x", "max": 1, "score": 0, "status": "scored"}]}
    )
    out = resolve_audit_evidence(payload, INLINE_CORPUS)
    assert "evidence_resolution" not in out["extracted_data"]


def test_non_dict_output_passthrough():
    assert resolve_audit_evidence(["not", "a", "dict"], INLINE_CORPUS) == ["not", "a", "dict"]


def test_malformed_corpus_does_not_crash():
    # 无锚点的乱底稿 → segments 空 → 原样返回，不崩
    payload = _audit_result()
    out = resolve_audit_evidence(payload, "random text without any anchors at all")
    assert out is payload


def test_corpus_index_corpus_for_fallback():
    idx = CorpusIndex(parse_corpus(INLINE_CORPUS))
    # 缺失 tier → 回落 whole_corpus（非空）
    assert idx.corpus_for("nonexistent") == idx.whole_corpus
    assert idx.whole_corpus


# ── 透传管道集成（apply_schema_semantics 经注册的 resolve hook）──────────────────


def _full_audit_result(**overrides) -> dict:
    """满足 audit-result schema required + additionalProperties:false 的完整结论（过硬校验用）。"""
    base = {
        "claim_id": "T-1",
        "verdict": "approved",
        "explanation": "评分完成",
        "reasons": [],
        "policy_refs": ["tender_evalmethod_001"],
        "risk_score": 20,
        "extracted_data": {
            "scoring": [
                {
                    "item": "技术",
                    "max": 40,
                    "score": 40,
                    "status": "scored",
                    "deduction_hits": [
                        {
                            "evidence": {
                                "source": "投标文件第6页",
                                "quote": "我方拥有五十项发明专利并通过欧盟CE认证及三千万元质量保证金",
                            }
                        }
                    ],
                }
            ]
        },
        "evidence_chain": [],
        "reviewed_by": "tender-evaluator",
        "timestamp": "2026-06-22T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_pipeline_no_evidence_source_skips_resolution(monkeypatch):
    import server.common.output_contracts as oc
    from server.common.contract import DEFAULT_OUTPUT_SCHEMA_NAME, apply_schema_semantics

    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: set())  # 真伪闸跳过
    out = apply_schema_semantics(DEFAULT_OUTPUT_SCHEMA_NAME, _full_audit_result())
    # 未传底稿 → resolve 跳过：无 evidence_resolution、不降级、verdict 不变
    assert "evidence_resolution" not in out["extracted_data"]
    assert out["verdict"] == "approved"


def test_pipeline_with_evidence_source_runs_resolution(monkeypatch):
    import server.common.output_contracts as oc
    from server.common.contract import DEFAULT_OUTPUT_SCHEMA_NAME, apply_schema_semantics

    monkeypatch.setattr(oc, "_load_known_rule_ids", lambda: set())
    monkeypatch.setenv("EVIDENCE_RESOLUTION_DOWNGRADE", "1")
    out = apply_schema_semantics(
        DEFAULT_OUTPUT_SCHEMA_NAME, _full_audit_result(), evidence_source=INLINE_CORPUS
    )
    # 传底稿 → 编造 quote 被回查降级 + verdict 升级 + 摘要写入
    assert out["extracted_data"]["evidence_resolution"]["unresolved"] == 1
    assert out["extracted_data"]["scoring"][0]["status"] == "manual_review"
    assert out["verdict"] == "manual_review"
    assert out["result"] is False


# ══════════════════════════════════════════════════════════════════════════════
# R3: confidence 消费（低置信→manual_review，接 G3）
# ══════════════════════════════════════════════════════════════════════════════

from server.common.evidence_resolution import (  # noqa: E402
    _normalize_filename,
    _parse_file_head,
)

# 含低置信标记的底稿（盖章/扫描件，file_clarity=low；_CLARITY_NOTE 注入头）
LOW_CLARITY_CORPUS = (
    "### 文件: 2.08资格审查资料.pdf (kind=ocr, route=cloud) [检出印章 2 枚] [⚠清晰度低：OCR 部分文本置信度低]\n"
    "【第 5 页】\n营业执照 注册资本 一千万元\n"
    "### 文件: 2.07项目管理机构.pdf (kind=pdf_text, route=native)\n"
    "【第 1 页】\n拟派项目负责人张三\n"
)


def test_parse_file_head_clarity_and_clean_name():
    # critic F1：文件名不被 (kind=)/[检出印章]/[清晰度] 污染
    name, clarity = _parse_file_head("2.08资格审查资料.pdf (kind=ocr, route=cloud) [检出印章 2 枚] [⚠清晰度低：x]")
    assert name == "2.08资格审查资料.pdf"
    assert clarity == "low"
    name2, c2 = _parse_file_head("普通.pdf (kind=pdf_text, route=native)")
    assert name2 == "普通.pdf" and c2 == "clear"
    _, c3 = _parse_file_head("扫描.pdf (kind=ocr) [清晰度未知：无置信度]")
    assert c3 == "unknown"


def test_normalize_filename():
    assert _normalize_filename("/path/To/Ｆile.PDF") == "file.pdf"
    assert _normalize_filename("a\\b\\c.pdf") == "c.pdf"


def test_parse_file_head_keeps_bracket_in_filename():
    # reviewer F2：文件名含普通 [ 不应被当标记切断（只在已知标记 [检出印章/[清晰度 处切）
    name, clarity = _parse_file_head("file[1].pdf (kind=pdf_text, route=native)")
    assert name == "file[1].pdf" and clarity == "clear"
    name2, c2 = _parse_file_head("data[v2].pdf (kind=ocr) [⚠清晰度低：x]")
    assert name2 == "data[v2].pdf" and c2 == "low"


def test_clarity_map_and_low_clarity_files():
    idx = CorpusIndex(parse_corpus(LOW_CLARITY_CORPUS))
    lcf = {f["file"]: f["clarity"] for f in idx.low_clarity_files()}
    assert lcf.get("2.08资格审查资料.pdf") == "low"
    assert "2.07项目管理机构.pdf" not in lcf  # clear 不列


def test_low_clarity_files_emitted_even_without_quotes():
    # codex#1：只有低置信文件、无可回查 quote → 仍 emit low_clarity_files
    out = resolve_audit_evidence(_audit_result(extracted_data={"scoring": []}), LOW_CLARITY_CORPUS)
    er = out["extracted_data"]["evidence_resolution"]
    assert any(f["file"] == "2.08资格审查资料.pdf" for f in er["low_clarity_files"])


def test_g3_score0_on_named_low_clarity_file_downgrades(monkeypatch):
    monkeypatch.setenv("EVIDENCE_RESOLUTION_DOWNGRADE", "1")
    out = resolve_audit_evidence(
        _audit_result(
            extracted_data={
                "scoring": [
                    {
                        "item": "营业执照",
                        "max": 5,
                        "score": 0,
                        "status": "scored",
                        # absence 项把文件写进 basis（点名 low 文件）
                        "basis": "已核投标文件2.08资格审查资料.pdf 未提供营业执照，故0分",
                    }
                ]
            }
        ),
        LOW_CLARITY_CORPUS,
    )
    sitem = out["extracted_data"]["scoring"][0]
    assert sitem["status"] == "manual_review"  # 读不清≠没提供
    assert sitem["score"] is None
    assert "低置信" in sitem["basis"]
    assert out["verdict"] == "manual_review"  # verdict 回填


def test_g3_score_positive_not_downgraded():
    out = resolve_audit_evidence(
        _audit_result(
            extracted_data={
                "scoring": [
                    {
                        "item": "营业执照",
                        "max": 5,
                        "score": 5,
                        "status": "scored",
                        "basis": "投标文件2.08资格审查资料.pdf 已提供营业执照",
                    }
                ]
            }
        ),
        LOW_CLARITY_CORPUS,
    )
    assert out["extracted_data"]["scoring"][0]["status"] == "scored"  # 非0分不降


def test_g3_unnamed_source_not_downgraded():
    # critic F2：source/basis 不点名低置信文件 → 不降级（保守，无误杀）
    out = resolve_audit_evidence(
        _audit_result(
            extracted_data={
                "scoring": [
                    {"item": "营业执照", "max": 5, "score": 0, "status": "scored", "basis": "投标第5页未提供"}
                ]
            }
        ),
        LOW_CLARITY_CORPUS,
    )
    assert out["extracted_data"]["scoring"][0]["status"] == "scored"


def test_g3_unknown_clarity_not_downgraded():
    # critic F3：unknown（云 OCR 常态）只 emit 不降级
    corpus = (
        "### 文件: 扫描件.pdf (kind=ocr) [清晰度未知：无置信度信号]\n【第 1 页】\nx\n"
    )
    out = resolve_audit_evidence(
        _audit_result(
            extracted_data={
                "scoring": [
                    {"item": "X", "max": 5, "score": 0, "status": "scored", "basis": "已核扫描件.pdf未提供"}
                ]
            }
        ),
        corpus,
    )
    assert out["extracted_data"]["scoring"][0]["status"] == "scored"  # unknown 不降
    er = out["extracted_data"]["evidence_resolution"]
    assert any(f["clarity"] == "unknown" for f in er["low_clarity_files"])  # 但 emit 可见


def test_r1_r3_combined_downgrade_idempotent(monkeypatch):
    # codex#3：同项 unresolved(R1) + low_clarity(R3) → 仅降级一次，downgraded_items 不重复
    monkeypatch.setenv("EVIDENCE_RESOLUTION_DOWNGRADE", "1")
    out = resolve_audit_evidence(
        _audit_result(
            extracted_data={
                "scoring": [
                    {
                        "item": "营业执照",
                        "max": 5,
                        "score": 0,
                        "status": "scored",
                        "basis": "投标文件2.08资格审查资料.pdf",
                        "deduction_hits": [
                            {
                                "evidence": {
                                    "source": "2.08资格审查资料.pdf 第5页",
                                    "quote": "完全编造的不存在原文五十项专利三千万保证金欧盟认证",
                                }
                            }
                        ],
                    }
                ]
            }
        ),
        LOW_CLARITY_CORPUS,
    )
    er = out["extracted_data"]["evidence_resolution"]
    sitem = out["extracted_data"]["scoring"][0]
    assert sitem["status"] == "manual_review"
    assert er["downgraded_items"].count("营业执照") == 1  # 不重复
    # reviewer F4：双触发时 R1 与 R3 两条降级原因都在 basis（note 不丢）
    assert "未在底稿核实" in sitem["basis"]  # R1 note
    assert "低置信" in sitem["basis"]  # R3 note
