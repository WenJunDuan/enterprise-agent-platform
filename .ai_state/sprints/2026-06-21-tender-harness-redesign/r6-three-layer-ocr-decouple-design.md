# C design · 三层数据结构 + 上传即 OCR 解耦 + 前端三区

> 用户:"招投标审核分基本信息 / 招标信息(原文+OCR后) / 各公司投递文档(原文+OCR后抓点),三点先行考虑";
> "上传即 OCR 解耦,现在 OCR 太慢"。mac mini 实测评标 537s,OCR 串行预处理是慢的大头之一。

## 0. 关键区分(决定设计边界)

| 处理 | 性质 | 何时可做 | 现状 |
|---|---|---|---|
| **OCR**(招标/投标文件→文本底稿) | **确定性**(pymupdf 直读 / 云 PaddleOCR) | **上传时即可**(content-sha256 缓存,性能轮已加) | 评标时才串行跑(慢) |
| **criteria 解析**(评分项/扣分点) | **AI**(agent S1 读招标底稿解析) | 评标时(或首次解析后存项目级复用) | 每家 result 重复解析 |
| **投标抓点**(投标人/报价/业绩/资质) | **AI**(agent S2 读投标底稿抽取) | 评标时 | 在 result.extracted_data |

→ "上传即 OCR" 解耦的是 **OCR 这层确定性预处理**;criteria/抓点的 AI 解析仍在评标,但底稿已 ready,且首次解析结果可回填到层、项目级复用。

## 1. 三层数据结构(地基)

- **基本信息** = `tender_projects`(已有):project_id/tender_no/title/control_price/funding_type/status。
- **招标信息层** = 新表 `tender_project_docs`(project_id PK):
  `{ tender_files JSON, ocr_text(招标底稿), ocr_clarity, ocr_status(pending/running/ready/failed), criteria JSON(首次评标解析后回填,项目级一份), updated_at }`。
- **投标信息层** = 新表 `tender_bid_docs`((project_id, bid_id) PK):
  `{ bidder_name, bid_files JSON, ocr_text(投标底稿), ocr_status, extracted JSON(抓点:投标人/报价/业绩/资质,评标后回填), updated_at }`。

## 2. 上传即 OCR(拆"上传文件"与"提交评标")

当前 `evaluateTenderProjectUpload` = 上传+提交合一 → OCR 仍评标时跑。拆为:
1. **建项目 + 传招标文件** → `POST /tender/projects/{id}/tender-doc` → 落盘 + **后台 OCR**(asyncio,不阻塞) → 写招标层 ocr_text + ocr_status。
2. **加投标人 + 传投标文件** → `POST /tender/projects/{id}/bids` → 落盘 + **后台 OCR** → 写投标层 ocr_text + ocr_status。
3. 前端轮询 ocr_status(各文件 ready)。
4. **点"开始分析"** → `POST .../evaluate` → worker **读招标层+投标层已 ready 的 ocr_text**(命中 content-sha256 缓存,秒过 OCR 阶段) → agent S1/S2/S3 评分,criteria/抓点首次解析回填层。

## 3. 评标读层(替换串行 OCR)

`tender_worker._run_evaluation`:`ocr_preprocess_block` 优先取 `tender_project_docs.ocr_text`+`tender_bid_docs.ocr_text`(已 ready);未 ready/缺失 → **回落原串行 OCR**(兜底,不破现有路径)。

## 4. 前端三区

- **区1 基本信息**:项目表单(名称/编号/控制价/资金类型)。
- **区2 OCR 识别区**:招标层 criteria(评分项 + 扣分点) / 投标审核要点;OCR 后即可展示(不等评标)。
- **区3 投标公司文档**:不展示原文,只展示**评标流式输出**(progressByRid,已做)+ 最终逐项得分。
- 布局:左(区1+2)右(区3 流式),或上下,自适应。

## 5. 分阶段落地(务实)

- **P1 — OCR 预热缓存(最小止血,1-2 处改)**:上传落盘后 `asyncio.create_task` 后台跑 `extract_dir`(填 content-sha256 缓存)。**不改数据模型/前端流程**。但因上传+提交仍合一,预热领先有限 → 仅作过渡验证。
- **P2 — 拆步骤 + 三层表(真解耦,大块)**:新建两层 store + 上传端点(落盘+后台 OCR+写层) + 评标读层(回落兜底) + 前端拆"上传"与"开始分析"。这是用户要的真效果。
- **P3 — 前端三区布局**:区1/2/3 重排,区2 接招标层 criteria。

## 6. 推荐路径

P1 的"合一时预热"领先有限,**不如直接 P2**(拆步骤=真解耦,且三层表是用户要的地基)。但 P2 改动大(数据模型+端点+评标读层+前端流程)。

**推荐:P2(拆步骤+三层表+评标读层)一轮做扎实 → P3 三区跟上。** criteria 项目级复用(首次解析回填、后续家复用)作为 P2 的一部分(顺带治"每家重复解析 criteria")。

## 影响范围

- server/stores:新 `tender_project_docs_store` + `tender_bid_docs_store`。
- server/routes/tender.py:上传端点(tender-doc / bids 落盘+触发 OCR);evaluate 读层。
- server/routes/tender_worker.py:_run_evaluation 读层(回落兜底)。
- server/ocr/pipeline.py:预热接口(复用 extract_dir + cache)。
- agent-front:拆"上传"与"开始分析"两步 + ocr_status 轮询 + 三区布局。
- 测试 + 迁移(新表)。

## 风险与缓解

- **criteria 项目级回填竞态**:多家并发首次评标都想回填 criteria → 用 `INSERT OR IGNORE`/首个写入者赢,后续读已存。
- **OCR 预热与评标重复**:content-sha256 缓存保证只算一次。
- **回落兜底**:层未 ready/OCR 失败 → 评标回落原串行 OCR,不破现有可用路径。
- **迁移**:新表 `CREATE TABLE IF NOT EXISTS`,旧项目无层数据 → 评标回落,渐进迁移。

## 验收

- 上传招标/投标文件后,后台 OCR 跑、ocr_status→ready;点开始分析,评标 OCR 阶段秒过(对比 537s 显著降)。
- 区2 展示招标 criteria(评分项+扣分点),不等评标完成。
- 回归 + codex 配合 review。
