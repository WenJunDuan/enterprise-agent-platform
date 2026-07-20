# Design · D9 页级流式 OCR（streaming-ocr）

> Sprint: 2026-07-20-streaming-ocr · Path: Feature · redzone: agent-front（已授权 2026-07-20）
> Roadmap: 2026-07-doc-intelligence D9 · 分诊见同目录 route-note.md

## Round 1

### 背景

- OCR 慢是 2026-06-21 用户实测 backlog 首条：`/ocr/fill` 自适应识别（云 OCR 158 页扫描 + 200K 底稿 + 模型映射串行）一次性同步返回，前端全程白屏等待，百页扫描件分钟级。
- D9 用户拍板（roadmap 决策3）＝页级部分结果流：边识别边出每页/每文件完成事件，前端渐进渲染。
- **前提修正（route-note 侦察事实 1）**：roadmap note 设想「复用平台 SSE 进度流机制」，实测 server/ 无任何 SSE/StreamingResponse。平台既有异步形态＝泛型 TaskStore submit→poll（audit/tender 同构）。传输形态是本设计第一分叉。

### 方案

#### 方案 A（选定）：OCR 任务化 + 部分结果轮询

- `POST /ocr/jobs`（入参对齐现 `/fill`：multipart files + 可选 form_schema）→ 202 `{job_id}`；后台 worker 跑 pipeline，每完成一个**单元**（页或文件，见粒度）把该单元结果 upsert 进 job record。
- `GET /ocr/jobs/{job_id}` → `{status, progress: {done_units, total_units}, results: [已完成单元…]}`；终态（completed/failed）后前端停轮询（tender compare 停轮询先例）。
- 存储复用泛型 `TaskStore`（audit/tender 先例），partial results 存 job record payload；不建新 store 机制。
- **粒度自适应（route-note 侦察事实 3，不硬造页级）**：
  - native（pymupdf，native.py:182 逐页循环）与 VLM（engine.py:131 `_render_pdf_pages` 逐页调用）→ **页级**单元；
  - cloud aistudio job-poll（engine.py:323-393 整档返回）→ **文件级**单元；
  - 单元 schema 统一 `{file, page?, status, payload}`，前端按单元渲染、不假设页级。
- pipeline 接缝：`extract_dir` / `_extract_one_raw` 增加 `on_unit_complete` 回调参数，**默认 None＝现行为逐字节不变**（D8 flag 门控同款纪律）；页级回调需 native/VLM 内循环透出，cloud 不透出。
- 现有同步 `/ocr/extract`、`/ocr/fill` 与 `ocr_preprocess_block`（tender/audit 预处理消费者）**零改动**。
- 页锚【第N页】全链路保真红线不变（partial 单元同样带真实页号或 null，不臆造）。

#### 方案 B（否决，理由留档）：新建 SSE 通道

- `text/event-stream` 真推送延迟最低；但平台零 SSE 基建——内网反代 buffering、断线重连、EventSource 封装、多 worker 进程间事件路由全要新建。
- OCR 单元完成粒度为秒级（云 OCR 5.9s/档、VLM 每页秒级），1s 轮询与推送的体感差可忽略；成本高收益薄。
- → SSE 随「识别-评标流水线重叠」（流式二期 backlog）真需要事件粒度时再评估，本 sprint 不建。

#### 反过度工程边界

- 不建平台级 streaming framework：partial-results 只做 OCR 域，无第二消费者不抽象。
- 不预置轮询间隔/粒度配置项；增量拉取参数（见风险②）按实测数据决定是否加，不「以防万一」预建。

### 影响范围

| 位置 | 改动 | 分区 |
|---|---|---|
| `server/ocr/pipeline.py` | `on_unit_complete` 回调接缝（默认 None 零行为变更） | 黄区 |
| `server/routes/ocr.py` | +`POST /ocr/jobs`、`GET /ocr/jobs/{id}`（复用 upload_helpers/准入闸先例） | 黄区 |
| `server/routes/*_worker` 先例 → ocr job worker | 信号量+超时+三态 upsert，复用 audit/tender harness 形态 | 黄区 |
| `agent-front/src/features/ocr/ocr-workbench-page.tsx` | 提交改走 jobs、轮询渐进渲染、loading/partial/success/error 四态 | **红区 worktree** |
| 契约 | job status 响应 schema（单元结构复用现 results[] 元素 + status/progress 字段） | 黄区 |

### 风险与缓解

1. **cloud 引擎页级不可得** → 粒度自适应已入方案；前端按单元渲染，文件级单元同样渐进（多文件场景仍逐档出）。
2. **轮询体积**：百页 markdown 每秒全量拉取浪费 → 首版 full 返回 + 实测响应尺寸；超阈值再加 `results_after` 增量参数（有数据再加，不预建）。
3. **并发/超时** → 复用 audit/tender worker 信号量与超时先例（R6 超时预算警告已在册）。
4. **前端红区回归** → worktree 强制 + eslint/build/test 三绿 + D11-R7 null-guard 纪律沿用（partial 数据天然「不完整」，四态渲染必须容忍 `page?`/缺字段）。
5. **同步路径回归** → T5 验收锁定现测试零改动全绿；回调默认 None 由单测断言函数对象/行为不变。

### 验收标准

- **T1** pipeline 回调接缝：默认 None 现行为不变（现有 OCR 测试零改动全绿）；注入回调时单元事件序完整、页锚保真（新单测）。
- **T2** jobs 端点：submit 202/status 轮询/终态一致性；partial results 单调递增不回退（新单测）。
- **T3** worker：准入闸+信号量+超时+三态 upsert，与 audit/tender 同构（新单测）。
- **T4** agent-front：渐进渲染四态、终态停轮询、lint/build/test 三绿（红区 worktree 内验收）。
- **T5** 存量回归：`/ocr/extract`、`/ocr/fill`、tender/audit 预处理相关测试**零改动**全绿；全量 pytest 基线（920 passed/2 skip）+ ruff 净。
- 端到端：多页 PDF 提交 → status 先出部分单元后到终态，前端可见渐进结果。

### 明确不做（本 sprint）

- SSE / WebSocket（流式二期）；识别-评标流水线重叠（backlog）；同步端点改造或下线；平台级 streaming 抽象。

## Round 1 · Critic Findings（2026-07-20 · VERDICT=NEEDS_REVISION）

critic 独立核验（34 tool calls 实证），方案 A 方向未被推翻（过度设计维度 5/5，SSE 否决成立），但六条 findings：

- **F1 [P0]** `TaskStore`/`ResultRecord` 均为固定字段（task_store.py:29-47），**无 JSON/blob 列可装增量单元列表**；`result_file` 仅终态一次性原子写、`status=="completed"` 才可读（routes/audit.py:188-189）。「partial 存 job record payload、不建新机制」名实不符，T2 无落点。
- **F2 [P1]** native 逐页循环整体在 `FITZ_LOCK`（全 OCR 模块共享锁，locks.py）临界区内（native.py:174-197）；`OCR_VL_USE_PADDLE_PIPELINE=1` 路径同在 `PADDLE_LOCK` 内（engine.py:280-292）。回调若锁内触发且做 DB/IO，会在 ThreadPoolExecutor(6) 并发下放大锁竞争，与提速初衷相悖。
- **F3 [P1]** `extract_one` 缓存命中直接返回（pipeline.py:203-216），不经 `_extract_one_raw`——命中文件永不触发回调，`done_units` 卡住，单元计数一致性被破坏（缓存命中是常规路径非边角）。
- **F4 [P2]** 边界遗漏：total_units=0 的 job 终态语义、未知 job_id 轮询语义未定义（前端防御先例 use-tender-review-page.ts:511-517「null=终态」未被继承）。
- **F5 [P2]** worker crash 后 `recover_stale`（task_store.py:277-300）整体覆盖 running 行——已发出 partial results 的去留未讲清。
- **F6 [P2]** 引用精度：VLM 页级插桩点应为 `_recognize_via_openai_compatible` 识别循环（engine.py:228-239）而非 `_render_pdf_pages`（仅切图）；前端落点实为 `agent-front/src/features/ocr/ocr-workbench-page.tsx`（workbench/ 子目录只有 mock-data/shared）；停轮询先例具体文件=use-tender-review-page.ts（refetchInterval ×3：L487/L284/L315）。

## Round 2 · 修订应答

- **F1 → 存储机制定案：追加式 JSONL 边车（撤回「存 job record payload」表述）**。单元事件逐行 append 到 job 提交目录 `data/submissions/<tenant>/ocr/<request_id>/units.jsonl`（per-job `threading.Lock` 保护 append，append-only 天然单调递增不回退）；`TaskStore` 只存 status + done/total 计数（现有 progress 字段薄更新，不加列）；`GET /ocr/jobs/{id}` = TaskStore record + 读 units.jsonl 组装 `results[]`。**不改共享 TaskStore schema**（audit/tender 零波及），存储布局沿用 storage-restructure 域命名空间先例；行号为将来增量拉取留自然锚（本 sprint 不加参数）。
- **F2 → 回调契约 = buffer-then-fire（锁外触发）**。native `read_pdf_text` 在 `FITZ_LOCK` 内只收集 `(page_no, payload)` 本地 buffer，退出 with 块后逐条回放；`_recognize_via_paddle_pipeline`（PADDLE_LOCK）同理；`_recognize_via_openai_compatible` 识别循环（engine.py:228-239，锁外）可直接触发。契约写明：**回调不得在持有 ocr/locks.py 模块锁时被调用**；T1 增单测（回调内断言 `FITZ_LOCK.locked() == False`）。
- **F3 → 缓存命中路径补事件**。`extract_one` 命中 `ocr_cache` 分支触发一次文件级单元事件（附 `from_cache: true`）；T1 增缓存命中单元计数断言。
- **F4 → 边界语义入 T2**。total_units=0（空目录/全 classify 失败）→ 立即 completed 不悬空；未知 job_id → 404；前端 null/404 一律按终态停轮询（显式继承 use-tender-review-page.ts:511-517 防御写法）。
- **F5 → partial 保留策略**。units.jsonl 是独立文件，`recover_stale` 置 failed 不触碰它：**保留**已出单元供人工核查；前端 failed 态仍渲染已完成部分 + 错误原因（与「不可判定不清零」纪律同族）。
- **F6 → 引用勘误已同步**：本文影响范围表与 route-note.md 前端路径、VLM 插桩点、停轮询先例均已修正（见下）。

### 验收清单增补（T1/T2 修订，其余不变）

- **T1 增**：缓存命中触发文件级事件断言；回调锁外触发断言（`FITZ_LOCK.locked()==False`）。
- **T2 增**：0 单元 job 立即 completed；未知 job_id 返回 404；units.jsonl 多线程并发 append 完整性（压测单测）。

## Round 2 · Critic Findings（2026-07-20 · VERDICT=APPROVE-WITH-CHANGES）

F1-F6 **全部 RESOLVED**（critic 逐条代码实证）：F1 两个关键点核验为真——`progress_message`（task_store.py:42 自由 TEXT 列）本就是高频薄更新先例（评标 flusher 1.5s 写进度），装 done/total 计数落在既有列语义内；`TaskStore("ocr_jobs")` 独立表是该类既有泛型用法（task_store.py:79-84 table_name 白名单），**不算改共享 schema**；`data/submissions/<tenant>/ocr/<request_id>/` 即 `materialize_ocr_upload`（upload_helpers.py:278-308 `build_case_dir`）已在用的同一目录，租户逐段白名单校验天然覆盖。F2 锁范围对应精确、F3 插桩点钉在 `extract_one`（含命中分支）自洽、F4/F5/F6 均可测可实现。

新 findings（同轮闭合，无需再开 critic 轮）：

- **G1 [P1]** units.jsonl 落在 `_iter_files` 会 `rglob` 扫描的同一 case_dir（pipeline.py:97-113，排除名单仅 `audit-request.json`），且 `/ocr/extract` 目录模式（ocr.py:93-95）与未来 job retry 都会对同一目录重跑 `extract_dir`——边车文件会被 classify→`read_text` 兜底当正文识别，内部诊断串进底稿、污染单元计数。与 F1 同族的「共享文件系统状态绕过零改动声称」模式。
- **G2 [P2]** ①`progress_message` 编码格式未钉死，GET 端解析有歧义空间；②units.jsonl 与 status 端点的路径派生方式只是隐含约定，未显式禁止客户端传路径。

## Round 2 · 收尾修订（G1/G2，随本轮定稿）

- **G1 → 排除名单（选最小解）**：`units.jsonl` 加入 `_OCR_EXCLUDED_FILENAMES`（pipeline.py:94），与 `audit-request.json` 先例完全同构，一处改动同时覆盖 `/ocr/extract` 目录模式与 job retry 两条重扫路径（都经 `_iter_files`）。**T1 增断言**：case_dir 内存在 units.jsonl 时重跑 `extract_dir`，其不计入 results/单元计数。不采用专属子目录方案（多排除一层目录、无额外收益，反过度工程判据）。
- **G2① → 格式钉死**：`progress_message` 固定为 JSON 字符串 `{"done": <int>, "total": <int>}`；GET 端解析失败按无进度信息处理（不 500），格式由 T2 单测锁定。
- **G2② → 路径派生显式入 T3**：`GET /ocr/jobs/{id}` 与 units.jsonl 路径一律由服务端从 `verify_tenant(authorization)` 的 tenant + TaskStore 记录的 request_id 经 `build_case_dir` 同款派生，**不接受任何客户端传入路径**（信任边界防御，非可选项）。

**design 定稿。进入 impl-entry 前置：用户 GO。任务分解见同目录 plan.md。**
