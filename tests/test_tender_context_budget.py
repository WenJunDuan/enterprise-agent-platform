"""Bug 1（2026-08-14 生产事故）：tender 注入 OCR 底稿必须过字节预算闸。

事故链：云 OCR 写超时 → runner 降级 ``inline_ocr`` → ``ocr_preprocess_block(directory_path)``
把整个 case 目录的 OCR 全文无上限注入 → 内网 DeepSeek Flash ``Prompt is too long``。
闸放在 tender 调用侧（``server/ocr/`` 禁改），两条底稿来源（doc_layer_reuse / inline_ocr）同过。

**2026-08-18 归宿变更**：整份注入路径一旦触发截断即失去评分权威性，runner 改为短路到
``build_manual_review_result``（不发 prompt、不出分），故"截断后的底稿注入给模型"这一形态
不复存在。本文件里原先经 ``run_tender_evaluation`` 断言注入产物的用例，按其**真正的被测
对象**重新落点：算法性质（关键节保留 / UTF-8 边界 / 省略标记 / 预算不越限）落到
``bound_draft`` 这个纯计算上，"哪几条路径受闸约束"落到 runner 的新归宿上。
转人工归宿本身由 ``tests/test_tender_truncation_authority.py`` 守。
"""

from __future__ import annotations

import asyncio
import logging

from server.common.agent_bridge import AgentRunMeta
from server.tender import doc_layer

# 用户可见的截断标记前缀（契约：模型能看见"这里被截了"，评分项据此走证据缺失规则）
TRUNCATION_NOTICE_PREFIX = "【底稿超出上下文预算，已截断"


def _fake_meta(request_id: str) -> AgentRunMeta:
    return AgentRunMeta(
        request_id=request_id,
        conversation_id="conv-test",
        claude_session_id="sess-test",
        resume_session_id=None,
        fork_from_session_id=None,
        schema_name="tender/audit-result.schema.json",
        log_file="logs/test.log",
        result_file="logs/test-result.json",
        result_subtype="success",
        cost_usd=0.0,
        finished_at=None,
    )


def _run_evaluation(monkeypatch, runner, *, request_id: str) -> dict:
    """跑一次评标，返回 run_command_json 实际收到的 kwargs（context / evidence_source）。"""
    calls: dict = {}

    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        calls.update(opts)
        return {"verdict": "manual_review"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(runner, "run_command_json", fake_run_command_json)
    monkeypatch.setattr(runner, "resolve_project_criteria", lambda *_a, **_kw: (None, None))
    asyncio.run(
        runner.run_tender_evaluation(
            request_id=request_id,
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-test",
        )
    )
    return calls


def _run_for_payload(monkeypatch, runner, *, request_id: str) -> dict:
    """跑一次评标并返回**结论**——整份注入被截断后模型不再被调用，故取不到 calls。"""
    sent = {"model": 0}

    async def fake_run_command_json(command_name, *arguments, schema_name, **opts):
        sent["model"] += 1
        return {"verdict": "approved"}, _fake_meta(opts["request_id"])

    monkeypatch.setattr(runner, "run_command_json", fake_run_command_json)
    monkeypatch.setattr(runner, "resolve_project_criteria", lambda *_a, **_kw: (None, None))
    payload, _meta = asyncio.run(
        runner.run_tender_evaluation(
            request_id=request_id,
            tenant="acme",
            directory_path="/fake/dir",
            project_id="tp-test",
        )
    )
    assert sent["model"] == 0, "整份注入被截断时不得把注定证据残缺的 prompt 发出去"
    return payload


def _kept_material(context: str) -> str:
    """取注入上下文里"截断标记之前的底稿本体"（标记自带前导换行，不算底稿内容）。"""
    body = context.split(TRUNCATION_NOTICE_PREFIX)[0]
    return body.split("===\n", maxsplit=1)[1].removesuffix("\n")


def _bounded(draft: str) -> str:
    """取预算闸对 ``draft`` 的实际产物（截断后的底稿 + 截断标记）。

    2026-08-18 后整份注入被截即转人工、不再进 prompt，故算法性质只能在这一层验；
    ``bound_draft`` 正是 runner 调用的同一个纯计算，不是为测试新造的旁路。
    """
    from server.tender.draft_budget import bound_draft

    truncated = bound_draft(draft)
    assert truncated is not None, "前置条件：本用例必须真的触发截断"
    return truncated.text


def _kept_body(bounded: str) -> str:
    """取 ``_bounded`` 产物里截断标记之前的底稿本体。"""
    return bounded.split(TRUNCATION_NOTICE_PREFIX)[0].removesuffix("\n")


def _truncation_account(payload: dict) -> dict:
    """从结论里取截断账目 warning（KD4：三个字节数随结论落盘）。"""
    warnings = payload["extracted_data"]["ocr_warnings"]
    return next(w for w in warnings if w["status"] == "draft_truncated")


def _use_inline_ocr(monkeypatch, runner, text: str) -> None:
    """强制走 inline_ocr 降级路径（事故路径）：doc 层不出底稿。"""
    monkeypatch.setattr(doc_layer, "load_doc_layer_context", lambda *_a, **_kw: None)
    monkeypatch.setattr(doc_layer, "load_doc_layer_context_slim", lambda *_a, **_kw: None)
    monkeypatch.setattr(runner, "ocr_preprocess_block", lambda *a, **kw: text)


def test_over_budget_draft_is_truncated_with_visible_marker(monkeypatch):
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "300")
    # 每个汉字 3 字节：150 字 = 450 字节 > 300 字节上限
    bounded = _bounded("招" * 150)

    assert TRUNCATION_NOTICE_PREFIX in bounded
    kept = _kept_body(bounded)
    assert len(kept.encode("utf-8")) <= 300
    # 保留的是**前** N 字节，不是随机片段
    assert kept == "招" * 100


def test_truncation_cuts_on_utf8_boundary(monkeypatch):
    """上限落在多字节字符中间时不得截出半个字符（截断产物必须严格 UTF-8 可解码）。"""
    # 100 不是 3 的整数倍 → 第 34 个汉字被上限劈开
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "100")

    raw = _kept_body(_bounded("标" * 60)).encode("utf-8")

    # 33 个完整汉字 = 99 字节；第 34 个字被上限劈开，必须整字丢弃而不是留半个
    assert len(raw) == 99
    # 严格解码：出现半个字符会抛 UnicodeDecodeError
    assert raw.decode("utf-8") == "标" * 33


def test_truncation_emits_structured_warning_log(monkeypatch, caplog):
    from server.tender import runner

    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "300")
    _use_inline_ocr(monkeypatch, runner, "招" * 150)

    with caplog.at_level(logging.WARNING, logger="server.tender.runner"):
        _run_evaluation(monkeypatch, runner, request_id="rid-budget-log")

    records = [r for r in caplog.records if r.getMessage() == "tender_context_truncated"]
    assert len(records) == 1
    record = records[0]
    assert record.request_id == "rid-budget-log"
    assert record.original_bytes == 450
    assert record.kept_bytes == 300
    assert record.limit_bytes == 300


def test_doc_layer_reuse_path_is_also_gated(monkeypatch):
    """预热底稿理论上也可能超大 → 复用路径同样受闸约束（归宿现为转人工）。"""
    from server.tender import runner

    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "300")
    monkeypatch.setattr(doc_layer, "load_doc_layer_context", lambda *_a, **_kw: "标" * 150)
    monkeypatch.setattr(doc_layer, "load_doc_layer_context_slim", lambda *_a, **_kw: "标" * 150)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("doc 层已出底稿时不应回落 inline OCR")

    monkeypatch.setattr(runner, "ocr_preprocess_block", fail_if_called)

    payload = _run_for_payload(monkeypatch, runner, request_id="rid-budget-doc-layer")

    assert payload["verdict"] == "manual_review"
    assert _truncation_account(payload)["original_bytes"] == 450


def test_evidence_source_matches_the_injected_block(monkeypatch):
    """evidence_source 与模型看到的底稿必须同源，否则出处回查会指向未注入内容。

    截断那一档现在由**不再发 prompt** 兜底（见 ``test_tender_truncation_authority.py``）：
    被截底稿根本不会成为任何结论的出处。此处守的是仍会注入的那一档。
    """
    from server.tender import runner

    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "300")
    _use_inline_ocr(monkeypatch, runner, "招" * 50)

    calls = _run_evaluation(monkeypatch, runner, request_id="rid-budget-evidence")

    assert calls["evidence_source"] in calls["context"]


def test_under_budget_block_is_passed_through_unchanged(monkeypatch, caplog):
    """对照：不超限时零改动、零日志。"""
    from server.tender import runner

    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "300")
    _use_inline_ocr(monkeypatch, runner, "招" * 50)

    with caplog.at_level(logging.WARNING, logger="server.tender.runner"):
        calls = _run_evaluation(monkeypatch, runner, request_id="rid-budget-fits")

    assert calls["evidence_source"] == "招" * 50
    assert TRUNCATION_NOTICE_PREFIX not in calls["context"]
    assert not [r for r in caplog.records if r.getMessage() == "tender_context_truncated"]


def test_default_budget_bounds_a_whole_directory_dump(monkeypatch):
    """未配 env 时默认值生效——事故当天正是"没人配上限"。"""
    from server.tender import runner

    monkeypatch.delenv("TENDER_CONTEXT_MAX_BYTES", raising=False)
    monkeypatch.delenv("MODEL_CONTEXT_WINDOW", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", raising=False)
    _use_inline_ocr(monkeypatch, runner, "招" * 400_000)  # 1.2 MB 整目录全文

    account = _truncation_account(
        _run_for_payload(monkeypatch, runner, request_id="rid-budget-default")
    )

    assert account["original_bytes"] == 1_200_000
    assert account["limit_bytes"] < 1_200_000, "默认上限必须真的生效"


# ── Bug A（2026-08-14 P0）：预算闸默认值错 + 盲截砍掉评分标准 ──────────────────
#
# 现场：``tender_context_truncated original_bytes=103335 kept_bytes=63999 limit_bytes=64000``。
# 部署实态 MODEL_CONTEXT_WINDOW=1048576（1M 窗口），旧默认 64,000 B ≈ 2 万 token 只占窗口 2%；
# 且 ``_bound_ocr_block`` 保留前 N 字节盲截，把总在后部章节的「第四章 评审方法和程序」整章砍掉
# → 模型反复 Read 原文件找评分标准 → 耗尽 30 轮 → error_max_turns → 整单无结论。

_FILLER_LINE = "本项目采用公开招标方式，投标人须知前附表内容详见下文说明。"
_QUALIFICATION_LINE = "投标人须具备市政公用工程施工总承包二级及以上资质。"
_SCORING_LINE = "商务部分：每提供1个类似业绩得2分，最多10分。"
_REVIEW_CHAPTER_TITLE = "第四章 评审方法和程序"


def _draft_with_tail_review_chapter(*, filler_lines: int) -> str:
    """构造「关键节在文件后半、总长可超预算」的底稿（真实标书的典型排布）。"""
    head = [
        "### 文件: 招标文件.pdf (kind=ocr, route=ocr)",
        "【第 1 页】",
        "第一章 投标邀请",
        *([_FILLER_LINE] * filler_lines),
        "【第 80 页】",
    ]
    tail = [
        _REVIEW_CHAPTER_TITLE,
        "一、资格审查",
        _QUALIFICATION_LINE,
        "二、评分标准",
        _SCORING_LINE,
    ]
    return "\n".join(head + tail)


def test_review_chapter_in_document_tail_survives_the_budget_gate(monkeypatch):
    """核心红：关键节（评审方法/资格审查/评分标准）在预算内时必须被保留，不得盲截丢弃。"""
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "4000")
    draft = _draft_with_tail_review_chapter(filler_lines=200)
    assert len(draft.encode("utf-8")) > 4000

    bounded = _bounded(draft)

    assert TRUNCATION_NOTICE_PREFIX in bounded
    assert _REVIEW_CHAPTER_TITLE in bounded
    assert _QUALIFICATION_LINE in bounded
    assert _SCORING_LINE in bounded


def test_content_first_truncation_marks_the_omitted_regions(monkeypatch):
    """AC②：被省略的区段在正文里有可见标记，读者能看出"哪一段没给"。"""
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "4000")

    assert "已省略" in _bounded(_draft_with_tail_review_chapter(filler_lines=200))


def test_content_first_truncation_respects_budget_and_stays_utf8(monkeypatch):
    """AC①③：内容优先不等于放弃预算；产物必须严格 UTF-8 可解码。"""
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "4000")

    raw = _kept_body(_bounded(_draft_with_tail_review_chapter(filler_lines=200))).encode("utf-8")

    assert len(raw) <= 4000
    # 严格解码：出现半个字符会抛 UnicodeDecodeError
    raw.decode("utf-8")


def test_production_incident_draft_fits_the_deployed_million_token_window(monkeypatch):
    """默认预算按模型窗口推导：1M 窗口部署下，事故当天 103 KB 底稿根本不该被截。"""
    from server.tender import runner

    monkeypatch.delenv("TENDER_CONTEXT_MAX_BYTES", raising=False)
    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "1048576")
    monkeypatch.setenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "32000")
    draft = _draft_with_tail_review_chapter(filler_lines=1400)
    assert len(draft.encode("utf-8")) > 103_335
    _use_inline_ocr(monkeypatch, runner, draft)

    context = _run_evaluation(monkeypatch, runner, request_id="rid-1m-window")["context"]

    assert TRUNCATION_NOTICE_PREFIX not in context


def test_default_budget_no_longer_scales_with_the_model_context_window(monkeypatch):
    """AC6（2026-08-15 改写）：预算脱钩 ``MODEL_CONTEXT_WINDOW``。

    本测试原先断言 ``wide > 2_000_000``——那正是 08-14 第二次事故的成因：部署声明 1M 窗口
    → 推出 2.1MB 预算 → 闸形同虚设，而 bundled CLI 约 200K token 就一次性硬拒。模型能力
    不描述 CLI 行为，故预算改由实测标定的 TENDER_EFFECTIVE_CONTEXT_TOKENS 单点决定。
    """
    from server.tender import context_budget

    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "1048576")
    monkeypatch.setenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "32000")
    wide = context_budget.derive_default_max_bytes()

    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "65536")
    monkeypatch.setenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "8000")
    narrow = context_budget.derive_default_max_bytes()

    assert wide == narrow, "预算不得再随模型窗口漂移"
    assert wide < 2_000_000, "2.1MB 那档预算等于没有闸"


def test_default_budget_follows_the_calibrated_token_ceiling(monkeypatch):
    """标定值变了预算才变——这是唯一允许的调节旋钮。

    F2：预算是**扣掉脚手架与循环余量之后**的余额（400000-90000-100000=210000 token
    → 630,000 B），不是整个窗口。整窗口那种算法加上 90K 脚手架必然爆窗。
    """
    from server.tender import context_budget

    monkeypatch.setenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", "400000")
    monkeypatch.setenv("TENDER_SCAFFOLD_RESERVE_TOKENS", "90000")
    assert context_budget.derive_default_max_bytes() == 630_000


def test_default_budget_never_loosens_past_the_pre_refactor_gate(monkeypatch):
    """F2 回归闸：口径单点化**不得把闸放松**。

    本测试原先断言 ``>= 256_000``——那是收编前的硬编码默认值，把它当下界等于允许闸越收越
    松；pass1 正是在这条掩护下把回落上限做成了 600,000 B（比收编前松 2.3 倍），大单回落
    必撞 CLI 硬拒。默认标定下回落额度只能比它更紧。
    """
    from server.tender import context_budget

    monkeypatch.delenv("TENDER_EFFECTIVE_CONTEXT_TOKENS", raising=False)
    monkeypatch.delenv("TENDER_SCAFFOLD_RESERVE_TOKENS", raising=False)

    assert context_budget.derive_default_max_bytes() < 256_000


def test_explicit_env_override_still_wins_over_the_derived_default(monkeypatch):
    """保留现有覆盖语义：显式设 TENDER_CONTEXT_MAX_BYTES 时以其为准。"""
    from server.tender import runner

    monkeypatch.setenv("MODEL_CONTEXT_WINDOW", "1048576")
    monkeypatch.setenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "32000")
    monkeypatch.setenv("TENDER_CONTEXT_MAX_BYTES", "5000")

    assert runner._context_max_bytes() == 5000


def test_review_keywords_cover_the_incident_chapter_title():
    """事故章节标题是「评审方法和程序」——旧关键词表只有「评审办法」，抓不住它。"""
    from server.tender.context_budget import KEY_SECTION_KEYWORDS

    assert any(keyword in _REVIEW_CHAPTER_TITLE for keyword in KEY_SECTION_KEYWORDS)


def test_select_review_spans_covers_the_whole_matched_chapter():
    """章节级选区：命中标题后整章（含其下子节）都算关键节，不是只留标题行。"""
    from server.tender.context_budget import select_review_spans

    lines = [
        "第一章 投标邀请",
        "无关正文",
        _REVIEW_CHAPTER_TITLE,
        "一、资格审查",
        _QUALIFICATION_LINE,
        "第五章 合同条款",
        "合同正文",
    ]

    assert select_review_spans(lines) == [(2, 5)]


# ── 2026-08-15 事故：规则源文件被证据材料挤掉 ──────────────────────────────────


def _multi_file_draft(bid_bulk_lines: int) -> list[str]:
    """构造「投标材料在前且体量远大、招标文件在后」的多文件底稿——事故的真实形态。"""
    bid = ["### 文件: 某公司投标文件.PDF"]
    # 投标材料通篇是"投标/技术参数"等词，关键词命中密度高，最易吃光预算。
    bid += [f"投标人技术参数指标响应第 {i} 条，完全满足招标文件要求。" for i in range(bid_bulk_lines)]
    tender = [
        "### 文件: 某项目公开招标文件.doc",
        "第一章 投标邀请",
        "招标人：某某单位。",
        _REVIEW_CHAPTER_TITLE,
        "一、资格审查",
        _QUALIFICATION_LINE,
        "二、评分标准：技术方案 40 分，报价 30 分。",
    ]
    return bid + tender


def test_rule_source_file_is_detected_by_content_not_filename():
    """规则源文件按「是否含关键评审章节」判定，不依赖文件名（各家命名千差万别）。"""
    from server.tender.context_budget import rule_source_spans

    lines = _multi_file_draft(bid_bulk_lines=5)
    spans = rule_source_spans(lines)

    assert len(spans) == 1, "只有含评审章节的那份文件是规则源"
    start, end = spans[0]
    assert lines[start].startswith("### 文件: 某项目公开招标文件")
    assert end == len(lines)


def test_rule_source_survives_when_evidence_would_eat_the_whole_budget():
    """事故回归：投标材料体量压倒时，招标文件（评分标准）必须仍在底稿里。

    修复前按文档顺序分配，前置的大体量投标材料吃光额度 → 招标文件整份被删
    （实测 784KB→136KB，截后只剩投标文件）→ 模型无评分标准，只能判
    insufficient_evidence。
    """
    from server.tender.context_budget import bound_draft_by_content

    lines = _multi_file_draft(bid_bulk_lines=400)
    draft = "\n".join(lines)
    limit = 4000
    assert len(draft.encode("utf-8")) > limit * 3, "前置条件：底稿必须远超预算才有意义"

    kept = bound_draft_by_content(draft, limit_bytes=limit)

    assert len(kept.encode("utf-8")) <= limit
    assert _REVIEW_CHAPTER_TITLE in kept, "评审章节标题必须保留"
    assert "评分标准：技术方案 40 分" in kept, "评分标准正文必须保留，否则整单无法评分"
    assert _QUALIFICATION_LINE in kept, "资格审查条款必须保留"
    assert "某项目公开招标文件" in kept, "规则源文件的文件头必须保留，模型据此定位出处"


# ── 2026-08-17 用户实测：省略标记谎报整份 ──────────────────────────────────────


def test_omission_marker_reports_only_the_dropped_part_not_the_whole_chunk():
    """标记只能描述**真正丢掉的那一段**，不能报整个 chunk 的页码与字节。

    事故：标记写「已省略原第 1-400 页约 681709 字节」，而模型手里同时看得见第 101-158 页，
    推理卡在"这怎么对得上"（用户贴回的模型原话）。根因是标记用整个 chunk 的 _page_note 与
    全长 size 渲染，但截断只丢尾部、头部是保留的。
    """
    from server.tender.context_budget import bound_draft_by_content

    # 需含关键评审章节，否则走的是"无关键节→保留开头"的回落分支，不经过省略标记路径。
    lines = ["### 文件: 某招标文件.pdf", _REVIEW_CHAPTER_TITLE, "评分标准：技术方案 40 分。"]
    for page in range(1, 41):
        lines.append(f"【第{page}页】")
        lines.append(f"第 {page} 页正文内容，" + "投标材料明细。" * 20)
    draft = "\n".join(lines)

    kept = bound_draft_by_content(draft, limit_bytes=4000)

    assert "第 1 页正文内容" in kept, "前置内容应被保留（截断只丢尾部）"
    assert "已省略" in kept, "前置条件：本用例必须真的触发截断"
    # 标记里的页码范围必须落在被丢弃的尾部，不能从第 1 页起算。
    assert "原第 1-" not in kept, "标记谎报：把保留下来的页也算进了省略范围"
