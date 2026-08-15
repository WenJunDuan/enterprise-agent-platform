---
sprint_slug: "2026-08-14-l2-model-routing"
path: "Feature"
created: "2026-08-14"
last_updated: "2026-08-14"
roadmap: "2026-07-doc-intelligence"
roadmap_item: "D4"
executor: "design 主 agent；impl 待 Fable 5 review PASS 后再派"
depends_on: "用户 2026-08-14 拍板：先扩建本仓 server/ocr，不先拆独立服务"
---

# Design — D4a 进程内 L2 引擎注册表（不拆服务、不编阈值）

## 背景

D4 原定义是把 `engine.recognize()` 的 env if/elif 换成 EngineRegistry + 五级路由梯
（compound/2026-07-02-decision-ocr-routing-ladder.md）。2026-07-20 倾向改成「独立 OCR
服务 + 本项目只调一个 API」（compound/2026-07-20-decision-ocr-as-standalone-service.md，
status=leaning）。用户 2026-08-14 拍板：**先在本仓 `server/ocr/` 扩建路由，业务侧继续只调
本工程 OCR**；独立服务留作二期，不是这一刀。

现状（2026-08-14 读源码坐实）：

- 全局调用都是进程内：`tender/runner`、`tender/doc_pipeline`、`audit_worker`、
  `routes/ocr.py`、`ocr_job_worker` 只认 `extract_dir` / `ocr_preprocess_block` /
  `prewarm_and_report` / `run_doc_recognize`。`engine.recognize` 的唯一生产调用方是
  `pipeline.py:28`。
- **T0 已在 L1**：`classify` 输出 `native|ocr|convert|manual`，pipeline 先直读，混合 PDF
  再 `extract_pdf_subset` 补扫描页。`recognize()` 只处理「已经决定要 OCR」的文件。
- **L2 还是开关**：`engine.recognize:905-920` 按 `OCR_CLOUD` →
  `OCR_VL_SERVER_URL && !OCR_VL_USE_PADDLE_PIPELINE` → 本地 Paddle pipeline。Tesseract
  不是可选引擎，是 VLM 可恢复失败后的整段降级（H3 已定，本 sprint 不改）。
- T1 经典 PaddleOCR、T3 Unlimited-OCR、T4 系统大模型 **没有适配器**。本机也没有画像数据。
- `cache._engine_fingerprint`（cache.py:33-45）已含 `OCR_CLOUD` / `OCR_VL_MODEL_NAME` /
  `OCR_VL_USE_PADDLE_PIPELINE`，不含「路由策略版本」。
- 行数基线（`wc -l`，2026-08-14）：`engine.py` 933、`pipeline.py` 868、`cache.py` 116。
  `engine.py` 已越 300 行，H3 明确「不拆 engine.py」。相关 OCR 单测 collect = **194**
  （`test_ocr_engine*` + `test_ocr_pipeline*` + `test_ocr_classify` + mixed_pdf +
  page_provenance + native_formats）。

## 目标

1. 用可单测的 `EngineRegistry` + `select_backend()` 替换 `recognize()` 顶部三段 if/elif，
   **默认选择与现网真值表逐字节等价**。
2. 五级梯在注册表里有名字和可用性；T1/T3/T4 标 `unavailable`，禁止假装会升降级。
3. 识别产物带 `routing` 观测字段；缓存指纹纳入策略版本，换策略不会命中旧缓存。
4. tender / audit / `/ocr/jobs` **零改**。

## 非目标

- 不新建 HTTP OCR 服务，不在本进程再包一层 HTTP。
- 不把 `docstructure` / RAG / context_slim 搬进路由（那是底稿消费）。
- 不重写 `engine.py` / `pipeline.py`；不改 T0、不改 Tesseract 整段降级、不改 `run_seal` 默认。
- 不接入 T1/T3/T4 真后端，不写未实测的置信阈值 / 自动升档。
- 不跑 D1 golden / 真评标（无新模型窗口）。独立服务拆分 = D4c，另开 sprint。

## 已调研的现成方案

检索：`OCR engine routing library python`、PaddleOCR / Tesseract / EasyOCR / RapidOCR /
Surya / ocrmypdf / Docling（2026-08-14 WebSearch）。

| 候选 | 判定 | 理由 |
|---|---|---|
| ocrmypdf | 否决 | PDF+Tesseract 封装，不覆盖本仓 24 格式、页锚契约、现有三后端 |
| Docling / unstructured | 否决 | 替换整层抽取，与 0730 刚验收的摄取梯冲突，集成面远超 Feature |
| RapidOCR / EasyOCR / Surya | 否决（本期） | 都是**引擎**不是路由；加引擎属 D4b |
| Paddle PP-Structure / 自带 pipeline | 部分采用 | 继续当 T2 后端实现，不当跨引擎注册表 |
| 自研 `routing.py` | **采用** | 无库能在不换契约的前提下给现有 `_recognize_via_*` 做可测选择；增量约一个纯函数模块 |

## 备选

- **A 本仓进程内注册表（选中）**：调用方不动，种子仍是 `server/ocr/`，独立服务拆分时只换
  `recognize()` 实现。代价：paddle/GPU 仍绑在审核进程（本来就是现状）。
- **B 现在拆独立服务**：2026-07-20 终态。现在缺的是路由本身和模型池，不是 HTTP 壳；先拆会
  把未完成的 L2 搬到第二个部署单元。
- **C 本进程 FastAPI 自调 `/ocr`**：零隔离、多一种失败，否决。

## 关键决策

### KD0 · 独立服务仍是终态，本期只做种子

不改 2026-07-20 的 API 形状（文件字节 → 带页锚底稿）。改的是**时机**：先让
`select_backend()` + 现有三后端成为可抽出的门面。D4c 再把 `routing`+`engine`+`pipeline`
T0/T1 边界挪到独立进程。H3「不要进程内大拆 engine / FITZ 精修」仍然成立——本期只抽出
`recognize()` 顶部约 15 行分发，不拆锁、不拆渲染。

### KD1 · `recognize()` 默认选择 ≡ 现网真值表

```
OCR_CLOUD=1                              → paddle_cloud
OCR_VL_SERVER_URL 且未开本地 pipeline    → openai_vlm
否则                                     → paddle_vl_pipeline
```

`select_backend(env, registry) -> RoutingDecision`。`recognize()` 只按 `decision.engine_id`
调已经存在的 `_recognize_via_paddle_cloud` / `_recognize_via_openai_compatible` /
`_recognize_via_paddle_pipeline`。缺依赖仍由这些函数抛 `OcrDependencyError`，选择层不吞。

### KD2 · 注册表有名字，没有的引擎不可选

| engine_id | 梯 | 本期 |
|---|---|---|
| （T0 直读） | T0 | 不进 `recognize()`，仍在 classify+pipeline |
| `paddle_ppocr` | T1 | 注册，`available=False` |
| `paddle_cloud` / `openai_vlm` / `paddle_vl_pipeline` | T2 | 现网三后端 |
| `seal` | T2s | 侧车，只经现有 `recognize_seal` + `run_seal` |
| `unlimited` | T3 | 注册，`available=False` |
| `system_vlm` | T4 | 注册，`available=False`（与 `OCR_VL_*` 不是同一配置面，禁止偷换成 T2） |

对 `available=False` 的 id：测试断言 `select_backend` 永不返回它。禁止加
`OCR_UPGRADE_MIN_CONFIDENCE` 之类未画像阈值。页级升档函数签名可以预留（入参
`page_confidence` + 已选引擎，返回「仍用原引擎」），默认实现恒为 no-op。

### KD3 · 观测字段进产物，不改调用方契约

`recognize()` 返回值增加：

```
routing: {engine_id, tier, reason, policy: "v1-env-parity"}
```

现有 `engine` / `degraded` / `partial` / `pages` 字段含义不变。pipeline 已经 `{**route, **recognize()}`，
观测字段自动出现在底稿旁路，tender/audit 不读可以当忽略。

### KD4 · 缓存指纹加策略版本，不靠 bump 藏行为

`_engine_fingerprint()` 追加 `policy=v1-env-parity`。换策略或将来启用 T1 会自动 miss。
`_CACHE_VERSION` 保持 `v6`（H2 产物结构未变）。现有 `test_ocr_pipeline.py` 对 `v6` 的断言不改。

### KD5 · 修改面锁死三文件 + 新测试

生产代码只动：

1. **新建** `server/ocr/routing.py`（≤150 行）：`EngineSpec`、默认 registry、`select_backend`、
   no-op `maybe_upgrade`。
2. **`engine.recognize`**：删顶部 if/elif，改为 `decision = select_backend(...)` 再分发；
   把 `decision` 写入返回值。净增目标 ≤30 行。
3. **`cache._engine_fingerprint`**：加 policy 段。

禁止改 `pipeline.py` / `tender/` / `audit/` / routes。`routing.py` 不得 import
tender/audit/routes（现有 layering 守卫覆盖）。

## 影响范围

| 文件 | 动作 |
|---|---|
| `server/ocr/routing.py` | 新建 |
| `server/ocr/engine.py` | `recognize()` 分发改调用 registry |
| `server/ocr/cache.py` | fingerprint 加 policy |
| `tests/test_ocr_routing.py` | 新建：真值表 + unavailable 永不选 + fingerprint 含 policy |
| 既有 `test_ocr_engine*` / pipeline | 应全绿，不断言新字段也可过 |

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| 分发改写后默认后端漂了 | KD1 真值表单测；既有 fallback/retry 测试继续 monkeypatch 同一组 env |
| 未画像就自动升档，质量暗变 | KD2：无第二可用引擎则 no-op；不加阈值 env |
| `engine.py` 继续膨胀 | 新逻辑只进 `routing.py`；engine 只留一层分发 |
| 与 2026-07-20「先拆服务」文案冲突 | KD0 写明改时机不改终态；Fable 若否决 KD0 再停 |
| 旧缓存命中新策略 | fingerprint 含 policy，自然 miss |

## 验收标准

- [ ] **AC1** `select_backend` 对 KD1 三行真值表（含空 URL、CLOUD=1 优先）全部测过，与
      `engine.recognize:905-920` 今日行为一致。
- [ ] **AC2** `paddle_ppocr` / `unlimited` / `system_vlm` 在默认 registry 下 `available is False`，
      且任意 env 组合都不会被选中。
- [ ] **AC3** `recognize()` 成功路径返回含 `routing.policy == "v1-env-parity"` 与对应
      `engine_id`；失败路径仍只抛既有 `OcrError` / `OcrDependencyError`。
- [ ] **AC4** `_engine_fingerprint()` 字符串包含 `v1-env-parity`；只改 policy 标签则
      cache key 变化（单测）。
- [ ] **AC5** 生产调用方零改：`git diff --name-only` 不得出现 `server/tender/`、
      `server/audit/`、`server/routes/`。`server/ocr/pipeline.py` 不得出现在 diff。
- [ ] **AC6** 回归：下列文件 collect 数 ≥ 194，且 `uv run pytest -q` 这些文件无新增失败
      （基线 2026-08-14 collect=194）：
      `tests/test_ocr_engine.py` `tests/test_ocr_engine_fallback.py`
      `tests/test_ocr_engine_retry_gate.py` `tests/test_ocr_pipeline.py`
      `tests/test_ocr_classify.py` `tests/test_ocr_native_formats.py`
      `tests/test_ocr_page_provenance.py` `tests/test_ocr_pipeline_mixed_pdf.py`。
- [ ] **AC7** `routing.py` ≤150 行；`engine.py` 相对本 sprint 起点净增 ≤30 行（豁免其 933
      行存量，不在本期拆文件）。

## Done Contract

1. `uv run pytest -q tests/test_ocr_routing.py` → exit 0，覆盖 AC1/AC2/AC4。
2. `uv run pytest -q` AC6 文件列表 → exit 0，无新增 failed。
3. `uv run ruff check server/ocr/routing.py server/ocr/engine.py server/ocr/cache.py` → exit 0。
4. `git diff --name-only` 满足 AC5；`wc -l server/ocr/routing.py` ≤150。

## 开放问题

无。用户已拍「先扩建本模块」。T1/T3 真接入、画像阈值、独立服务拆分都不在本期决策面。

## Key Decisions

1. **进程内种子，服务后拆**（KD0）——缺的是可测路由，不是第二个进程。
2. **默认行为冻结为现网真值表**（KD1）——没有画像就没有资格改质量。
3. **未装引擎只注册不选择**（KD2）——避免空壳 if 变成假升降级。
4. **观测 + 缓存策略版本**（KD3/KD4）——调用方不读也能以后对账。
5. **三文件锁死**（KD5）——对齐「全局仍调本工程 OCR」。

## PR Plan

单 PR（Feature，可两个 commit）：

1. `test(ocr): add L2 routing truth table` — 先红：`select_backend` 不存在。
2. `feat(ocr): EngineRegistry env-parity selector` — `routing.py` + `recognize()` 改分发 +
   fingerprint policy。

不依赖其它 PR。D4b（T1/T3 适配器 + 部署机画像）/ D4c（抽服务）另开 sprint，依赖本 PR 合入。

## Round 1 · Critic Findings

（待 Fable 5 review 写入。本档为送审稿，尚未跑 Athena critic。）
