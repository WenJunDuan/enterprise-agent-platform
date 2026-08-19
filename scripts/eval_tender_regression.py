#!/usr/bin/env python3
"""评标回归闸（Phase 0 "先造尺子"）：对一个金标准 case 端到端跑评标，出四指标。

    uv run python scripts/eval_tender_regression.py --case case-zj-live \\
        --backend http://127.0.0.1:9999 [--mode single] [--repeat 3]
    uv run python scripts/eval_tender_regression.py --case case-zj-live --dry-run

**为什么走 HTTP 而不是 import ``server.tender``**：评测对象是端到端行为（准入闸、上传
即 OCR、criteria 预抽、软超时都在这层），绕过 HTTP 就测不到它们。故本脚本只认
``/tender/*`` 公开接口，可连同 ``eval/regression.py`` 一起拷到部署机跑。

**判定逻辑不在本文件**：YAML 子集解析、case 校验、语料指纹定位、四指标计算与报告渲染
在 ``eval/regression.py``（纯逻辑，可脱离服务端单测）；本文件只留 CLI 与 HTTP 驱动，
并逐名 re-export 那些符号，既有 ``scripts.eval_tender_regression.X`` 引用点不变。

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

纠偏令 v2.1 五节的度量修正（报告新增列，判定逻辑与期望值一字未改）：

==========================  ==================================================
客观分·真漏                 结论里没有同满分值的项，或有该项却 ``score=null``。
                            这是**链路债**
客观分·匹配器未匹配         关键词族没命中、但结论里有同满分值的项 = 项名漂移。
                            这是**度量债**，先扩 item_class 同义词族再读数，否则
                            会把度量债当链路债去修（v2.1 五节点名的坑）
补证工具调用数              任务记录的 ``tool_call_count``。**服务端今天不发这个
                            信号**，故恒显示 ``n/a``——n/a ≠ 0，把"没接信号"读成
                            "没调用"会直接把实验判成模型空转
结论字节数                  结论体规范化序列化后的 UTF-8 字节数。连续两轮越过
                            ``CONCLUSION_SIZE_REVIEW_THRESHOLD`` 触发 P0.6 复议
                            （v2.1 三节；原文以「字」计，报告脚注写明单位差异）
归因二分表                  每条缺陷 / 每个客观分项标注 v2.1 二节的列A（文本可达）
                            或列B（像素必需），来自 ``expected.yaml`` 的可选字段
                            ``attribution: text|pixel``。列B 在 vision-page 上线
                            前不变不计失败——跨列记账会把结论读反
==========================  ==================================================

退出码：0 通过 / 1 运行期失败 / 2 case 定义错误 / 3 语料缺席（SKIP）/ 4 语料指纹不符。

**本脚本不内置任何项目的评分项与缺陷**：它们随标书而异，写死等于把一次测试当产品配置
（沿用 ``scripts/measure_tender_evidence.py`` 立下的规矩）。要测哪个 case 就写哪个
``eval/golden/<case>/``。

YAML 子集自解析的由来：仓库基础依赖里没有 PyYAML（venv 里也没有），Phase 0 又不准引新
依赖。故在 ``eval/regression.py`` 内置一个只认「映射 / 缩进序列 / 流式列表 / 标量 /
注释」的解析器，**认不出的语法一律报错**——静默误解析一条 anchors 等于静默改判据。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
# 判定逻辑下沉成包 ``eval.regression`` 后，直跑（``python scripts/…``）时 sys.path[0] 是
# scripts/，须先把仓库根放进去才导得到（同 scripts/smoke_document_formats.py 的既有做法）；
# 导入必须排在这之后，故就地豁免 E402。
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.regression import (  # noqa: E402
    ARTIFACT_CONVERTED,
    ARTIFACT_ORIGINAL,
    ATTRIBUTION_PIXEL,
    ATTRIBUTION_TEXT,
    CONCLUSION_SIZE_REVIEW_THRESHOLD,
    CORRECT_PENDING_REASONS,
    DEFAULT_CORPUS_ROOT,
    EXIT_CASE_INVALID,
    EXIT_CORPUS_ABSENT,
    EXIT_CORPUS_MISMATCH,
    EXIT_OK,
    EXIT_RUN_FAILED,
    MAX_ANCHOR_RANGE_PAGES,
    TOOL_CALL_FIELD,
    Aggregate,
    CaseDefinitionError,
    ConclusionSize,
    CorpusFile,
    CorpusResolution,
    Defect,
    DefectRecall,
    Finding,
    GoldenCase,
    ObjectiveOutcome,
    ObjectiveScore,
    PageRef,
    PendingOutcome,
    PriceCheck,
    RunMetrics,
    YamlSubsetError,
    aggregate,
    check_case,
    check_price,
    conclusion_size,
    count_evidence_tool_calls,
    count_pending,
    evaluate_result,
    extract_page_refs,
    iter_findings,
    load_case,
    match_defects,
    match_objective_scores,
    parse_yaml,
    render_report,
    resolve_corpus,
    wall_clock_seconds,
)

# 下半张表是**逐名 re-export**：这些符号拆分前定义在本文件，既有引用点按
# ``scripts.eval_tender_regression.X`` 取用（含 tests/），拆分不得改变其可达性。
# 用 ``__all__`` 而非 ``X as X`` 标记 re-export：两者对类型检查器等价，但后者会被
# isort（combine-as-imports 默认关）拆成 25 条 import 语句（同 server/core.py 的做法）。
__all__ = [
    # CLI 与 HTTP 驱动（本文件定义）
    "HTTP_TIMEOUT_SEC",
    "REPO_ROOT",
    "TenderBackend",
    "main",
    "run_case",
    "wait_for",
    # 判定逻辑（定义在 eval/regression.py）
    "ARTIFACT_CONVERTED",
    "ARTIFACT_ORIGINAL",
    "ATTRIBUTION_PIXEL",
    "ATTRIBUTION_TEXT",
    "CONCLUSION_SIZE_REVIEW_THRESHOLD",
    "CORRECT_PENDING_REASONS",
    "DEFAULT_CORPUS_ROOT",
    "EXIT_CASE_INVALID",
    "EXIT_CORPUS_ABSENT",
    "EXIT_CORPUS_MISMATCH",
    "EXIT_OK",
    "EXIT_RUN_FAILED",
    "MAX_ANCHOR_RANGE_PAGES",
    "TOOL_CALL_FIELD",
    "Aggregate",
    "CaseDefinitionError",
    "ConclusionSize",
    "CorpusFile",
    "CorpusResolution",
    "Defect",
    "DefectRecall",
    "Finding",
    "GoldenCase",
    "ObjectiveOutcome",
    "ObjectiveScore",
    "PageRef",
    "PendingOutcome",
    "PriceCheck",
    "RunMetrics",
    "YamlSubsetError",
    "aggregate",
    "check_case",
    "check_price",
    "conclusion_size",
    "count_evidence_tool_calls",
    "count_pending",
    "evaluate_result",
    "extract_page_refs",
    "iter_findings",
    "load_case",
    "match_defects",
    "match_objective_scores",
    "parse_yaml",
    "render_report",
    "resolve_corpus",
    "wall_clock_seconds",
]


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
