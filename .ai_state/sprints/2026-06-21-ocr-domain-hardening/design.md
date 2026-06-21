# OCR 域强化 + 招投标接入 OCR — Design

> Sprint 2026-06-21 · Path: System · 对话驱动；先调研(两库已 fetch README)后设计

## 0. 结论（先读这段）

1. **别替换 PaddleOCR-VL。** 它是你的中文扫描 SOTA;liteparse(自带 Tesseract)和 opendataloader(EasyOCR 系后端)在中文扫描件上都更弱。换掉=降级。
2. **真正该升级的是「文本层 PDF 读取器」**——你现在用 `pypdf`(native.py:57),只抽字符、丢表格/丢阅读顺序/丢多栏。这是大多数场景(电子发票/电子合同/招标文件评分表)、也是你"识别不清晰"投诉的真凶。
3. **升级路径**：先 `pymupdf`(零新依赖,已在 deps;`find_tables()` + 版面块),不够再上 **opendataloader-pdf 本地模式**(表格/阅读顺序基准 #1,纯 CPU,但 +JVM)。**跳过 liteparse**(表格弱,它的增量只是 bbox/截图,pymupdf 也能给)。
4. **补一个置信度信号**——这才是"识别不清晰"的**检测**机制,你现在底稿里完全没有(只有 kind/route/error)。没有它,模型看到糊的文本也当真。
5. **盖章/低置信页 → 多模态兜底**：渲染成图喂 VL 模型(走你现成的 LiteLLM 端点),门控、按页触发、失败降级 manual_review。
6. **招投标**：OCR 作为 S2 前的**确定性预处理**;按投标章节 **map-reduce**;低置信 → `manual_review`(直接接你"不可判定项绝不判 0"教义);印章 → 投标人名称一致性核验。

## 1. 两个候选库的实测定位（+ 你的现状）

| 维度 | liteparse (run-llama) | opendataloader-pdf | 你现状 (pypdf + PaddleOCR-VL) |
| --- | --- | --- | --- |
| License | Apache-2.0 | Apache-2.0 | — |
| 离线/隔离 | ✓ (Tesseract 打包 / 可 HTTP 接 PaddleOCR) | ✓ 100% 本地、无云、**无 GPU** | ✓ (PaddleOCR-VL serving 需 GPU) |
| 运行时依赖 | Rust 原生二进制 (PyO3),`pip install` 轻 | **JVM (Java 11+)**,每次 convert 起一个 JVM 进程 | 纯 Python |
| 表格 | 弱（自评基准 table=0.000;README 自承复杂文档要上云） | **强 (0.928 hybrid / 0.489 local),基准第一** | pypdf 丢表格;PaddleOCR-VL 扫描表格好 |
| 阅读顺序/多栏 | 空间网格 + bbox | **XY-Cut++ + 每元素 bbox(最佳)** | pypdf 朴素;PaddleOCR-VL 版面感知 |
| 中文扫描 | 自带 Tesseract(弱);可 HTTP 转 PaddleOCR | hybrid OCR ch_sim(EasyOCR 系,中等) | **PaddleOCR-VL(中文 SOTA)** ✓ |
| Word/Excel | 经 LibreOffice 转 PDF | **不支持(仅 PDF)** | 原生 python-docx/openpyxl ✓ |
| 防注入 | 无 | **有(过滤隐藏文字/页外/隐形层)** | 无(round4 L5 缺口) |
| 给多模态用的页图 | `lit screenshot` | 注记 PDF/抽图 | pymupdf 可渲染(已装) |

> ⚠️ 基准口径:0.907/table-0.928 与 liteparse-0.000 都来自 **opendataloader 自己的 benchmark 仓**,自评、非中立。但方向被 liteparse 自己的 README 佐证(承认复杂表格/扫描弱)。把它当"方向可信、绝对值打折"。

**取舍判断**：opendataloader 的强项(版面/表格/阅读顺序/防注入)正好补你 pypdf 的短板,且纯 CPU、可离线;代价是一个 JVM。liteparse 的强项(轻、Rust、截图)替代不了你缺的东西(表格)。所以**候选是 opendataloader,不是 liteparse**;但**先别急着上 JVM**——pymupdf 已在手,先吃掉表格这口,证明不够再上 opendataloader。

## 2. "识别不清晰"按格式拆解 + 读取器阶梯

把"识别不清晰"拆开,每种格式的短板与升级各不相同:

| 格式 | 现 handler | 清晰度短板 | 升级 |
| --- | --- | --- | --- |
| 电子 PDF(文本层) | native `pdf_text` = pypdf | **丢表格/阅读顺序/多栏** | pymupdf `find_tables()`+版面块 → 不够再 opendataloader 本地 |
| 扫描 PDF/图片(中文) | OCR = PaddleOCR-VL | DPI 偏低、无置信度门控 | 保留引擎;升 `OCR_VL_PDF_RENDER_SCALE`(2→3)、加去斜/去噪、**捕获置信度** |
| 盖章页(业绩/资质) | seal pipeline `recognize_seal` | 公章压字、faint text OCR 糊 | seal 检测 + **多模态兜底**(§4) |
| Word .docx | native python-docx | 文本框/页眉/嵌套表偶漏 | 次要;必要时补 docx 表格/文本框遍历 |
| Excel .xlsx | native openpyxl `data_only` | 良好 | 保留 |
| 未知/损坏 | manual | — | 保留(转人工,不硬塞模型) |

**四层读取阶梯**(classify 路由不变,扩 native 与新增多模态层):

1. **native-layout**(电子 PDF/Word/Excel):版面感知抽取,**确定、便宜、零网关**。大多数文档走这层。
2. **OCR-VL**(扫描中文):PaddleOCR-VL,**带置信度返回**。
3. **multimodal**(盖章/低置信/复杂版面残差):渲染页→VL 模型,**门控、按页**。
4. **manual**:未知/损坏/全低置信 → 人工。

## 3. 置信度信号（缺失的核心原语）

现状:`build_extraction_block`(pipeline.py:116) 只标 `kind/route/error/seals`,**没有任何清晰度信号**。模型拿到一段糊文本和一段干净文本,无从区分。

补法(确定性、不调模型):
- OCR-VL 与 opendataloader 都按块/页返回 `confidence`/bbox;native 直读视为高置信。
- 每块打 `clarity ∈ {clear, low, failed}`(阈值可 env)。底稿里**低置信块显式标注**(像现在截断标注那样)。
- 聚合:单文件低置信占比 > 阈值 → 文件级 `needs_review`;关键字段(金额/日期/印章单位)落在低置信块 → 该字段 `needs_review`。
- 接 round4 backlog②(算术重算):金额/日期从**高置信块**取确定性数,Python 重比较;落在低置信块的数不参与自动判定。

这一步把"识别不清晰"从**事后靠模型猜**变成**事前可检测、可路由**。是本 sprint 杠杆最高的一刀,且零新依赖。

## 4. 盖章件多模态兜底（新 tier，门控）

**触发**(满足任一):seal pipeline 检出公章且周边文本低置信;OCR-VL 整页低置信;classify 判复杂版面。
**做法**:`pymupdf` 渲染该页为 PNG(已装,`OCR_VL_PDF_RENDER_SCALE` 复用)→ 经 LiteLLM 端点喂 **VL 模型(如 Qwen-VL)** 直接读图出文本/字段 → 过结构校验进底稿。复用 engine.py 现有的 OpenAI 兼容调用形态(OCR_VL_SERVER_URL 同款)。
**边界**:仅按页触发(不全量,贵);VL 模型未配置 → 该页降级 `manual_review`(不静默);结果带 `source=multimodal` 标记,便于审计与抽查。
**依赖诚实**:需 LiteLLM 里注册一个 VL 模型。没有就只到 seal 检测 + 低置信标注 + 转人工——仍比现状强(现状盖章页 OCR 糊了也当真)。

## 5. 招投标链路接入 OCR（思路）

现状(实测):`tender_worker._run_evaluation` → `run_command_json("tender-evaluate", directory_path)` → 模型用 Read **直读** 标书文件。**无 OCR**,且 docstring 自承"标书 40MB+/~18 章节、S2 抽取慢"。在 qwen 网关上,Read 工具循环正是脆弱点。

**接入思路——OCR 作为 S2 前的确定性预处理,底稿注入,不靠模型 Read:**

```
S0 立案 ─ S1 取评分标准 ─[新增 S1.5: 确定性 OCR 预处理]─ S2 抽取 ─ S3 评判 ─ S4 汇总
                                   │
              tender_worker 在 run_command_json 之前调
              pipeline.extract_dir(bid_dir) + build_extraction_block
              → 按章节切分的、带置信度的底稿，注入命令上下文
```

要点:

1. **预处理在 worker 层**:`tender_worker._run_evaluation` 里,`run_command_json` 之前先跑 `extract_dir(directory_path)`,把底稿写进 case 目录(或作为材料块拼进命令上下文)。S1 取评分标准也受益——招标文件的评分表用 native-layout 读,表结构不被 pypdf 揉碎,criteria 才解析得对。
2. **按投标章节 map-reduce**:一标 ~18 章节(商务/技术/资信/报价)。每章节一个抽取单元、独立底稿、可并行——**这正是 G2 plan/拆解真正承重的地方**(把"为未来铺路"变成现在就用)。每章节底稿有界,避免 40MB 整标爆上下文。
3. **置信度 → manual_review,直接接教义**:某评分项依据的章节底稿低置信/被截断 → 该项 `score:null` + `manual_review`(needs_review),**不判 0**。OCR 置信度成了"不可判定项绝不判 0"的客观触发器,而不是靠模型自觉。
4. **印章 → 一致性核验**:盖章页(业绩证明/资质)走 §4 多模态;seal 检出的**单位名称**与投标人名称比对——不一致 = 该业绩项 `manual_review(data_conflict)`(对齐 CLAUDE.md tender 段"拟派负责人/业绩经理不一致"那类一致性风险),证据链同时引两处出处。
5. **网关安全 + 可复现**:OCR 全程确定性 Python、零模型;唯一模型调用是多模态兜底(门控)与 S3 判断。不依赖 Read 工具循环 → 绕开 qwen tool_use 脆弱点,且同一标两次跑底稿一致。

## 6. 落地顺序 + 取舍

| 阶段 | 动作 | 取舍 |
| --- | --- | --- |
| P1 | native `pdf_text`: pypdf → **pymupdf**(find_tables + 版面块) | 零新依赖,立刻吃掉表格;先证明它不够再谈 JVM |
| P2 | **置信度信号** 进底稿 + 文件级/字段级 needs_review | 杠杆最高、零依赖;"识别不清晰"从此可检测 |
| P3 | **盖章/低置信 → 多模态兜底**(门控) | 需 LiteLLM 注册 VL 模型;无则降级人工 |
| P4 | 招投标 worker 接 OCR 预处理 + 按章节 map-reduce | 关掉 round4 的 audit/tender「OCR 未接」耦合缺口 |
| P5 | 评估 **opendataloader-pdf 本地模式** 替换/补强 native-layout | 仅当 pymupdf 表格仍不够;代价是 JVM 进镜像 |

**红线**:不替换 PaddleOCR-VL;不为还没证明必要的表格质量提前引 JVM;OCR 保持确定性(判断仍归模型,验证归代码);多模态是门控的第 4 层不是默认。

## 关联
- round4 `reviews/round5-post-sprint-review.md`:OCR 与审核/评标的耦合缺口(本 sprint P4 关闭)、注入缺口(opendataloader 防注入可顺带补)。
- 现成可复用:`server/ocr/pipeline.py`(extract_dir/build_extraction_block)、`engine.py`(recognize/recognize_seal + OpenAI 兼容端点形态)、`classify.py`(分诊)、已装 `pymupdf`。
