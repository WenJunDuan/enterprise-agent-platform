# 部署机窗口清单（2026-07-20 · 交 codex 执行）

> 代码基线：origin/main **f76ac26**（含 D11 安全硬化 / E4 依赖升级 / D3+D10 直连 / D8 瘦身代码；新能力全部 flag 默认关，部署即有、不改现行为）。
> 注意：`knowledge/` 与 `data/` 不入库（.gitignore）——git pull 不会带规则文件与业务数据，部署机沿用本地已有。

## A · 装机更新（必做）

1. `git pull origin main`（→ f76ac26）。
2. `uv sync --extra ocr` —— **必须带 `--extra ocr`**（纯 `uv sync` 会卸 pypdf/openpyxl/docx，历史坑）；E4 升级了 8 个依赖（cryptography 46→49 等），此步不可跳。
3. 前端 `npm --prefix agent-front run build`（含 D11-R7 tender-review null guard，闭合报告页 500 潜根因）。
4. `.env` 对照 `enterprise-agent.env.example` 核对（部署机 .env 不入库）：
   - 网关：`MODEL_BASE_URL` / `MODEL_AUTH_TOKEN` / `MODEL_NAME`
   - OCR：`OCR_CLOUD`、`OCR_VL_SERVER_URL` / `OCR_VL_MODEL_NAME`（+可选 `OCR_VL_API_KEY`）
   - 租户与网络：`TENANT_KEYS`、`CORS_ALLOWED_ORIGINS`（改成部署机地址）
   - 超时/并发：`AUDIT_TIMEOUT_SEC` / `TENDER_TIMEOUT_SEC` / `MAX_CONCURRENT_AUDITS` / `CLAUDE_MAX_BUFFER_BYTES`
   - 新 flag（**先保持默认关**，验证任务里再开）：`AUDIT_DIRECT_CONNECT` / `TENDER_SLIM_CONTEXT`
5. 起服务：`uv run python -m server.cli serve`（`SERVE_UI_DIST=true` 时后端托管前端 dist）。
6. 冒烟：health 200 + 各跑一单 audit / tender 到 completed。

## B · 模型池装齐（D4 前置，一次窗口装完）

内网隔离部署模型选型限 **DeepSeek / qwen 系**（用户 2026-07-19 拍板，不用 glm）。

| 层 | 模型 | 动作 |
|---|---|---|
| T1 打底 | PaddleOCR 经典管道 | 已部署，确认可用 |
| T2 升级 | PaddleOCR-VL | 确认 `OCR_VL_SERVER_URL` 内网可达（或自托管），跑一档扫描件验通 |
| T3 长程 | Unlimited-OCR（baidu 3B/激活 500M） | SGLang 或 transformers 部署，整本标书解析层 |
| T4 兜底 | 多模态大模型（qwen-vl 类） | **同时是 D10② 前置**——当前网关 deepseek-v4-flash 不支持 vision（image block POC 两次空回答已实证），需网关加挂 vision 模型 |
| 评标基线 | deepseek-v4-pro（V4Pro） | 网关可路由即可，供 C-2 基线标定 |

## C · 验证与基线任务（装机后跑，出数回传）

1. **D8 复测（runbook：`.ai_state/sprints/2026-07-18-d8-transcript-slimming/`）**：真标书上 `TENDER_SLIM_CONTEXT=1` vs `=0` 跑 S7 harness，对比**成本 / 时延 / 一致性跨度 / policy_refs 合规率**四指标。只出数不改默认值（通过标准量化待用户拍，达标后由本机翻转默认）。
2. **D4 前置基线**：`TENDER_EVAL_MODEL` 指 V4Pro，用真实 golden manifest 跑 `server/tender/eval.py` 回归闸，标定 score_consistency 跨次极差基线；顺带填真实 `MODEL_CONTEXT_WINDOW` 重测截断防护（D1 runbook 用户侧待办）。**回传基线数**→ 一致性硬门锁定在本机二次 commit。
3. **D10② vision POC**：T4 vision 模型就位后重跑 image block POC（读附件案件）；通过则本机启动附件预嵌实施。
4. **expense golden 不回退**：带网关跑 `server/audit/eval.py` manifest；可开 `AUDIT_DIRECT_CONNECT=1` 对照直连时延（本机数据：直连中位 16.7s vs CLI 52.8s，供参考）。

## 回传物（写回 .ai_state 或交主 agent 记账）

D8 四指标数据 · V4Pro 一致性基线数 · vision POC 结论 · 冒烟/golden 结果。D4 锁硬门与 D8 默认值翻转均在本机做，部署机只出数。
