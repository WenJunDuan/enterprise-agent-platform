---
sprint_slug: "2026-08-11-ocr-concurrency-degrade"
created: "2026-08-12"
path: "System"
polish_worker: "polish_worker subagent (worktree agent-ad32a594fad71cd9a)"
program: "2026-08-11-tender-eval-hardening (H3)"
---

# Cleanup Pass — 2026-08-11-ocr-concurrency-degrade (H3)

> 范围 = 本 sprint review 已确认的 P2 清单，逐项闭环。全量回归与基线逐条一致（见文末）。

## 已执行

### F6 — `ocr_failed_files` 列解析二次实现且行为不一致

同一个 JSON 列有两份解析：`runner._decode_failed_files`（损坏 → `[]`）与
`doc_rerun._restore_snapshot` 内联的一段（含函数内 `import json`，损坏 → `None`）。
两者行为不一致不是笔误——`[]` 会被编码成 `"[]"` 落库，`None` 才是"不记"。

**处置**：在 `server/stores/tender_doc_store.py` 公开 `decode_failed_files(raw)`，与既有
`_encode_failed_files` 对称同处一家（列格式只此一家知道）。返回 `list[str] | None`，
`None` 沿用编码端"不记"的语义。两个调用点改共用：

- `doc_rerun._restore_snapshot` 直接透传（回滚时"不记"必须原样是 `None`），函数内 `import json` 消失；
- `runner` 的 warning 渲染写 `decode_failed_files(...) or []`（warning 侧"没记清单"与"清单为空"
  同义，只是不点名文件），归一处显式注明。

### F10 — 读层两个孪生 loader

`load_doc_layer_context` 与 `load_doc_layer_context_slim` 逐行孪生，只差"招标底稿要不要按
criteria 瘦"一处；本 sprint 已经为此付过一次双改成本。抽 `_build_doc_context(..., slim: bool)`
承载全部读层判据（bid_id 缺失回落、状态可用性、ValueError 不吞、DB/IO 异常静默回落），
两个公开名保留薄封装——它们是 runner 的 monkeypatch 目标，签名与可打桩性不变。
回落日志合并为一条并带 `slim` 字段区分（原来两条消息文本不同）。

### F9 残留 — 陈旧符号名

`tests/test_codex_p2_rework_fixes.py` 与 `tests/test_tender_read_layer.py` 的 docstring /
断言消息里还写着 `_load_doc_layer_context`（带前导下划线的旧私有名），改为
`doc_layer.load_doc_layer_context`。

commits `f575577`（F6/F10/F9）。

### F7（部分）— 饿死对照测试的 flake 面

`tests/test_ocr_executor_pool.py` 实验组原断言 `named_pool_latency < 0.15s` 是**绝对墙钟**：
机器负载会同时抬高两侧耗时，慢机上这行就是纯 flake，而它要防的性质其实是"命名池远快于默认池"。
改为相对比较 `named * 10 < default`；对照组阈值由 `_SLOW_SEC` 派生（`_SLOW_SEC * 0.5`）不再写死
秒数。连跑 5 次稳定通过（实测实验组亚毫秒 vs 对照组 ~0.25s，10 倍余量充足）。commit `f32e469`。

## 已 defer（本轮不做，理由如下）

- **F7 剩余面：池单例的测试序依赖**。`test_ocr_executor_is_a_named_bounded_pool` 拿进程级单例的
  `_max_workers` 与**当前** env 派生的 settings 比对；若更早的测试在 `OCR_EXECUTOR_WORKERS` 被
  monkeypatch 期间首次创建了单例，两者会漂移。要修得给进程级单例加 reset/注入口子——为可测性
  改一个生产单例的生命周期，超出 polish 范围且违反反过度工程。当前 `-p no:randomly` 下顺序固定，
  暴露面为零。留待哪天真的踩到再连同 fixture 设计一起处理。
- **N8：`ocr_failed_files` 列名语义**（实际含降级文件，不只失败文件）。列名不改的理由已写进
  store 的 `_encode_failed_files` docstring；改列名要动 schema 迁移 + 全部读写点，收益只是命名，
  不值当。**维持 defer**。

## 5 检查项结论（本 sprint diff 范围）

1. **临时代码 / 调试痕迹**：无；函数内 `import json` 这类"就地凑合"随 F6 一并消除。
2. **注释完整性**：`decode_failed_files` / `_build_doc_context` 均带完整 Args/Returns/Raises；
   两个薄封装各一行说明并指向公共体。
3. **冗余 / 重复**：两处重复解析归一、两个孪生 loader 归一，是本轮主要产出。
4. **低效模式**：无新增循环内 IO；`_build_doc_context` 的读次数与合并前一致。
5. **过度设计**：`slim` 是布尔参数不是策略对象；`decode_failed_files` 有两个真实消费者才公开；
   保留薄封装是因为 monkeypatch 目标真实存在，不是"以防万一"。

## VERDICT

**PASS** — F6/F10/F9 闭环，F7 部分硬化（绝对墙钟已消），F7 剩余面与 N8 显式 defer。
