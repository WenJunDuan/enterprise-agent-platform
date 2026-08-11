---
sprint_slug: "2026-08-11-ocr-concurrency-degrade"
path: "System"
created: "2026-08-11"
last_updated: "2026-08-11"
executor: "generator subagent model=opus, isolation: worktree (红区)"
depends_on: "H1 (doc 状态枚举接口对齐，可并行开发合并前对齐)"
---

# Design — H3 并发与降级治理：页级重试/并发闸 + degraded 不落 ready + executor 治理 + 双跑消解

## 背景

实跑症状"两个标并发跑，第二个标大量缺结果"。机制链（2026-08-11 评审，主 agent 抽查坐实）：

1. 袋1 先占满三层全局队列：LibreOffice 全进程 `BoundedSemaphore(1)`（office_convert.py:39-41，
   90s 超时不含排队）、`FITZ_LOCK`（native.py:269-294 整本直读持锁，实测可达分钟级）、asyncio
   默认 executor（4 核 ≈8 线程，分钟级 OCR 调用占满后**连状态写库都排队**）。
2. 袋2 预热 360s 超时（runner.py:69）→ 评标回落 inline 全量重 OCR（runner.py:227-234），预热
   不取消 → 同批文件双份流水线，负载翻倍正反馈（runner.py:97-99 非 ready 一律回落）。
3. 逐页 VLM 无客户端并发闸（`OCR_VL_MAX_CONCURRENCY` 只接了本地 Paddle，engine.py:122-123；
   openai-compatible 路径 engine.py:419-487 直接 urllib 无信号量）→ 预热 4×6 + inline 6 线程
   可 ~30 路并发打网关 → 页级超时暴增。
4. 任意一页 VLM 一次可恢复失败 → 该文件**其余全部页永久降级 Tesseract 无重试**
   （engine.py:529-548）；降级低质文本非空即判有效、以 `ocr_status=ready` 永久落库
   （doc_pipeline.py:425-435）→ 之后永不重跑 VLM。KD3(0730) "degraded 不落缓存"只挡了文件
   缓存层，漏了 doc 层 DB。
5. 渲染中途结构化错误丢弃整文件含已成功页（engine.py:519-565 迭代器异常冲出循环 →
   pipeline.py:527-533 整份 `[识别失败]`）；`is_ocr_text_valid` 任一行有效即整包 ready
   （pipeline.py:607-629）——部分失败对任务状态机不可见。
6. 超时不杀底层线程（ocr_job_worker.py:31-33 自认），failed 任务的僵尸负载继续争抢资源。

架构评审拍板：FITZ/LO per-task 隔离精修**不做**（并入 OCR 独立服务迁移，进程内修是白修）；
本 sprint 只做平台侧残留三件（executor / 状态粒度 / 双跑消解）+ 降级语义修复。

## 目标

1. 单页 VLM 可恢复失败先重试 1 次再降级；降级结果不再以 ready 永久落库。
2. doc 层状态增 `degraded` / `partial` 档，评标入口对非 ready 底稿显式决策，部分失败对状态机可见。
3. openai-compatible VLM 路径接入客户端并发闸。
4. prewarm / inline OCR 移出 asyncio 默认 to_thread 池，状态写库不再被 OCR 饿死。
5. 预热超时不再触发 inline 双跑。
6. 渲染中途失败保留已完成页（partial 底稿），不整份报废。

## 非目标

- 不做 FITZ_LOCK / LO 信号量的 per-task 隔离与公平调度（OCR 独立服务迁移承接）。
- 不拆 engine.py（887 行基线豁免，迁移期重构）。
- 不实现任务级抢占/取消已在途的底层线程（结构上需要服务化才能干净做到；本 sprint 只消灭
  "主动制造双跑"这一自伤项）。
- 不改 Tesseract 兜底本身的质量与"outage 例外"定位（0730 KD3 决策维持）。

## 已调研的现成方案

executor 治理用 stdlib `concurrent.futures.ThreadPoolExecutor` + `loop.run_in_executor` 即可，
不引第三方（anyio CapacityLimiter 等价但项目未用 anyio 生态，引入不划算）；VLM 并发闸用
`threading.BoundedSemaphore` 与既有 office_convert 同构。无自研轮子。

## 关键决策

### KD1 · 页级重试与降级范围

- `_recognize_via_openai_compatible` 单页 VLM 命中可恢复错误（现有 OcrDependencyError 归一集）：
  同页 bytes 重试 1 次（固定 2s 退避；重试预算计入该页 90s deadline 剩余量，不超页预算）。
- 重试再失败 → 维持现状"该页起整文件降级 Tesseract"（0730 设计的页序连续性约束不变），但结果
  `degraded=true` 语义从"仅缓存层不落"扩展为**doc 层同样不落 ready**（KD2）。
- 不做每页独立"VLM/Tesseract 混跑"（页间引擎抖动比整段降级更难解释，且违反 0730"页只发一次"
  简单性决策）。

### KD2 · doc 层状态粒度

`tender_bid_docs.ocr_status` 枚举扩展：`ready | degraded | partial | failed | pending | running`。

- `degraded`：底稿完整但含 Tesseract 降级段（engine 结果 degraded=true 透传到 doc_pipeline）。
- `partial`：目录级部分文件失败（`is_ocr_text_valid` 改为返回逐文件明细，
  `run_bid_doc_ocr` 落库带 `failed_files: [...]`）。
- 评标入口（runner）对非 ready：`degraded/partial` → 先自动重跑**一次**该 doc 的预热 OCR
  （只重跑失败/降级文件，命中缓存的成功文件零成本）；重跑后仍非 ready → 评标继续但结论
  强制注入 warning（"以下文件底稿降级/缺失：..."），依赖这些文件的评分项由模型按现行
  evidence 缺失规则处理——**不静默**。`failed` → 阻塞报错。
- H1 接口对齐：横比完成态判定只认 ready/degraded/partial 结论中**已成功产出**的结果行，
  枚举值命名与 H1 保持一致（合并前对齐）。
- **前端硬门同步**（Round1-F1，P0）：doc 状态有独立前端消费点，新枚举不进前端会把用户锁死——
  `use-tender-review-page.ts:289-292` 终态集只认 `ready|failed`（degraded → 轮询永不终止）、
  `:328-330` canStart 要求全家 ready（"开始分析"永久禁用）、`api.ts` OcrStatus 类型拒新值、
  `analyzing-view.tsx:456` 状态 label。四点全部拉进修改面：终态集 += degraded/partial；
  canStart 接受 degraded/partial（带告警样式提示"底稿降级/部分缺失，结论将标注"）；类型与
  label 补全。否决备选"路由兼容映射对外冒充 ready"：对外撒谎状态与本 sprint"部分失败对状态机
  可见"的目标自相矛盾。

### KD3 · VLM 客户端并发闸

进程级 `BoundedSemaphore(OCR_VL_MAX_CONCURRENCY)`（默认 4，env 已存在只是没接对地方）包住
`_call_openai_compatible_vlm` 的网络调用段（含重试）。信号量等待不计入页 deadline（与 LO 排队
同坑不同修：页 deadline 语义是"识别耗时"，排队饿死由 KD4/KD5 的源头减压解决；闸的目的是保护
网关不被 30 路并发打崩，从源头减少页级超时）。

### KD4 · executor 治理

- 新建模块级命名池：`_OCR_EXECUTOR = ThreadPoolExecutor(max_workers=OCR_EXECUTOR_WORKERS 默认 4,
  thread_name_prefix="ocr")`。`prewarm_and_text`（doc_pipeline.py:338/425）与 inline
  `ocr_preprocess_block`（runner.py:232）改走 `loop.run_in_executor(_OCR_EXECUTOR, ...)`。
- DB 读写、轮询等短调用留在默认 to_thread 池——分钟级阻塞与毫秒级调用分池，状态更新不再被饿。
- 不加更多池/配置项（反过度工程：只治"分钟级调用污染默认池"这一个实测病灶）。

### KD5 · 双跑消解

`_wait_doc_layer_ready` 超时后**不再无条件回落 inline**：

- **in-flight oracle 定义**（Round1-F5，预热是 upload 端点起的后台任务、无任务注册表，
  不能凭空"查任务状态"）：oracle = doc 行 `ocr_status=running` **且** `updated_at` 距今
  < staleness 阈值（`OCR_PREWARM_STALE_SEC` 默认 300s，落 config.py；预热流水线以 **doc 级
  ticker 周期性 touch updated_at，周期 60s ≪ 阈值**——不得按"每处理完一个文件才 touch"实现，
  单个大文件超 300s 即假 stale → inline 双跑复活，恰是本 KD 要杀的病灶（critic R2-P2b）。
  touch 义务落 doc_pipeline + stores，本 sprint 一并落实）。stale running（进程重启遗留，doc_pipeline.py:371 注释
  自证此形态）按 failed 处理。
- oracle 判 in-flight → 继续等待（上限改为从 tender 总预算派生：
  `min(TENDER_TIMEOUT*0.5, 剩余预算-评标保留量)`，替代拍脑袋 360s；轮询间隔不变）。
  **派生上限到期仍 in-flight → 按 failed 走 inline 回落一次 + 结论 warning**（不无限等）。
- oracle 判 failed/stale/不存在 → 走 inline 回落（此时无双跑）。
- 等待期间每 60s 记结构化日志（等的是哪个 doc、预热任务状态）——并发排查可观测性最小集。

### KD6 · 渲染中途失败保留已完成页

逐页迭代循环把"迭代器抛出的结构化错误"从冲出循环改为捕获收口：已完成页正常出稿，剩余页以
`[第M页起识别失败: <原因>]` 单行标记；文件级结果标 `partial`（进 KD2 状态）。`MemoryError`/
取消/进程退出仍按 0730 设计透传不伪装。

## 影响范围

```text
server/ocr/engine.py           KD1 重试 / KD3 闸 / KD6 收口（基线 887 行已越线，豁免：净增 ≤60 行，
                               超出拆 server/ocr/vlm_client.py）
server/ocr/pipeline.py         KD6 partial 透传, is_ocr_text_valid 明细化（基线 791 行，同豁免）
server/tender/doc_pipeline.py  KD2 状态落库
server/tender/runner.py        KD2 入口决策 / KD5（基线 328 行已越线，豁免：净增 ≤40 行）
server/tender/worker.py        KD2 状态消费（如需）
server/platform/config.py      KD4/KD5 新 env（OCR_EXECUTOR_WORKERS；等待上限派生逻辑）
server/stores/*                KD2 ocr_status 枚举 + failed_files 字段迁移
tests/test_ocr_engine_fallback.py, test_ocr_pipeline.py, test_tender_* 等  全 KD 红→绿
deploy/TROUBLESHOOTING.md      并发症状排查节（等待日志怎么读）
```

前端修改面（Round1-F1 拉入，仅 doc 状态硬门四点，不做专门 UI）：

```text
agent-front/.../api.ts                       OcrStatus 类型 += degraded/partial
agent-front/.../use-tender-review-page.ts    终态集(:289-292) / canStart(:328-330)
agent-front/.../components/analyzing-view.tsx 状态 label(:456) + OcrDot 色点映射(:446-453，
                                             degraded 不得显示"进行中"蓝色脉冲) + :309 文案(critic R2-P2c)
对应 *.test.ts                                红→绿
```

## 已验证基线（2026-08-11 主 agent 实测）

- 全量测试收集数 = 1162（`uv run pytest --collect-only -q | tail -1`）。
- `wc -l`：engine.py=887、pipeline.py=791、runner.py=328（三者基线已越 300 线，豁免 + 净增上界
  见影响范围节）；doc_pipeline.py 改后须 ≤300 现值另测（impl-entry 时 `wc -l` 复核）。
- ocr_status 现有枚举取值：impl-entry 时以
  `grep -rn "ocr_status" server/stores/ server/tender/doc_pipeline.py` 实测清单为准做迁移。

## 风险与缓解

- ocr_status 枚举扩展是 DB 迁移 + 多消费点契约：先 grep 全量消费点再改（影响范围节命令），
  未知消费点按 fail-fast 处理（未识别状态抛错不静默当 ready）。
- KD5 "继续等"可能把整单推向 TENDER_TIMEOUT：预算派生上限保证评标保留量；比双跑恶化（现状）
  严格更优，且等待可观测。
- KD1 重试延长单页耗时：重试预算封顶在页 deadline 内，最坏不劣于现状超时路径。
- 与 H2 的 pipeline.py/engine.py 改动面重叠：两 sprint 各自 worktree，**合并顺序 H2 先、H3 后**
  （H3 rebase 消解冲突；两者语义正交——H2 改页号字段，H3 改控制流）。

## 验收标准

- [ ] AC1 重试：单页 VLM 首次失败第二次成功 → 该页 VLM 结果、无降级、页序连续；两次失败 →
  该页起 Tesseract，行为与 0730 一致。
- [ ] AC2 降级不落 ready：degraded 结果 → doc 层状态 degraded、文件缓存不写（0730 语义回归）、
  下次预热重call VLM；评标入口自动重跑一次后仍 degraded → 结论带结构化 warning 且照跑。
- [ ] AC3 partial：10 文件 2 失败 fixture → 状态 partial + failed_files 明细；8 个成功文件底稿
  完整；评标结论 warning 点名失败文件。渲染第 3 页故障的 5 页 PDF → 前 2 页正常出稿 + 尾标记。
- [ ] AC4 并发闸：mock 网关计数并发 → 峰值 ≤ OCR_VL_MAX_CONCURRENCY；闸等待不触发页 deadline。
- [ ] AC5 executor：注入慢 OCR（sleep 模拟）双任务并发 → DB 状态写与轮询读延迟不随 OCR 在途数
  恶化（对照测试：默认池路径 vs 命名池路径）。
- [ ] AC6 双跑消解：预热 in-flight 时评标等待不发起 inline（进程内 OCR 调用计数=1 套）；预热
  failed → inline 回落照常；等待日志按约定输出。
- [ ] AC6b 前端硬门：doc 状态 degraded/partial → 轮询正常终止、"开始分析"可用且带告警提示、
  label 正确显示；前端 test/build/eslint 绿。
- [ ] AC7 质量门：先红后绿证据齐；`uv run pytest -q` 全绿收集数 ≥1162+新增构成式；ruff 净；
  schema 演化沿用仓库既有幂等 PRAGMA+ALTER TABLE 先例（tender_doc_store.py:77-101 同型，
  不引入迁移框架、不要求 downgrade，Round1-F6），未知枚举值 fail-fast；TROUBLESHOOTING 更新。

---

## Round 1 (initial draft by Fable 5)

页级重试、degraded 不落 ready、VLM 并发闸、executor 分池、双跑消解、渲染失败保留已完成页。

## Round 1 · Critic Findings

VERDICT: NEEDS_REVISION（三设计合审，本档相关项）

- F1 [P0] ocr_status 新枚举打断前端硬门：终态集/canStart/OcrStatus 类型/label 四点不改，
  degraded 会让轮询不终止、"开始分析"永久禁用（0730 KD4 漏末端消费者同型事故）。
- F5 [P1] KD5 "查预热任务状态"无可查对象（预热无任务注册表）；stale running 未处置；
  派生上限到期路径未定义。
- F6 [P1] AC7 "DB 迁移含 downgrade"与仓库现实不符（全仓先例是幂等 ALTER TABLE，零 downgrade），
  照做只能新造框架（违反铁律[反过度工程]）或 AC 不可达。

## Round 2 (revised by Fable 5)

- F1 CLOSED：前端四点拉进修改面（KD2 增前端硬门同步段 + 影响范围前端节 + AC6b）；否决
  "路由冒充 ready"备选（与本 sprint 可见性目标矛盾）。
- F5 CLOSED：oracle 定义为 `ocr_status=running && updated_at 新鲜度 < OCR_PREWARM_STALE_SEC(300s)`，
  预热周期性 touch updated_at 随行落实；stale/上限到期均按 failed 走 inline 一次 + warning。
- F6 CLOSED：AC7 改为沿用幂等 ALTER TABLE 先例 + 未知枚举 fail-fast，删 downgrade 要求。
- 另接受 roadmap 级 F7：合并序 H1→H2→H3（本 sprint 最后合并，rebase 后做共享契约复核）。
