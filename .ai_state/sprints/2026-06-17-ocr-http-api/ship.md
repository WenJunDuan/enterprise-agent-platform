# OCR HTTP API & Frontend Ship Record

> 对话驱动交付，事后补档 2026-06-17。

## Scope

OCR 对外 HTTP API + 前端接入 + 既有分诊缺陷修复。不改审核（audit）链路、不改规则内容。

## Result

### 新增端点

- `POST /ocr/extract` — 纯识别，同步，upload / directory 双模式
- `POST /ocr/fill` — 识别 + 表单回填，同步，仅 UI 演示

### 改动文件

- 后端：`server/routes/ocr.py`(新)、`server/ocr/runner.py`、`server/ocr/classify.py`、`server/ocr/pipeline.py`、`server/routes/upload_helpers.py`、`server/api.py`
- 前端：`ui/src/pages/OcrExtract/*`(新 5)、`ui/src/api/client.ts`、`ui/src/types/index.ts`、`ui/src/App.tsx`、`ui/src/components/Layout.tsx`
- 测试：`tests/test_ocr_routes.py`(新)、`tests/test_ocr_pipeline.py`(新)、`tests/test_ocr_classify.py`、`tests/test_routes_smoke.py`
- 文档：`README.md`（HTTP API 表 audit 4→7 + ocr）

### Bugfix

- classify 文本层误判（`fonts>0` 判据）：真实备案证修前 ocr→无引擎 error，修后 native 直读 570 字符
- pipeline `pages` 字段冲突（`page_count` + `isinstance` 守卫）：native PDF 分支首次真跑暴露的预存 bug

## Verification

- `uv run pytest -q` → **186 passed**
- `uv run ruff check server/ tests/` → All checks passed
- `npm --prefix ui run build` → tsc + vite build 通过
- 端到端（TestClient + 真实样例）：/ocr/extract Excel native 3 表格、扫描 PDF error 隔离、临时目录清理；备案证 native 570 字符；/ocr/fill 200 含 results+block+fill

## Follow-ups

- [P1] extract-result schema 与实际产物对齐（`additionalProperties` + 多字段）
- [P1] 配线上 model key 验 `/ocr/fill` 真识别；扫描件验部署机 PaddleOCR-VL serving
- [P1] `build_extraction_block` 20K 截断砸 136 页合同付款节点（原 review 待办①）
- 代码本轮**尚未 commit**（建议 `feat(ocr): 对外识别/回填 API + 前端接入`）
