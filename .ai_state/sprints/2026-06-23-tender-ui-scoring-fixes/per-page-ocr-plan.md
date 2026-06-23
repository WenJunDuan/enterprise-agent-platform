# 设计 · 混合 PDF 扫描页 OCR 路由（"逐页 OCR" 计划）

> 由 workflow `per-page-ocr-plan` 产出（5 维 grounding → 2 方案选优 → 风险对抗验证），CC 综合落档。
> 状态：**设计就绪，待用户确认后实施**。归属 Sprint：2026-06-23-tender-ui-scoring-fixes。

## 背景（为什么做）

张謇 3 模型 dogfood 实测：投标 400 页中 **~59 页（资质/业绩/职称/社保/检测报告）是扫描件**。
根因（grounding 确认）：`classify._probe_pdf` 以 **文件级** `fonts>0` 为唯一判据 → 整份 PDF 只要有一页有字体就全判
`native`，扫描页经 `page.get_text()` 抽出**空字符串**且**静默丢失**（不报错）。→ 底稿缺这 59 页 →
技术参数/企业实力/负责人评分缺据 → 模型只能 manual_review。**这是评标拿不到全自动真分的唯一卡点。**

## 方案对比与决策（workflow judge）

| | 方案 A 逐页渲染+单页云 OCR | **方案 B 阈值触发整份云 OCR（选定）** |
|---|---|---|
| 正确性 | 单页 PNG→aistudio **接口未验证** + 拆页**破坏跨页表格**（评分表常跨页）| 走**已生产验证**的 `_recognize_via_paddle_cloud`，服务端保跨页表格连续 |
| 延迟 | 59 页串行 ~2100s / 并发4 ~530s（>TENDER_TIMEOUT 1200）| 整份 job ~65-250s |
| 缓存 | 需 bump `_CACHE_VERSION`→**全量重 OCR** | kind=ocr 缓存键经 `_engine_fingerprint` 含 OCR_CLOUD **天然隔离，无需 bump** |
| 复杂度/回退 | +150 行（线程池+信号量+临时文件+未验证路径）| **+~35 行**，复用现有调用链，删分支即回退 |

**决策：方案 B 为主体，三层吸收 A 的逐页能力。**

## 实施（三层）

### Layer 1 — 立即可上线（~35 行，本计划核心）
1. **`pipeline.py` 顶部常量**（与 `MAX_FILE_BLOCK_CHARS` 同列）：
   `OCR_BLANK_PAGE_RATIO=float(getenv('OCR_BLANK_PAGE_RATIO','0.4'))`（灰度期先 `0.8`）、
   `OCR_BLANK_PAGE_MIN_CHARS=int(getenv('OCR_BLANK_PAGE_MIN_CHARS','20'))`。
2. **新函数 `_blank_page_ratio(blocks: list[str]) -> float`**（紧接 `_has_extractable_text` 之后，≤10 行，纯计算可单测）：
   `len([b for b in blocks if not b.strip() or len(b.strip())<MIN_CHARS]) / max(1,len(blocks))`。
3. **`_extract_one_raw`（pipeline.py:121）** handler==`pdf_text` 分支，在现有"全空回退 OCR"**之后**插阈值判断：
   `ratio>OCR_BLANK_PAGE_RATIO` → 构 `fallback{route:'ocr', handler:'pdf_scan'}` → `return _recognize_with_seal(path, fallback, ...)`（整份走云）；否则原样 `return {**route, **native}`。逻辑分支互斥。
4. **🔴 BLOCKER 同批修：`engine.py:_parse_cloud_jsonl`** `for res in layoutParsingResults` → `enumerate(..., start=1)` 并注入 `'page_number': page_no`。否则整份云路径 pages 缺 `page_number` → `_render_body` 回退枚举序号 → **evidence `【第N页】` 回查定位失准（伤 G2）**。这是存量 bug，逐页/整份都需要。
5. **`classify._probe_pdf` 加 `mixed_pdf`**（`fonts>0 且 image_filters>0`）：供 `_extract_one_raw` early-exit（非 mixed 跳过 `_blank_page_ratio`，优化数字 PDF 快路径）。classify 不做页级分支（SRP）。
6. **env**：`OCR_VL_CLOUD_MAX_WAIT=1200`（对齐 TENDER_TIMEOUT，防云 job 排队误超时）。
7. **不 bump `_CACHE_VERSION`**（kind=pdf_text 旧缓存与 kind=ocr 新键天然隔离）。
8. **单测** `tests/ocr/test_pipeline_mixed_pdf.py`：59 空/341 文（ratio~0.147<0.4 不触发）；200/200（0.5>0.4 触发，fallback handler=pdf_scan）；ratio=0 全触发边界；mock `_recognize_with_seal` 验调用参数。

调用链不变：`extract_one`→（缓存命中即跳过）→`_extract_one_raw`→新阈值判断→`_recognize_with_seal`→`recognize`→`_recognize_via_paddle_cloud`。

### Layer 2 — 验证后可选（~150 行，env `OCR_MIXED_PDF_PAGE_MODE` 默认 0）
aistudio **单页 PNG 接口兼容性实测通过后**才启用：`_merge_scan_pages` 用 `ThreadPoolExecutor(OCR_VL_PAGE_WORKERS)` 对空洞页并发逐页提交 + `threading.Semaphore` 限全局页级并发（防文件级×页级叠加超 aistudio 配额）。决策树：非 mixed→native；ratio≤阈值→native；PAGE_MODE=0→B 整份；=1→A 逐页。

### Layer 3 — 缓存渐进失效
对已有 kind=pdf_text 混合 PDF 旧缓存：接受"下次重评/重传自然走新路径"；需强制失效则离线脚本统计 `data/ocr-cache/` 中 kind=pdf_text 且空页占比高的条目定向删，**不全量 bump**。

## 影响范围
`server/ocr/pipeline.py`（常量+新函数+1 分支）、`server/ocr/engine.py`（_parse_cloud_jsonl 2 行）、`server/ocr/classify.py`（mixed_pdf 字段）、`.env` 示例、`tests/ocr/`（新测试）。零新依赖。

## 风险与缓解
| 风险 | 缓解 |
|---|---|
| 🔴 整份云 path 缺 page_number（BLOCKER）| Layer 1 步骤 4 enumerate 修复，同批上线 |
| native_read 冗余执行（mixed PDF 先抽再丢）| 步骤 5 classify mixed_pdf + page_count 阈值 early-exit |
| 阈值 0.4 未经真实样本标定 | 上线前离线统计 `data/ocr-cache/` kind=pdf_text 空页占比分布，或人工标 3-5 份混合标书；灰度先 0.8 |
| 云 path `purpose` 被丢弃（评标场景提示对云无效）| 架构隐性限制；若评分表识别质量不足 → 降级 OCR_CLOUD=0 + openai-compatible 逐页 |
| 成本：整份多送 341 数字页 | 数字页有文本层云端识别极快；按 job 计费不变，按页计费 ~5.8x 页数（评估 ≤30% 增量）；缓存命中零增量 |
| aistudio 单页 PNG 兼容性未验证 | Layer 2 前置实测，未通过则停留 Layer 1（整份）|

## 验收
- 张謇新和重评：59 扫描页内容进底稿，技术参数/企业实力/负责人从 manual_review → **scored 真分**（3 模型，尤其 qwen/deepseek 不再因读不到证书 punt）。
- evidence `【第N页】` 回查定位准确（page_number 修复后）。
- 数字 PDF（无扫描页）快路径不受影响（early-exit）；纯扫描 PDF 行为不变。
- `uv run pytest -q` + ruff 全绿；OCR_BLANK_PAGE_RATIO 灰度可调。

## 待用户确认点
1. **是否实施 Layer 1**（核心，~35 行 + 测试）？
2. 阈值 `OCR_BLANK_PAGE_RATIO` 初值：灰度 0.8 还是直接 0.4？
3. Layer 2（逐页并发）是否本 Sprint 做，还是待 Layer 1 验证后另议？
