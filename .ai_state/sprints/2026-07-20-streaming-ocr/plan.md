# Plan · D9 页级流式 OCR（streaming-ocr）

> design 定稿见同目录 design.md（Round 1 + 两轮 critic + 收尾修订）。
> 执行纪律：TDD red→green，每 T 单 commit + 全量 pytest 绿再进下一 T（Sisyphus 全绿才可 ship）。

## 任务分解

### T1 · pipeline 回调接缝（黄区，后端 subagent）

- `on_unit_complete` 回调参数贯穿 `extract_dir → extract_one`（**含缓存命中分支**，附 `from_cache: true`）`→ _extract_one_raw`；默认 `None` = 现行为逐字节不变。
- 页级透出：native `read_pdf_text` 与 `_recognize_via_paddle_pipeline` 走 **buffer-then-fire**（锁内收集、锁外回放）；`_recognize_via_openai_compatible` 识别循环（engine.py:228-239）直接触发；cloud 整档 = 文件级单元。
- G1：`units.jsonl` 加入 `_OCR_EXCLUDED_FILENAMES`（pipeline.py:94）。
- 单测：默认 None 现测试零改动全绿；事件序完整 + 页锚保真；回调内断言 `FITZ_LOCK.locked()==False`；缓存命中触发文件级事件；units.jsonl 存在时重跑 `extract_dir` 不计入 results。

### T2 · jobs 端点（黄区，后端 subagent）

- `POST /ocr/jobs`（multipart 对齐 `/fill`）→ 202 `{job_id}`；`GET /ocr/jobs/{job_id}` = `TaskStore("ocr_jobs")` 记录 + 读 units.jsonl 组装 `{status, progress, results[]}`。
- `progress_message` 固定 JSON `{"done": <int>, "total": <int>}`，解析失败按无进度处理（G2①）。
- 单测：submit/status/终态一致性；partial 单调递增不回退；total_units=0 立即 completed；未知 job_id 404。

### T3 · job worker（黄区，后端 subagent）

- 与 audit/tender harness 同构：准入闸 + 信号量 + 超时 + 三态 upsert；units.jsonl append 由 per-job `threading.Lock` 保护。
- 路径派生（G2②，信任边界）：tenant 来自 `verify_tenant(authorization)`、request_id 来自 TaskStore 记录，`build_case_dir` 同款派生，**不接受客户端传入路径**。
- `recover_stale` 置 failed 不触碰 units.jsonl（partial 保留供核查）。
- 单测：并发 append 完整性压测；crash→failed 后 units 仍可读。

### T4 · agent-front 渐进渲染（**红区 worktree**，已授权）

- `ocr-workbench-page.tsx` 提交改走 jobs + 轮询渐进渲染；loading/partial/success/error 四态；failed 态仍渲染已完成单元 + 错误原因。
- null/404 一律终态停轮询（继承 use-tender-review-page.ts:511-517 防御写法）。
- 验收：eslint 净 / build 过 / test 绿（worktree 内）。

### T5 · 全量回归（主 agent 独立验）

- 存量 `/ocr/extract`、`/ocr/fill`、tender/audit 预处理测试**零改动**全绿；全量 pytest ≥ 920 基线 + ruff 净。

## 执行序与分区

T1 → T2/T3（可并行）→ T4（红区 worktree，依赖 T2 契约冻结）；T5 每 T 后跑、merge 前全量。
后端 T1-T3 = 黄区单 feature 模块（Agent subagent）；T4 = agent-front 红区（isolation: worktree 强制）。

## 状态

- [x] T1 pipeline 回调接缝 — merge ebf9113(main),931 passed/ruff 净;主 agent 独立验(buffer-then-fire 锁外/零kwarg透传/F3缓存补事件/G1排除全实证)
- [ ] T2 jobs 端点
- [ ] T3 job worker
- [ ] T4 agent-front 渐进渲染
- [ ] T5 全量回归

> T2+T3 合并为一个 generator 一次做完（共享 job 生命周期契约,耦合紧,避免并行 worktree 冲突）。

**待用户 GO 后开工（GO 前勿写代码）。**
