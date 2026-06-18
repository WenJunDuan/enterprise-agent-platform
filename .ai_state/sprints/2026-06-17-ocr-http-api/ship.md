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

- ✅ extract-result schema 对齐（additionalProperties + 补字段 + kind enum + 一致性测试）
- ✅ build_extraction_block 截断显式标记 + 上限可配（OCR_MAX_FILE_BLOCK_CHARS）
- ✅ 代码已 commit（feat + docs + fix×4）
- ✅ 生产真识别验证通过（mac mini 0618b4，7 文件全成功含扫描件 OCR）——见末尾段

## 遗漏修复 + codex 四轮交叉 review（2026-06-17 续）

事后检查上阶段遗漏（schema 债 / 截断 / commit / 真识别）设为 goal 解决，再经 codex
四轮独立交叉 review，共 14 findings 全修：

- 轮1（5）：畸形 JSON→400、上传同名去重、path 投影 basename、软超时不删目录、前端渲染 pages
- 轮2（2）：孤儿目录 maintenance 兜底、directory 保留相对路径（均为轮1修复引入的副作用）
- 轮3（4，含 P1）：软超时根治（识别在信号量内 await 完成）、font-only PDF 回退 OCR、
  解析失败 per-file 隔离、vite 代理 /ocr
- 轮4（3，含 P1 安全）：directory symlink 任意文件读取防护、maintenance known 用
  PROJECT_ROOT 解析（防误删）、UI note 改附加 banner

验收：测试 170→200，ruff / 前端 build 全过，6 个 commit（feat + docs + fix×4）。
**注**：findings 趋势 5→2→4→3，**未收敛到 0**，且多个是修复前一轮引入的——交叉 review
的修复本身需再 review，应按"连续一轮无 P0/P1/P2"收敛而非固定轮数（详见 compound 教训）。

## 生产真识别验证 + engine.py PDF 渲染修复（2026-06-18）

mac mini（Apple container，镜像 `audit-agent:0618b4`，PaddleOCR-VL serving 经 litellm
`10.200.52.4:4000/v1`）上 `/ocr/extract` 实测 7 个文件**全部识别成功**（HTTP 200，0 error）：

| 文件 | kind/route | 耗时 |
|---|---|---|
| 项目库.xlsx / 项目管理功能清单.xlsx | excel/native | 0.06–0.38s |
| 备案证.pdf（文本层）| pdf_text/native | 0.01s |
| 河道护栏 概算/标底/立项批复.pdf（扫描 1–2 页）| ocr/ocr | 2.7–5.7s |
| 供电工程/金欣F外线.pdf（扫描 12 页）| ocr/ocr（12 页全识别）| 50.4s |

性能：native 秒级；扫描件 ~3–5s/页（含网关往返）。多页大文档（市政 27 页 / 金欣F 136 页）
按比例更久，同步调用须把客户端超时设足。

**关键依赖修复（`2a7d2d5` engine.py，mac mini 回流并已汇入本仓库）**：远端 VLM（OpenAI
兼容端点）不接受 `application/pdf` 会 400；改为 PyMuPDF 先把 PDF 每页渲染成 PNG、以
`data:image/png` 调用。配套 `pymupdf` 依赖 + Dockerfile OCR 层 + `tests/test_ocr_engine.py`。
两端不再分叉（原"mac mini 适配未回流 git"的债随此解决）。

至此 OCR 对外能力（/ocr/extract 纯识别 + /ocr/fill 回填，502 已由 schema 驱动归一化修复）
在生产环境端到端验证通过。
