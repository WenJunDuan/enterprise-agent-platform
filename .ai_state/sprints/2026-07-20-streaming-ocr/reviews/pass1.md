# D9 streaming-ocr · Review Pass 1

> stage=review · 2026-07-20 · base=b2c133d · 20 文件/2876 行
> reviewer + spec-compliance 并行返回，主 agent 合并 + 独立确认。**VERDICT=REWORK**（confirmed P0 F1）。

## VERDICT: REWORK

一个 confirmed P0（F1 流式内容保真）阻塞。其余维度（correctness 主干 / buffer-then-fire / progress 单调 / G1·G2 信任边界 / 安全 / 前端质量 / spec 覆盖）均实证无 P0/P1。F1 修复后重跑 review（pass2）。

---

## Findings

### F1 [P0] Correctness — 流式回调在 native→OCR 回退路径产生重复/过期页级单元
**File**: `server/ocr/pipeline.py:309-356`（`_dispatch_extract`）+ `_augment_mixed_pdf_blocks`(:157-200)
**主 agent 独立确认（读 merge 后代码）**：
- line 320 `_call_native_read(path, on_page)` 对 pdf_text handler **无条件先逐页触发**（扫描页=空白文本），此时尚未决定是否回退 OCR。
- **font-only 回退**（:321-330）与**混合 PDF 整份回退**（:342-350）随后用 `on_page` 对**同一页号**再触发真实内容 → units.jsonl 每页两条（先空后真），前端 `groupUnitsByFile` 不去重 → 同一「第N页」并列渲染两份。
- **混合 PDF 子集增强成功**（:339-341）`_augment_mixed_pdf_blocks(...)` **未传 on_page** → 云 OCR 修正后的扫描页内容永不推流；前端到 completed 停轮询后**永远看不到**正确内容，只见空白版。
**失败场景**：font-only 扫描 PDF（代码注释自称常见）/ 混合数字+扫描 PDF——D9 核心目标场景。页锚保真守住，**内容保真被破坏**。
**测试缺口**：`test_ocr_streaming_callback.py` 无 mixed_pdf/font-only/fallback 用例；`extract_one` 页锚测试只走纯 native 可抽文本 PDF，从未触达「native 后又调 OCR/augment」交互路径。设计侧遗漏（design Round2 T1 增补未覆盖此交互），非纯实现疏忽。
**建议修复**（主 agent 采纳 a+c 组合）：
- (a) pdf_text handler 的 native 读取**不即时触发 on_page**（先读不流），待 dispatch 分支确定最终内容后统一发；
- 纯 native 路径（:351 return 前）从最终 `native["blocks"]`（逐页、页锚保真）发页级事件；
- font-only / 混合整份回退：只由 OCR 侧 `on_page` 发（真实内容，无重复）；
- (c) 混合子集增强成功：从 `augmented["blocks"]`（修正后内容+真实页号）发页级事件。
- 该重构使页级发射**全程锁外**（比原 buffer-then-fire 更安全，F2 critic 约束天然满足）。

### F2 [P1] Test risk — F1 场景零回归防护
`test_ocr_streaming_callback.py` 缺 font-only 回退 / mixed 子集回退 / mixed 子集成功三路径的 `on_unit_complete` 序列断言（重复检测 + 内容最终一致性）。**修复必带**：三个用例直接复现并守卫 F1。

### F3 [P2] INFO — 前端轮询 catch(()=>null) 吞所有 fetch 失败（含瞬时抖动）当终态
`ocr-workbench-page.tsx` jobQuery，与既有 `use-tender-review-page.ts:491` 同构，design Round2 显式要求继承此写法（F4 应答）→ **平台既有共享弱点，非本轮新增**，不计入判定，记录供后续统一治理。

### 疑点判定（非 finding）：`_call_native_read`/`_call_recognize`/`_call_recognize_with_seal` 三包装
reviewer 判**非过度设计**：删后默认路径多传 on_page=None 违反 T1 零 kwarg 约束，且存量旧签名 monkeypatch mock 会真实报错（会失败的真实调用方）；三处对接不同下游签名，合并只增间接性。**维持现状不改**。

---

## spec-compliance（并行返回，建议 PASS）
- MISSING 0 / scope-creep 0 / 3 个合理 refactor（新文件 SRP 拆分 ocr_jobs/ocr_job_worker/ocr_job_store、api 类型对齐契约、smoke 路由基线 +2 行）。
- DEVIATED 1（minor 非阻塞）：**D1** `/ocr/jobs` 不收 `form_schema`（反过度工程，无消费方）+ 用 `request_id` 而非 design 文字的 `job_id`（对齐平台 audit/tender 既有命名）。自洽简化，不影响任一 T1-T5 验收，仅记录。
- T1-T5 + F1-F6 + G1/G2 全部 COVERED（矩阵见 spec-compliance 返回）。**注**：其覆盖矩阵未捕获 reviewer F1 的动态交互缺陷（spec 看静态覆盖，reviewer 看运行时路径），两者互补。

---

## 已实证无 P0/P1 的维度（reviewer + 主 agent）
默认 None 零字节透传 / buffer-then-fire 锁外（native+paddle，断言 locked()==False）/ progress 锁内单调（并发 12 文件 append 完整性）/ 缓存命中补 from_cache / 0 单元即 completed / G1 units.jsonl 排除 / G2① progress 格式解析失败不 500 / G2② 路径服务端派生+跨租户 404 / F5 recover_stale 不碰 units.jsonl / multipart 复用 sanitize+validate 先例 / 无硬编码密钥 / SQL 参数化+表名白名单 / 前端 eslint+tsc+bun-test 净、reducer 非空壳断言。后端 952 passed/2 skip、ruff 净、前端 121 绿。

## 下一步
回 impl 出 pass2：generator（worktree）修 F1（a+c 组合重构 `_dispatch_extract` 页级发射时机）+ F2 三个回归用例。修完全量回归 + 重跑 review（reviewer+spec）→ evaluator。
