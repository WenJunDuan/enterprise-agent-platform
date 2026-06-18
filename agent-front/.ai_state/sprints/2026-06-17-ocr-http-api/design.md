# OCR HTTP API & Frontend Integration Design

> Sprint 2026-06-17 · Path: Feature · 对话驱动开发，事后补档（未走显式 PACE stage 切换）

## Goal

补齐 OCR 的对外 HTTP API（此前只有 skill + 进程内函数，无路由），并在本平台 UI 演示「识别 → 表单回填」全链路：

- 外部系统：上传文档 → 同步返回结构化识别底稿
- 本平台 UI：上传文档 → 识别底稿（左栏）+ 表单回填含付款子表（右栏）一次展示

## Scope

涉及：

- `POST /ocr/extract` 纯识别（同步）
- `POST /ocr/fill` 识别 + 表单回填（同步，仅本 UI 演示）
- `server/ocr/runner.py` 拆出 `map_extraction_to_form` 复用
- 前端 `ui/src/pages/OcrExtract/` 左右分割页面 + `client.ts` 接入
- 修复 classify 文本层误判 + pipeline `pages` 字段冲突

不涉及：

- 异步任务 / 任务存储（纯识别 0 网关往返、回填 1 跳，同步足够）
- 扫描件 OCR 引擎部署（PaddleOCR-VL serving 在部署机，本机标 error）
- 审核域 / 规则库 / 记忆沉淀

## Current State（开工前）

OCR 能力三层但**无 HTTP API**：

1. `.claude/skills/multi-ocr/` — skill，agent 交互式入口（`python -m server.ocr <dir>`）
2. `server/ocr/`（classify/native/engine/pipeline/runner）— 确定性流水线 + `run_doc_extract` 进程内 async
3. `server/routes/` — 仅 `/audit` + `/health`

缺口：外部系统无法单独调 OCR；前端无 OCR 页面。

## Design

### 1. POST /ocr/extract（纯识别，同步）

- 鉴权 `verify_tenant`；upload（multipart）/ directory（data/ 下 JSON）双模式
- `run_doc_recognize` 经 `asyncio.to_thread` 跑确定性流水线（OCR 引擎 `predict` 同步阻塞，不能堵事件循环）
- 并发闸 `MAX_CONCURRENT_OCR`(2) + 硬超时 `OCR_EXTRACT_TIMEOUT_SEC`(120s)
- 每文件错误隔离（pipeline 内 try，单个失败标 `kind=error`，整体仍 200）
- 上传件识别后清理临时目录；directory 模式不动用户目录
- 返回 `{request_id, results, block}`

### 2. POST /ocr/fill（识别 + 回填，同步）

- 仅供本平台 UI 演示「识别 → 回填」，非给外部系统
- multipart：files + `form_schema`（目标表单定义，注入 prompt 指导映射）
- `run_doc_recognize`（拿 results/block）+ `map_extraction_to_form`（一次模型映射 → form-fill 契约）
- 一次响应同时给底稿（左栏）和回填（右栏）：`{request_id, results, block, fill}`
- 需模型网关；映射阶段失败 → 502

### 3. runner 重构（DRY）

把 `run_doc_extract` 的映射循环抽成 `map_extraction_to_form`（识别底稿 → form-fill，含契约校验 + 重试）；`run_doc_extract` = `run_doc_recognize` + `map_extraction_to_form` 编排。`/ocr/fill` 直接组合两者，以一次响应同时拿 results 与 fill。

### 4. 前端 OCR 页面

- `ui/src/pages/OcrExtract/`（index / UploadPanel / ResultPanel / shared / mockData）
- 左 40% 上传 + 识别底稿 / 右 60% 回填（字段带置信度徽标、付款子表、需复核 banner）
- 「开始识别」真调 `/ocr/fill`（需 key）；「加载示例」mock（免 key 预览）
- 路由 `/ocr` + 侧边栏「文档识别」导航

### 5. classify / pipeline 修复

- classify：`has_text = fonts>0 and kb/page<200` → `fonts>0`（字节大小是噪声，电子证照含印章图被误判扫描件、白送 OCR）
- pipeline：classify 的页数(int) 与 OCR 引擎 pages(list) 同名 → `_render_body` 迭代 int 崩；页数改名 `page_count` + `isinstance(pages, list)` 守卫

## API Summary

| 方法 | 路径 | 输入 | 输出 |
| --- | --- | --- | --- |
| POST | `/ocr/extract` | upload(files) / directory(JSON) | `{request_id, results, block}` |
| POST | `/ocr/fill` | multipart: files + form_schema | `{request_id, results, block, fill}` |

## Testing Strategy

- `tests/test_ocr_routes.py`：/extract（upload/directory/auth/415/400/manual 隔离）+ /fill（结果结构 / 缺 schema / auth，映射阶段 mock 模型）
- `tests/test_ocr_pipeline.py`：`build_extraction_block` 对 page_count(int) / pages(list) / tables / error 四种
- `tests/test_ocr_classify.py`：加「大图电子证照判 native」回归
- `tests/test_routes_smoke.py`：路由基线锁加 `/ocr/extract` + `/ocr/fill`
- 端到端（TestClient + 真实样例）：备案证 /ocr/extract native 直读 570 字符；/ocr/fill 200 含 results+block+fill

## Risks

1. `extract-result.schema.json` 是 `additionalProperties:false`，但实际 pipeline 产物多 `container`/`handler`/`page_count`/`has_text_layer`/`reason` 字段；`/ocr/extract` 当前**不校验** results 故不报错，外部严格按 schema 解析会见多余字段 → 待对齐（出口投影 or 改 schema）。
2. `/ocr/fill` 依赖模型网关，本机无 key 时只能 mock；扫描件依赖部署机 PaddleOCR-VL serving。
3. `pipeline.build_extraction_block` 每文件 20K 字符硬截断，136 页扫描合同付款节点若在尾部会被截 → POC 必碰（原 review 待办①，仍未解）。
