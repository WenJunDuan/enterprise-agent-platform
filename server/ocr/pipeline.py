"""编排：目录 → 每文件分类 → 直读/OCR → 组装内联"识别底稿"。不调模型。

这是确定性流水线的单一入口，被 `server.ocr.runner`（进程内）与 `python -m server.ocr`
（交互式）共用。每个文件独立 try，一个文件失败不拖垮整批（标 manual + error）。
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from server.ocr import boq as boq_extract
from server.ocr import cache as ocr_cache
from server.ocr.classify import classify
from server.ocr.engine import extract_pdf_subset, recognize, recognize_seal
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

# 混合 PDF（数字页 + 扫描页）整份转云 OCR 的触发阈值。背景：classify 以文件级 fonts>0 判 native，
# 整份 PDF 只要有文本层就全判 native，其中扫描页经 pymupdf get_text 抽出空串被静默丢失（张謇
# 400 页投标含 ~59 页扫描资质/业绩/职称证书 → 底稿缺据 → 技术/业绩/负责人评分只能 manual）。
# 触发判据 = 计数为主 + 比例兜底：空白页**数量** ≥ MIN_COUNT（59 页绝对量是强信号，不该被
# 341 数字页稀释成 ratio 0.147），或空白**比例** > RATIO（兜底小份多扫描件，如 6 页 4 扫 ratio
# 0.67 但 count 4<10）。仅对 classify 判定的 mixed_pdf 生效（纯数字 PDF 的空白页是真空页，无
# 扫描内容可补）。两阈值均 env 可灰度。详见 .ai_state/sprints/2026-06-23-tender-ui-scoring-fixes/
# per-page-ocr-plan.md「决策修正」。
MAX_BLANK_CHARS = int(os.getenv("OCR_BLANK_PAGE_MIN_CHARS", "20"))
OCR_BLANK_PAGE_MIN_COUNT = int(os.getenv("OCR_BLANK_PAGE_MIN_COUNT", "10"))
OCR_BLANK_PAGE_RATIO = float(os.getenv("OCR_BLANK_PAGE_RATIO", "0.5"))


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


# P1-4: sidecar files written by materialize_upload_submission must not be OCR-processed.
# audit-request.json is a metadata sidecar written into every submission dir — it is not
# a user document and must be excluded to avoid polluting the extraction block.
_OCR_EXCLUDED_FILENAMES: frozenset[str] = frozenset({"audit-request.json"})


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


def _recognize_with_seal(
    path: Path, route: dict, *, run_seal: bool, purpose: str | None = None
) -> dict:
    """走 OCR 引擎识别（可选印章），合并分诊信息。purpose 透传给 OCR 引擎做场景化识别。"""
    result = {**route, **recognize(path, purpose=purpose)}
    if run_seal:
        result["seals"] = recognize_seal(path).get("seals", [])
    return result


def _has_extractable_text(native: dict) -> bool:
    """native 直读是否抽到非空文本（blocks 或 tables 任一有内容）。"""
    if any(block.strip() for block in native.get("blocks", [])):
        return True
    return any(
        any(str(cell).strip() for cell in row)
        for table in native.get("tables", [])
        for row in table.get("rows", [])
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

    本地抽页失败（fitz 缺失/渲染错）→ 返回 None，调用方回退整份云 OCR（Layer 1）；云识别失败由
    外层 per-file 隔离归 error（不在此重试整份，避免双倍云开销）。
    """
    blocks = list(native.get("blocks", []))
    blank_indices = [i for i, b in enumerate(blocks) if len(str(b).strip()) < MAX_BLANK_CHARS]
    subset = extract_pdf_subset(path, blank_indices)
    if subset is None:
        return None  # 本地抽页失败 → 回退整份云 OCR
    try:
        ocr_pages = recognize(subset, purpose=purpose).get("pages", [])
    finally:
        try:
            subset.unlink()
        except OSError:
            pass
    # OCR 结果按提交顺序对应 blank_indices；回填到真实页位（空文本不覆盖，保留原空白页跳过逻辑）。
    for offset, true_idx in enumerate(blank_indices):
        if offset < len(ocr_pages) and (text := (ocr_pages[offset].get("markdown") or "")).strip():
            blocks[true_idx] = text
    return {
        **route,
        **native,
        "blocks": blocks,
        "note": f"混合 PDF：{len(blank_indices)} 个扫描页经子集云 OCR 回填，数字页保原生直读",
    }


def extract_one(path: Path, *, run_seal: bool = False, purpose: str | None = None) -> dict:
    """对单个文件识别（带按文件内容 sha256 的结果缓存，P1）。

    缓存命中（重评 / 重试 / 换评分标准时同一文件）直接返回，跳过 OCR/直读——格式无关，慢的
    扫描件收益最大。键含 purpose/run_seal（影响识别）。识别失败（可能临时故障）不缓存。
    """
    cached = ocr_cache.get_cached(path, purpose=purpose, run_seal=run_seal)
    if cached is not None:
        cached["path"] = str(path)  # 同内容不同文件名时 path 取当前文件
        return cached
    result = _extract_one_raw(path, run_seal=run_seal, purpose=purpose)
    if result.get("kind") != "error":
        ocr_cache.put_cached(path, purpose=purpose, run_seal=run_seal, result=result)
    return result


def _extract_one_raw(path: Path, *, run_seal: bool = False, purpose: str | None = None) -> dict:
    """对单个文件分类并按路由直读 / OCR；任何失败归一为 error（per-file 隔离）。

    - font-only 扫描 PDF（有字体但 native 抽不到文本）回退 OCR，避免返回空结果。
    - 任何异常（损坏文件 / 缺引擎 / 解析错误）归一为 kind=error，单个失败不拖垮整批。
    """
    try:
        route = classify(path)
        if route["route"] == "native":
            native = native_read(path)
            if route.get("handler") == "pdf_text" and not _has_extractable_text(native):
                fallback = {
                    **route,
                    "route": "ocr",
                    "handler": "pdf_scan",
                    "note": "PDF 有字体但无可抽文本，回退 OCR",
                }
                return _recognize_with_seal(path, fallback, run_seal=run_seal, purpose=purpose)
            # 混合 PDF（数字页 + 扫描页）：native 抽不到扫描页内容（空串被静默丢失）。空白页计数/
            # 比例达阈值 → 只对扫描页做子集云 OCR 并回填（主路径，保数字页原生保真）；本地抽页失败
            # 回退整份云 OCR（Layer 1）。gate 在 mixed_pdf：纯数字 PDF 的空白页是真空页，无内容可补。
            if (
                route.get("handler") == "pdf_text"
                and route.get("mixed_pdf")
                and _should_cloud_ocr_mixed_pdf(native.get("blocks", []))
            ):
                augmented = _augment_mixed_pdf_blocks(path, route, native, purpose=purpose)
                if augmented is not None:
                    return augmented
                fallback = {
                    **route,
                    "route": "ocr",
                    "handler": "pdf_scan",
                    "note": "混合 PDF 子集抽页失败，回退整份云 OCR 补回扫描页",
                }
                return _recognize_with_seal(path, fallback, run_seal=run_seal, purpose=purpose)
            return {**route, **native}
        if route["route"] == "ocr":
            return _recognize_with_seal(path, route, run_seal=run_seal, purpose=purpose)
        return {**route, "kind": "manual"}
    except Exception as exc:  # per-file 隔离：损坏 / 缺引擎 / 解析错误都归一为 error
        logger.warning("extract failed for %s: %s", path, exc)
        return {"path": str(path), "kind": "error", "route": "manual", "error": str(exc)}


def extract_dir(case_dir: str, *, run_seal: bool = False, purpose: str | None = None) -> list[dict]:
    """对目录下每个文件跑确定性识别（多文件并行），返回结构化产物列表（不调模型）。

    多文件时用线程池并行——扫描件走云 OCR 是 job-poll IO 等待，串行十几个标书文件会数分钟
    甚至超时，并行把墙钟压到"最慢单个"。``ThreadPoolExecutor.map`` 保持文件顺序（底稿组装依赖
    顺序）；``extract_one`` 已 per-file 隔离（异常归 error），并行不互相拖垮。并发度 = min(
    ``OCR_MAX_WORKERS``, 文件数)。单文件直接同步（不值得开池）。
    """
    files = _iter_files(case_dir)
    if len(files) <= 1:
        return [extract_one(path, run_seal=run_seal, purpose=purpose) for path in files]
    workers = min(OCR_MAX_WORKERS, len(files))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(
            pool.map(lambda path: extract_one(path, run_seal=run_seal, purpose=purpose), files)
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


def _render_body(result: dict) -> str:
    if result.get("error"):
        return f"[识别失败] {result['error']}"
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
        head = f"### 文件: {name} (kind={result.get('kind')}, route={result.get('route')})"
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
    return "\n\n".join(parts) or "（无识别内容）"


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
