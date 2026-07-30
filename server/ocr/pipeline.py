"""编排：目录 → 每文件分类 → 直读/OCR → 组装内联"识别底稿"。不调模型。

这是确定性流水线的单一入口，被 `server.ocr.runner`（进程内）与 `python -m server.ocr`
（交互式）共用。每个文件独立 try，一个文件失败不拖垮整批（标 manual + error）。
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from server.ocr import OcrDependencyError, OcrError
from server.ocr import boq as boq_extract
from server.ocr import cache as ocr_cache
from server.ocr.classify import classify
from server.ocr.engine import extract_pdf_subset, recognize, recognize_seal
from server.ocr.office_convert import convert_office_to_pdf
from server.ocr.native import native_read

logger = logging.getLogger(__name__)

# 单文件底稿截断上限，防超大扫描件撑爆映射 prompt。默认 600000：评标标书动辄数百页（张謇 400 页
# 投标底稿 ~215k，旧 200000 恰好截掉尾 ~15k——而那正是模型引用的证据所在，致 evidence 回查
# unresolved 偏高；提到 600k 后实测回查率 71%→92%、unresolved 8→1，见
# sprints/2026-06-23-tender-ui-scoring-fixes/findings.md）。大上下文模型（如 deepseek [1M]）可吃下；
# 本机/小上下文模型经 env OCR_MAX_FILE_BLOCK_CHARS 调小。
MAX_FILE_BLOCK_CHARS = int(os.getenv("OCR_MAX_FILE_BLOCK_CHARS", "600000"))

# P2 置信度门控：OCR 逐块 score 低于此阈值 → 文件标 low（依赖字段须人工复核）。可经 env 调。
OCR_CLARITY_MIN_CONFIDENCE = float(os.getenv("OCR_CLARITY_MIN_CONFIDENCE", "0.6"))

# 低置信/未知清晰度的底稿提示——把"识别不清晰"从事后靠模型猜变成事前显式标注。
_CLARITY_NOTE = {
    "low": " [⚠清晰度低：OCR 部分文本置信度低，依赖本文件的关键字段(金额/日期/单位)请标 needs_review]",
    "unknown": " [清晰度未知：本文件经图像 OCR 但无逐块置信度信号，关键字段请人工抽查]",
}

# P4：是否对 case 目录做确定性 OCR 预处理后注入模型上下文（=0 关闭，回落模型自己 Read）。
OCR_PREPROCESS = os.getenv("OCR_PREPROCESS", "1").lower() in {"1", "true", "yes"}

# PPTX with embedded pictures and less native text than this is treated as scan-heavy. A deck
# without pictures stays native regardless of length; a deck at/above the threshold also stays
# native, avoiding a LibreOffice/OCR tax for ordinary text/table presentations with logos.
PRESENTATION_NATIVE_MIN_TEXT_CHARS = 80


def _env_int(name: str, default: int) -> int:
    """防御解析整数 env：非法值（typo / 非数字）回退默认。模块级常量绝不能因坏 env 抛
    ValueError——否则 `import server.ocr.pipeline` 失败会拖垮整个服务启动，而非只影响 OCR。"""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    """防御解析浮点 env：非法值回退默认（理由同 _env_int）。"""
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# 混合 PDF（数字页 + 扫描页）子集云 OCR 的触发阈值。背景：classify 以文件级 fonts>0 判 native，
# 整份 PDF 只要有文本层就全判 native，其中扫描页经 pymupdf get_text 抽出空串被静默丢失（张謇
# 400 页投标含 ~59 页扫描资质/业绩/职称证书 → 底稿缺据 → 技术/业绩/负责人评分只能 manual）。
# 触发判据 = 计数为主 + 比例兜底：空白页**数量** ≥ MIN_COUNT（59 页绝对量是强信号，不该被
# 341 数字页稀释成 ratio 0.147），或空白**比例** > RATIO（兜底小份多扫描件，如 6 页 4 扫 ratio
# 0.67 但 count 4<10）。仅对 classify 判定的 mixed_pdf 生效（纯数字 PDF 的空白页是真空页，无
# 扫描内容可补）。两阈值均 env 可灰度。详见 .ai_state/sprints/2026-06-23-tender-ui-scoring-fixes/
# per-page-ocr-plan.md「决策修正」。
MAX_BLANK_CHARS = _env_int("OCR_BLANK_PAGE_MIN_CHARS", 20)
OCR_BLANK_PAGE_MIN_COUNT = _env_int("OCR_BLANK_PAGE_MIN_COUNT", 10)
OCR_BLANK_PAGE_RATIO = _env_float("OCR_BLANK_PAGE_RATIO", 0.5)


# OCR 文件级并行度：标书常十几个文件，扫描件走云 OCR 是 job-poll（IO 等待为主），串行会数分钟
# 甚至撞 TENDER_TIMEOUT_SEC；多文件并行把墙钟从"求和"压到"最慢单个"。数字 PDF 走 native 本就快。
# 受云服务并发上限约束，默认 4 保守（防触发云限流）；高并发云 / 全本地可经 env 调大。
def _ocr_max_workers() -> int:
    """防御解析 OCR_MAX_WORKERS：非法值回退默认、clamp ≥1（防 0/负数破坏 ThreadPoolExecutor，codex P2-5）。

    R4-B 提速：默认 4→6（一份文档多文件并行 OCR 把墙钟压到"最慢单个"）。env OCR_MAX_WORKERS 可调。
    """
    try:
        value = int(os.getenv("OCR_MAX_WORKERS", "6"))
    except (TypeError, ValueError):
        return 6
    return max(1, value)


OCR_MAX_WORKERS = _ocr_max_workers()


# D9 streaming-ocr T2/T3: canonical sidecar filename — single source of truth so the job
# worker (writer) and jobs GET route (reader) agree with the exclusion list below without
# each re-hardcoding the literal string (DRY).
OCR_JOB_UNITS_FILENAME = "units.jsonl"

# P1-4: sidecar files written by materialize_upload_submission must not be OCR-processed.
# audit-request.json is a metadata sidecar written into every submission dir — it is not
# a user document and must be excluded to avoid polluting the extraction block.
# units.jsonl (D9 streaming-ocr G1): per-job partial-results sidecar appended by the OCR job
# worker into the same case_dir _iter_files rglobs (T3). Same failure mode as audit-request.json
# — without exclusion a job retry / `/ocr/extract` directory-mode rerun over that dir would
# classify→read_text the sidecar as a regular file and pollute the extraction block/unit count.
_OCR_EXCLUDED_FILENAMES: frozenset[str] = frozenset({"audit-request.json", OCR_JOB_UNITS_FILENAME})


def _iter_files(case_dir: str) -> list[Path]:
    base = Path(case_dir)
    if not base.is_dir():
        return []
    base_resolved = base.resolve()
    files: list[Path] = []
    for p in sorted(base.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue  # 安全：跳过符号链接，防经 symlink 读取 case 目录外的文件
        if p.name in _OCR_EXCLUDED_FILENAMES:
            continue  # P1-4: skip sidecar metadata files
        try:
            p.resolve().relative_to(base_resolved)  # resolved 必须仍在 base 内
        except ValueError:
            continue
        files.append(p)
    return files


def count_pending_files(case_dir: str) -> int:
    """待处理文件数（排除 units.jsonl/audit-request.json 等 sidecar）。

    供 job worker（D9 streaming-ocr T3）在启动时预估 ``total`` 单元数：每个文件至少触发一次
    单元事件（``extract_one`` / ``_extract_one_raw`` 的"至少一次"契约），故文件数是 total_units
    的一个下界估计（页级文件会触发更多单元，属"预估"而非精确值，见 design.md T2/T3 验收）。
    """
    return len(_iter_files(case_dir))


# D9 streaming-ocr T1：单元事件回调。unit 形如 {"file", "page", "status", "payload",
# "from_cache"}（page=None 表文件级单元）。默认 None＝现行为逐字节不变。
UnitCallback = Callable[[dict], None]
_PageCallback = Callable[[int, dict], None]


def _make_unit(*, file: str, page: int | None, status: str, payload: dict, from_cache: bool) -> dict:
    """组装单元事件 dict（页级/文件级统一 schema，见 design.md 单元事件回调签名）。"""
    return {"file": file, "page": page, "status": status, "payload": payload, "from_cache": from_cache}


def _call_native_read(path: Path, on_page: _PageCallback | None) -> dict:
    """调 ``native_read``，``on_page=None`` 时按原始（无 on_page 形参）签名调用。

    保持默认路径调用字节不变（T1 硬约束）：既是行为契约，也让存量测试里把 ``native_read``
    monkeypatch 成旧签名（如 ``lambda path: {...}``）的 mock 无需改动即可继续通过。
    """
    if on_page is None:
        return native_read(path)
    return native_read(path, on_page=on_page)


def _call_recognize(path: Path, *, purpose: str | None, on_page: _PageCallback | None) -> dict:
    """调 ``recognize``，理由同 ``_call_native_read``（存量 mock 兼容）。"""
    if on_page is None:
        return recognize(path, purpose=purpose)
    return recognize(path, purpose=purpose, on_page=on_page)


def _recognize_with_seal(
    path: Path,
    route: dict,
    *,
    run_seal: bool,
    purpose: str | None = None,
    on_page: _PageCallback | None = None,
) -> dict:
    """走 OCR 引擎识别（可选印章），合并分诊信息。purpose 透传给 OCR 引擎做场景化识别。"""
    result = {**route, **_call_recognize(path, purpose=purpose, on_page=on_page)}
    if run_seal:
        result["seals"] = recognize_seal(path).get("seals", [])
    return result


def _call_recognize_with_seal(
    path: Path,
    route: dict,
    *,
    run_seal: bool,
    purpose: str | None,
    on_page: _PageCallback | None,
) -> dict:
    """调 ``_recognize_with_seal``，``on_page=None`` 时按原始签名调用（存量 mock 兼容，理由同
    ``_call_native_read``——测试里整体 monkeypatch ``_recognize_with_seal`` 为旧签名的场景）。
    """
    if on_page is None:
        return _recognize_with_seal(path, route, run_seal=run_seal, purpose=purpose)
    return _recognize_with_seal(path, route, run_seal=run_seal, purpose=purpose, on_page=on_page)


def _has_extractable_text(native: dict) -> bool:
    """native 直读是否抽到非空文本（blocks 或 tables 任一有内容）。"""
    if any(block.strip() for block in native.get("blocks", [])):
        return True
    return any(
        any(str(cell).strip() for cell in row)
        for table in native.get("tables", [])
        for row in table.get("rows", [])
    )


def _presentation_needs_ocr(native: dict) -> bool:
    """True for scan-heavy PPTX: at least one picture and insufficient native text."""
    image_count = native.get("image_count", 0)
    text_char_count = native.get("text_char_count", 0)
    return (
        isinstance(image_count, int)
        and not isinstance(image_count, bool)
        and image_count > 0
        and isinstance(text_char_count, int)
        and not isinstance(text_char_count, bool)
        and text_char_count < PRESENTATION_NATIVE_MIN_TEXT_CHARS
    )


def _blank_page_count(blocks: list[str]) -> int:
    """统计近空白页数。pdf_text 的 blocks 一页一项（read_pdf_text 逐页 append），扫描页经
    pymupdf get_text 抽出空串/极短文本 → 视为空白页（< MAX_BLANK_CHARS 个非空白字符）。"""
    return sum(1 for block in blocks if len(str(block).strip()) < MAX_BLANK_CHARS)


def _should_cloud_ocr_mixed_pdf(blocks: list[str]) -> bool:
    """混合 PDF 是否整份转云 OCR：空白页数 ≥ MIN_COUNT（主信号）OR 空白比例 > RATIO（兜底）。

    计数为主——绝对扫描页量是强信号，不该被大量数字页稀释成低比例；比例兜底小份多扫描件
    （如 6 页 4 扫，count<阈值但 ratio 高）。仅应对 classify 判定的 mixed_pdf 调用（纯数字 PDF
    的空白页是真空页，无扫描内容可补，触发只会白送云 OCR）。
    """
    total = len(blocks)
    if total == 0:
        return False
    blank = _blank_page_count(blocks)
    return blank >= OCR_BLANK_PAGE_MIN_COUNT or (blank / total) > OCR_BLANK_PAGE_RATIO


def _augment_mixed_pdf_blocks(
    path: Path, route: dict, native: dict, *, purpose: str | None
) -> dict | None:
    """混合 PDF 子集 OCR：只对扫描(空白)页做云 OCR 并回填进 native blocks，数字页保原生直读。

    比"整份转云 OCR"更优——避免用云 OCR 覆盖 341 数字页的原生高保真文本（OCR 反而引误差），
    且只送扫描页（更省）、单 job（更快）、复用已验证的云文件提交路径（无新接口）。回填后页号仍
    取真实页（blocks 一页一项 → _render_body 按真实页打锚点），evidence 回查【第N页】不失准。

    返回 None → 调用方回退整份云 OCR（Layer 1），覆盖三种"子集路径不可靠"情形（与"无法抽页"
    对称，最大化张謇出真分机会，整份云路径的页→内容映射由云直接给出，不依赖本函数 offset 假设）：
    ① 本地抽页失败（fitz 缺失/渲染错，extract_pdf_subset→None）；
    ② 子集云 OCR 失败（OcrError/OcrDependencyError，如 transient 网络/job 失败）；
    ③ 云返回页数 ≠ 提交扫描页数（云端切页/合并与预期不符，按 offset 回填会错位）。
    """
    blocks = list(native.get("blocks", []))
    blank_indices = [i for i, b in enumerate(blocks) if len(str(b).strip()) < MAX_BLANK_CHARS]
    subset = extract_pdf_subset(path, blank_indices)
    if subset is None:
        return None  # ① 本地抽页失败 → 回退整份云 OCR
    try:
        ocr_result = recognize(subset, purpose=purpose)
        ocr_pages = ocr_result.get("pages", [])
    except (OcrError, OcrDependencyError):
        return None  # ② 子集云 OCR 失败 → 回退整份云 OCR（不在此抛，否则跳过 Layer 1 兜底）
    finally:
        try:
            subset.unlink()
        except OSError:
            pass
    if len(ocr_pages) != len(blank_indices):
        return None  # ③ 页数不匹配 → 放弃按 offset 回填（会错位），回退整份云 OCR
    # ocr_pages 按提交顺序对应 blank_indices，回填到**真实页位** blocks[blank_indices[offset]]。
    # 注意：ocr_pages[*]["page_number"] 是**子集相对序号**(1..M)，非原始页号——真实页号由 blocks
    # 下标经 _render_body 的 enumerate 给出，故此处只取 markdown，切勿用其 page_number 打锚点。
    for offset, true_idx in enumerate(blank_indices):
        markdown = ocr_pages[offset].get("markdown") or ""
        if markdown.strip():  # 空 OCR 文本不覆盖，保留原空白页跳过逻辑
            blocks[true_idx] = markdown
    result = {
        **route,
        **native,
        "blocks": blocks,
        "note": f"混合 PDF：{len(blank_indices)} 个扫描页经子集云 OCR 回填，数字页保原生直读",
    }
    if ocr_result.get("degraded") is True:
        result.update({"engine": "tesseract", "degraded": True, "clarity": "unknown"})
    return result


def extract_one(
    path: Path,
    *,
    run_seal: bool = False,
    purpose: str | None = None,
    on_unit_complete: UnitCallback | None = None,
) -> dict:
    """对单个文件识别（带按文件内容 sha256 的结果缓存，P1）。

    缓存命中（重评 / 重试 / 换评分标准时同一文件）直接返回，跳过 OCR/直读——格式无关，慢的
    扫描件收益最大。键含 purpose/run_seal（影响识别）。识别失败（可能临时故障）不缓存。

    Args:
        path: 待识别文件路径。
        run_seal: 是否附加印章识别。
        purpose: 场景化识别目的，透传给 OCR 引擎。
        on_unit_complete: 可选单元完成回调（D9 streaming-ocr T1）。默认 ``None``＝现行为逐字节
            不变。缓存命中分支也会触发**一次文件级**事件（``from_cache=True``），F3：不能因命中
            而漏事件，否则调用方（job worker）done_units 计数会卡住。
    """
    cached = ocr_cache.get_cached(path, purpose=purpose, run_seal=run_seal)
    if cached is not None:
        cached["path"] = str(path)  # 同内容不同文件名时 path 取当前文件
        if on_unit_complete is not None:
            on_unit_complete(
                _make_unit(file=str(path), page=None, status="ok", payload=cached, from_cache=True)
            )
        return cached
    result = _extract_one_raw(
        path, run_seal=run_seal, purpose=purpose, on_unit_complete=on_unit_complete
    )
    if result.get("kind") != "error":
        ocr_cache.put_cached(path, purpose=purpose, run_seal=run_seal, result=result)
    return result


def _emit_pages_from_blocks(blocks: list[str], on_page: _PageCallback) -> None:
    """从最终确定的 ``blocks``（pdf_text 逐页 append，真实页号 = 下标 + 1）逐页触发
    ``on_page``。供纯 native 路径与混合 PDF 子集增强路径复用（DRY，避免两处重复循环）。

    review pass1 F1 修复核心：页级事件只在内容**最终确定**后发一次——不再有 native 先发
    空白页、OCR/子集增强再对同页发真实内容的重复/过期问题。payload 结构对齐
    ``native.read_pdf_text`` 的 on_page 契约（``{"text": ...}``）。空白页仍发（保留页号、内容
    可空），与 ``_render_body`` 的页锚策略一致，不跳页导致页号错位。全程锁外触发（调用时
    native/augment 已返回，FITZ_LOCK/云 OCR job 早已释放）。
    """
    for page_no, block in enumerate(blocks, start=1):
        on_page(page_no, {"text": block})


def _dispatch_native_pdf_text(
    path: Path,
    route: dict,
    native: dict,
    *,
    run_seal: bool,
    purpose: str | None,
    on_page: _PageCallback | None,
) -> dict:
    """native pdf_text handler 的三路分支：font-only 回退 OCR / 混合 PDF 子集增强或整份回退 /
    纯 native（抽出减 ``_dispatch_extract`` 圈复杂度，只服务 handler=="pdf_text"，SRP）。

    页级事件时机（review pass1 F1 修复）：font-only / 混合整份回退只由 OCR 侧
    ``_call_recognize_with_seal(..., on_page=on_page)`` 发（真实内容，不再有 native 重复）；
    混合子集增强成功 / 纯 native 各自从最终 ``blocks`` 经 ``_emit_pages_from_blocks`` 发
    （页锚真实、内容最终确定，不再有过期/重复）。
    """
    if not _has_extractable_text(native):
        fallback = {
            **route,
            "route": "ocr",
            "handler": "pdf_scan",
            "note": "PDF 有字体但无可抽文本，回退 OCR",
        }
        return _call_recognize_with_seal(
            path, fallback, run_seal=run_seal, purpose=purpose, on_page=on_page
        )
    # 混合 PDF（数字页 + 扫描页）：native 抽不到扫描页内容（空串被静默丢失）。空白页计数/
    # 比例达阈值 → 只对扫描页做子集云 OCR 并回填（主路径，保数字页原生保真）；本地抽页失败
    # 回退整份云 OCR（Layer 1）。gate 在 mixed_pdf：纯数字 PDF 的空白页是真空页，无内容可补。
    if route.get("mixed_pdf") and _should_cloud_ocr_mixed_pdf(native.get("blocks", [])):
        augmented = _augment_mixed_pdf_blocks(path, route, native, purpose=purpose)
        if augmented is not None:
            if on_page is not None:
                _emit_pages_from_blocks(augmented["blocks"], on_page)
            return augmented
        fallback = {
            **route,
            "route": "ocr",
            "handler": "pdf_scan",
            "note": "混合 PDF 子集抽页失败，回退整份云 OCR 补回扫描页",
        }
        return _call_recognize_with_seal(
            path, fallback, run_seal=run_seal, purpose=purpose, on_page=on_page
        )
    if on_page is not None:
        _emit_pages_from_blocks(native.get("blocks", []), on_page)
    return {**route, **native}


def _dispatch_extract(
    path: Path, *, run_seal: bool, purpose: str | None, on_page: _PageCallback | None
) -> dict:
    """对单个文件分类并按路由直读 / OCR（``_extract_one_raw`` 主体，抽出以便调用方在异常路径
    也能统一触发单元事件）。

    异常向上传播（由 ``_extract_one_raw`` 统一捕获归一为 error，见其 docstring）。native 读取
    **不即时**触发 ``on_page``（先读不流，见 ``_call_native_read(path, None)``）——pdf_text
    handler 的页级事件时机交 ``_dispatch_native_pdf_text``（review pass1 F1 修复）；非 pdf_text
    的 native（word/excel/text 无页结构）与 ocr/manual 路由不在此发，交 ``_extract_one_raw`` 的
    "至少一次"文件级兜底（``page_emitted`` 语义不变）。
    """
    route = classify(path)
    if route["route"] == "convert":
        return _convert_and_dispatch(
            path, route, run_seal=run_seal, purpose=purpose, on_page=on_page
        )
    if route["route"] == "native":
        try:
            native = _call_native_read(path, None)
        except MemoryError:
            raise
        except Exception:
            if route.get("handler") not in {
                "legacy_word",
                "excel_xls",
                "excel_xlsb",
                "presentation",
            }:
                raise
            return _convert_and_dispatch(
                path, route, run_seal=run_seal, purpose=purpose, on_page=on_page
            )
        if route.get("handler") == "pdf_text":
            return _dispatch_native_pdf_text(
                path, route, native, run_seal=run_seal, purpose=purpose, on_page=on_page
            )
        if route.get("container") in {"word", "excel", "presentation"} and (
            not _has_extractable_text(native)
            or (
                route.get("container") == "presentation"
                and _presentation_needs_ocr(native)
            )
        ):
            return _convert_and_dispatch(
                path, route, run_seal=run_seal, purpose=purpose, on_page=on_page
            )
        return {**route, **native}
    if route["route"] == "ocr":
        return _call_recognize_with_seal(
            path, route, run_seal=run_seal, purpose=purpose, on_page=on_page
        )
    return {**route, "kind": "manual"}


def _convert_and_dispatch(
    path: Path,
    original_route: dict,
    *,
    run_seal: bool,
    purpose: str | None,
    on_page: _PageCallback | None,
) -> dict:
    """Convert Office input to PDF, then reuse the PDF native/OCR ladder."""
    with convert_office_to_pdf(path) as pdf:
        pdf_route = classify(pdf)
        if pdf_route["route"] == "native":
            native = _call_native_read(pdf, None)
            downstream = _dispatch_native_pdf_text(
                pdf,
                pdf_route,
                native,
                run_seal=run_seal,
                purpose=purpose,
                on_page=on_page,
            )
        else:
            downstream = _call_recognize_with_seal(
                pdf,
                pdf_route,
                run_seal=run_seal,
                purpose=purpose,
                on_page=on_page,
            )
    return {
        **original_route,
        **downstream,
        "path": str(path),
        "converted_from": path.suffix.lower(),
        "downstream_route": downstream.get("route", pdf_route.get("route")),
        "route": "convert",
    }


def _extract_one_raw(
    path: Path,
    *,
    run_seal: bool = False,
    purpose: str | None = None,
    on_unit_complete: UnitCallback | None = None,
) -> dict:
    """对单个文件分类并按路由直读 / OCR；任何失败归一为 error（per-file 隔离）。

    页级粒度自适应（D9 streaming-ocr T1，方案 A；页级事件时机见 review pass1 F1 修复）：
    - native pdf_text：读取完成后从**最终确定的 blocks** 逐页发（``_dispatch_native_pdf_text`` →
      ``_emit_pages_from_blocks``）——纯 native 从 native blocks、混合子集增强从 augmented blocks，
      font-only/整份回退则只由 OCR 侧发（不再有 native 先空后真的重复/过期）。全程锁外。
    - OCR 路径：本地 paddle pipeline 走 buffer-then-fire（``PADDLE_LOCK`` 内收集、锁外回放，见
      engine._recognize_via_paddle_pipeline）；VLM openai-compatible 识别循环锁外逐页直接触发。
    - 无页循环路径（excel/word/text/cloud 整档）或识别失败：退化为**一次文件级**事件（"至少一次"，
      design 方案 A 粒度自适应兜底，``page_emitted`` 语义）。
    """
    file_str = str(path)
    page_emitted = False
    on_page: _PageCallback | None = None

    if on_unit_complete is not None:
        # on_page 只在真有回调时才构造成非 None——保持 on_unit_complete=None（默认）时
        # on_page 全链路仍是 None，_call_native_read/_call_recognize_with_seal 才会走
        # "不多传 kwarg" 分支，与存量对 native_read/_recognize_with_seal 的旧签名 mock 兼容。
        def _on_page(page_no: int, payload: dict) -> None:
            nonlocal page_emitted
            page_emitted = True
            on_unit_complete(
                _make_unit(file=file_str, page=page_no, status="ok", payload=payload, from_cache=False)
            )

        on_page = _on_page

    try:
        result = _dispatch_extract(path, run_seal=run_seal, purpose=purpose, on_page=on_page)
    except MemoryError:
        raise
    except Exception as exc:  # per-file 隔离：损坏 / 缺引擎 / 解析错误都归一为 error
        logger.warning("extract failed for %s: %s", path, exc)
        result = {"path": file_str, "kind": "error", "route": "manual", "error": str(exc)}

    if on_unit_complete is not None and (
        not page_emitted or result.get("kind") == "error"
    ):
        status = "error" if result.get("kind") == "error" else "ok"
        on_unit_complete(
            _make_unit(file=file_str, page=None, status=status, payload=result, from_cache=False)
        )
    return result


def extract_dir(
    case_dir: str,
    *,
    run_seal: bool = False,
    purpose: str | None = None,
    on_unit_complete: UnitCallback | None = None,
) -> list[dict]:
    """对目录下每个文件跑确定性识别（多文件并行），返回结构化产物列表（不调模型）。

    多文件时用线程池并行——扫描件走云 OCR 是 job-poll IO 等待，串行十几个标书文件会数分钟
    甚至超时，并行把墙钟压到"最慢单个"。``ThreadPoolExecutor.map`` 保持文件顺序（底稿组装依赖
    顺序）；``extract_one`` 已 per-file 隔离（异常归 error），并行不互相拖垮。并发度 = min(
    ``OCR_MAX_WORKERS``, 文件数)。单文件直接同步（不值得开池）。

    Args:
        on_unit_complete: 可选单元完成回调，透传给每个 ``extract_one``（D9 streaming-ocr T1）。
            默认 ``None``＝现行为逐字节不变。多文件并行时回调会从多个 worker 线程并发触发——
            本函数只保证回调被正确调用且携带正确 unit，回调本身的线程安全由调用方负责。
    """
    files = _iter_files(case_dir)
    if len(files) <= 1:
        return [
            extract_one(path, run_seal=run_seal, purpose=purpose, on_unit_complete=on_unit_complete)
            for path in files
        ]
    workers = min(OCR_MAX_WORKERS, len(files))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(
            pool.map(
                lambda path: extract_one(
                    path, run_seal=run_seal, purpose=purpose, on_unit_complete=on_unit_complete
                ),
                files,
            )
        )


def _render_tables(tables: list[dict]) -> str:
    lines: list[str] = []
    for table in tables:
        if table.get("name"):
            lines.append(f"[表: {table['name']}]")
        for row in table.get("rows", []):
            lines.append("\t".join(str(cell) for cell in row))
    return "\n".join(lines)


def _page_anchor(page_no: int) -> str:
    """页锚点：让模型 evidence/basis 能引到底稿真实页（G2 证据定位准确性）。"""
    return f"【第 {page_no} 页】\n"


# 识别失败标记前缀：识别失败时 _render_body 以此前缀打头该文件正文。
# 公开常量 + is_ocr_text_valid 是 OCR 域唯一权威，消费方（评标上传 OCR 编排）据此判文本有效性，
# 不要在调用层各自硬编码该字符串（S3 消重：原 routes/tender.py 重复定义了一份）。
OCR_ERROR_PREFIX = "[识别失败]"
# build_extraction_block 每个文件以此为头、空目录回退此占位（is_ocr_text_valid 据此剔除非内容行）。
_FILE_HEADER_PREFIX = "### 文件:"
_EMPTY_BLOCK_MARKER = "（无识别内容）"
_PAGE_ANCHOR_PATTERN = re.compile(r"^【第\s+\d+\s+页】$")


def is_ocr_text_valid(text: str) -> bool:
    """True iff the rendered OCR block contains at least one line of real recognized content.

    ``prewarm_and_text``→``build_extraction_block`` 把每个文件渲染成 ``### 文件: …`` 头 + 正文；
    识别失败的文件正文以 ``OCR_ERROR_PREFIX`` 打头，空目录回退 ``_EMPTY_BLOCK_MARKER``。
    **不能只看整体 startswith(prefix)**——文件头在最前，全失败时整体不以 prefix 开头会被误判有效
    （后台 OCR 会把失败件写成 ocr_status=ready）。逐行剔除文件头/失败行/空行/空占位后，只要还剩
    任一真实内容行即有效（多文件部分成功也算有效）。
    """
    stripped = text.strip()
    if not stripped or stripped == _EMPTY_BLOCK_MARKER:
        return False
    for line in stripped.splitlines():
        s = line.strip()
        if (
            not s
            or s.startswith(_FILE_HEADER_PREFIX)
            or s.startswith(OCR_ERROR_PREFIX)
            or _PAGE_ANCHOR_PATTERN.fullmatch(s)
        ):
            continue
        return True
    return False


def _render_body(result: dict) -> str:
    if result.get("error"):
        return f"{OCR_ERROR_PREFIX} {result['error']}"
    # pages 仅指 OCR 引擎产物（list[每页 {markdown}]）；native 文件的页数在 page_count，
    # 不在此。isinstance 守卫防止把页数整数误当列表迭代。
    pages = result.get("pages")
    if isinstance(pages, list) and pages:
        # 每页加页锚点（page_number 缺/None 才回退序号；不用 `or` 以免 page_number=0 被吞）。
        return "\n\n".join(
            _page_anchor(pn if (pn := page.get("page_number")) is not None else idx)
            + (page.get("markdown") or "")
            for idx, page in enumerate(pages, start=1)
        )
    # native：blocks(正文) 与 tables(表) 可并存（pdf_text/word 两者都有）→ **都渲染**。
    # 旧逻辑 tables 分支吃掉 blocks 会丢正文；P1 给 pdf_text 加了 find_tables 后更明显，故合并。
    segments: list[str] = []
    blocks = result.get("blocks")
    if blocks:
        # pdf_text 的 blocks 一页一项（read_pdf_text 逐页 append）→ 按页打锚点，跳空页但保留页号，
        # 让模型能引真实页（G2）；其余 kind（word/text）blocks 非页结构，原样拼。
        if result.get("kind") == "pdf_text":
            segments.append(
                "\n\n".join(
                    _page_anchor(i) + b
                    for i, b in enumerate(blocks, start=1)
                    if isinstance(b, str) and b.strip()
                )
            )
        else:
            segments.append("\n".join(blocks))
    if result.get("tables"):
        segments.append(_render_tables(result["tables"]))
    return "\n\n".join(seg for seg in segments if seg.strip())


def file_clarity(result: dict, *, threshold: float = OCR_CLARITY_MIN_CONFIDENCE) -> str:
    """文件级清晰度信号（确定性，不调模型）：clear / low / unknown / failed。

    - error / kind=error → failed
    - OCR 产物：任一页 confidence < threshold → low；全无置信度信号（VLM 端点路径）→ unknown
    - native 直读（数字文件，零 OCR 误差）→ clear

    这是"识别不清晰"的**检测**原语：底稿据此显式标注，下游不再拿糊文本当真。
    """
    if result.get("error") or result.get("kind") == "error":
        return "failed"
    pages = result.get("pages")
    if isinstance(pages, list) and pages:
        confidences = [
            page["confidence"]
            for page in pages
            if isinstance(page, dict)
            and isinstance(page.get("confidence"), (int, float))
            and not isinstance(page.get("confidence"), bool)
        ]
        if not confidences:
            return "unknown"
        return "low" if min(confidences) < threshold else "clear"
    return "clear"


# R2：通用截断「从头切」是否改「首尾切」（保尾部，如合同付款节点/落款）。**默认关**——
# expense/audit 关键字段多在头部，贸然减头部预算会回归；tender 大非 BOQ 文件需保尾可经 env 开。
def _truncate_head_tail_enabled() -> bool:
    return os.getenv("OCR_TRUNCATE_HEAD_TAIL", "0").lower() in {"1", "true", "yes"}


def _truncate_body(full_body: str) -> str:
    """大文件截断：默认头截（向后兼容）；OCR_TRUNCATE_HEAD_TAIL=1 则首尾截（保尾）。

    截断标记**不含 `【第N页】` 字样**——免破 evidence-resolution 的 parse_corpus 页索引（R1 协同）。
    """
    n = len(full_body)
    if _truncate_head_tail_enabled():
        head_n = int(MAX_FILE_BLOCK_CHARS * 0.7)
        tail_n = MAX_FILE_BLOCK_CHARS - head_n
        marker = (
            f"\n\n...[内容已截断：本文件共 {n} 字符，保留首 {head_n} + 尾 {tail_n}，"
            f"中间省略；相关字段请标 low_confidence / needs_review]\n\n"
        )
        return full_body[:head_n] + marker + full_body[-tail_n:]
    return full_body[:MAX_FILE_BLOCK_CHARS] + (
        f"\n\n...[内容已截断：本文件共 {n} 字符，仅保留前 {MAX_FILE_BLOCK_CHARS}；"
        f"尾部信息（如合同付款节点）可能丢失，相关字段请标 low_confidence / needs_review]"
    )


def build_extraction_block(results: list[dict]) -> str:
    """把结构化产物组装成内联文本底稿，供模型做字段映射。

    单文件超过 MAX_FILE_BLOCK_CHARS 时：
    - **BOQ（已标价工程量清单）** → 结构化抽关键金额（投标总价/各合计/Top-N）紧凑摘要（R2），
      替代"210 页噪音从头截"——治报价淹没/失据（见 ``server.ocr.boq``）。
    - 其余大文件 → ``_truncate_body``（默认头截，env 可首尾截），并**显式标记**避免静默丢尾。
    """
    parts: list[str] = []
    for result in results:
        name = Path(result.get("path", "?")).name
        head = f"{_FILE_HEADER_PREFIX} {name} (kind={result.get('kind')}, route={result.get('route')})"
        full_body = _render_body(result)
        if len(full_body) > MAX_FILE_BLOCK_CHARS:
            summary = (
                boq_extract.extract_boq_summary(
                    name, full_body, max_chars=MAX_FILE_BLOCK_CHARS // 4
                )
                if boq_extract.is_boq(name, full_body, kind=result.get("kind"))
                else None
            )
            body = summary if summary is not None else _truncate_body(full_body)
        else:
            body = full_body
        seals = result.get("seals")
        if seals:
            head += f" [检出印章 {len(seals)} 枚]"
        head += _CLARITY_NOTE.get(file_clarity(result), "")
        parts.append(f"{head}\n{body}".rstrip())
    return "\n\n".join(parts) or _EMPTY_BLOCK_MARKER


def prewarm_and_text(case_dir: str, *, purpose: str | None = None) -> str:
    """预热 content-sha256 缓存并返回目录 OCR 底稿文本（P2 上传即 OCR 解耦）。

    复用 ``extract_dir``（已有 content-sha256 缓存），对目录下每个文件跑确定性 OCR，
    把结果组装成内联底稿（``build_extraction_block``）并返回字符串。

    用于上传端点触发的后台 OCR 预热：评标时读层直接取 ocr_text，跳过串行 OCR。
    **同步函数**，async 调用方须经 ``asyncio.to_thread``（含云 OCR 会阻塞事件循环）。

    Args:
        case_dir: 文件目录路径（招标或投标文件落盘目录）。
        purpose: 透传给 OCR 引擎的场景提示（如评标目的字符串）。

    Returns:
        内联底稿文本字符串（``build_extraction_block`` 产物，至少 "（无识别内容）"）。
    """
    results = extract_dir(case_dir, purpose=purpose)
    return build_extraction_block(results)


def ocr_preprocess_block(
    case_dir: str, *, skip: set[str] | None = None, purpose: str | None = None
) -> str | None:
    """P4：对 case 目录做确定性 OCR 预处理，返回内联底稿供注入模型上下文（不调判断模型）。

    OCR_PREPROCESS=0 关闭（回落模型自己 Read）。任何失败 → None（降级，**绝不拖垮**审核/评标）。
    skip：按文件名跳过已单独内联的文件（如 audit-request.json）。**同步**函数，async 调用方须经
    ``asyncio.to_thread`` 调用（含云 OCR，会阻塞事件循环）。
    """
    if not OCR_PREPROCESS:
        return None
    try:
        results = extract_dir(case_dir, purpose=purpose)
        if skip:
            results = [r for r in results if Path(r.get("path", "")).name not in skip]
        if not results:
            return None
        return build_extraction_block(results)
    except Exception:
        logger.warning("ocr_preprocess 失败 %s（降级回落模型 Read）", case_dir, exc_info=True)
        return None
