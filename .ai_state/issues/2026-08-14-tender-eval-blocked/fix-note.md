---
date: 2026-08-14
type: issue-fix-note
slug: tender-eval-blocked
---

# fix-note

commits: `f5cf7b8`(Bug A) / `983ea1a`(Bug B)，基线 `59b0906`，合入 main `df8b33c`。

## Bug A · 底稿预算按窗口推导 + 内容优先截断

- 新增 `server/tender/context_budget.py`：`derive_default_max_bytes` 从
  `MODEL_CONTEXT_WINDOW` / `CLAUDE_CODE_MAX_OUTPUT_TOKENS` 推导
  `(window - output - 30_000 - window//4) * 3`，缺配置回落 `256_000` B。
  生产配置（1,048,576 / 32,000）推导得 **2,173,296 B ≈ 2.1 MB**（事故底稿 103,335 B
  直接不再触发截断）。`TENDER_CONTEXT_MAX_BYTES` 显式设置仍绝对优先。
  - `30_000` token 脚手架来自实测提示词 55,439 B ≈ 18,500 token + criteria 注入 + 告警块 + 误差
  - `window//4` 预留：评标是 30 轮 agent 循环，模型还要 Read/重识别/扩展思考，底稿不得独占整窗
- `bound_draft_by_content`：章节级识别关键评审节（标题→整章，无标题回落关键词行窗口）并
  **优先足额分配预算**，其余按剩余预算均分，削减处留可见省略标记；标记与分隔符**先从预算扣除**，
  产物严格 ≤ limit。UTF-8 走既有 `errors="ignore"` 手法，测试用 strict decode 锁死。
- **关键词表补「评审方法」「评审程序」**——旧表只有「评审办法」，事故章节「第四章 评审方法和程序」
  一字之差整章漏判。关键词表与选区逻辑与 `context_slim` 首抽瘦身**消重到单点**，否则两处各漏
  一次同一个词就会同时丢掉评分标准。
- RED 7 failed / GREEN 48 passed。

## Bug B · 云 OCR 分片上传

- 新增 `server/ocr/cloud_chunk.py`（分片规划 / 页号换算 / 退避重试 / 节流 / 失败片标注），
  engine 注入 `extract_pdf_subset` 与 `_cloud_fetch_pages`，**不反向 import**。
- `OCR_CLOUD_CHUNK_PAGES` 默认 **50**（实测 50 页 OK / 80 页 400）；
  `OCR_CLOUD_CHUNK_PAUSE_SEC` 默认 2s；重试 2 次、退避 10s/20s，
  可重试状态码 `{400,408,429,500,502,503,504}`（该服务端把限流也回成 400）。
  可重试判定靠 `exc.__cause__` 是否 `HTTPError` 及其 code，**不做消息串匹配**。
- 仅当 `pdf_page_count(path) > 阈值` 才分片，阈值以下逐字节走原路径；
  `pdf_page_count` 返回 `None`（缺 pymupdf/读不出）也回退整份上传——**分片是优化，不是新的失败点**。
- `extract_pdf_subset` 存盘补 `garbage=4/deflate=True/clean=True`（50 页 20.3 MB → 3.24 MB）。
- **页号对齐**（本项最大风险）：页号 = 本片起始页索引 + 片内序号，**不跨片累加**——某片少返回
  几页只影响该片，不会把后续片整体平移。测试锁死 120 页/3 片合并后页号 == 原文档 1..120，
  且内容映射正确、临时子集删净。`page_artifact` 仍是 `cloud_seq`，
  `pipeline._guard_cloud_page_count` 整份页数比对兜底不变。
- 失败片逐页标 `[识别失败]` 并写明页码区间，`partial=True`（doc 层落 partial 不落 failed，
  底稿照常落库）；**全片失败仍抛 `OcrError`**。
- RED（`cloud_chunk` 缺失 → 整模块 ImportError；建模块后 engine 未接线 4 failed；
  压缩项带真 pymupdf 复核 `assert 8650 <= 8151`）/ GREEN 13 passed + 1 skipped。

## 运维侧（已执行）

`.env` 注释掉 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY`（用户拍板：服务器连不上该代理且影响联网测试；
公网端点直连实测可达 api.deepseek.com 0.15s / paddleocr 0.2s），新增 `AUDIT_MAX_TURNS=50`。
备份留 `.env.before-noproxy-0814`。

## 禁区声明

本次改了 `server/ocr/`（`engine.py` + 新增 `cloud_chunk.py`），该目录是 sprint
`2026-08-14-l2-model-routing` 的禁改区（其 `_index.next_action` 写明"勿在 review 前改
server/ocr"）。按 **Hotfix 授权**执行（铁律[门禁即律法] Hotfix 唯一免审议；生产投标文件
完全读不出属 P0）。改动严格限于本 bug 所需，未顺手重构其它部分。

**l2-model-routing 的 design 若假设了 `engine.py` 现状，需重新核对**：
`_recognize_via_paddle_cloud` 已拆出 `_cloud_fetch_pages` / `_cloud_result` 并新增分片分支，
`extract_pdf_subset` 的 save 签名变了，`engine.py` 933 → 970 行。

## 门禁

- pytest FAILED/ERROR 列表与 `/tmp/hotfix-baseline.txt` **diff 为空**
  （34 个基线失败全部是本机缺 `ocr` extra 的 pymupdf ModuleNotFoundError）
- 总数 34 failed / 1374 passed / 4 skipped（基线 34/1352），净增 23 个测试
- `ruff check server tests` 净
- 行数：`engine.py` 933→970、`runner.py` 289→**293**、`context_slim.py` 300→244；
  新增 `cloud_chunk.py` 207 / `context_budget.py` 264

## 遗留待办

- **`server/tender/runner.py` 293 行，离 300 上界只剩 7 行**——下次再动它必须先拆。
- `engine.py` 970 行（基线即远超 300），分片主体已落新模块避免继续撑大；后续若再动 engine
  应优先外移。
