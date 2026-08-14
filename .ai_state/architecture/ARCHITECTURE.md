# 架构现状档 · 总入口

> 项目长效架构档索引。每个子系统一档 `{type}-{slug}.md`。Refactor/System 路径 ship 前强制更新。

## 子系统档

| 档 | 子系统 | 摘要 |
|---|---|---|
| `system-tender-data-model.md` | tender 招标数据模型 | 招标项目实体 owns N 家投标评标 + 多投标人追加 + 回看 + 价格横比（Phase 1+2，2026-06-20） |
| `system-tender-evidence-resolution.md` | tender 评标证据可验证性 | evidence-resolution 闸（出处回查）+ 底稿→校验透传管道 + BOQ 感知抽取 + confidence 消费（2026-06-22） |
| `system-document-ingestion.md` | 文档摄取与 OCR | 24 格式 native→Office→VLM→Tesseract 路由、资源门禁、缓存与双镜像配置边界（2026-07-30） |
| `system-prompt-architecture.md` | 提示词架构 | ⚠️ 下沉结构已回滚（2026-08-14 生产爆窗）：现状=38,754B 单文件；档内存 KD2 单源链路（仍有效）与已回滚结构的历史参考 |
| （已删） | contract/legal | 2026-06-20 agent-capability-redesign G0 删除（死域，无 knowledge/legal 规则） |

## 真实业务域（round4 校准）

- **expense**（报销审核）· **tender**（招投标评标）· **ocr**（文档识别能力，喂其它域）。
- system 是制度→规则工具域，不出审批结论。
- **已删死域**：legal/contract（无规则、纯增攻击面）+ HR（仅孤儿 agent stub）——见 round4 F8。

## 全局分层（server/）

```
app (api/cli) → routes → ops → features(audit|tender) → ocr(服务层) → core → common → stores → platform
```

- `ops` 是 routes 之下的 service 层（diagnostics/maintenance），被 app+routes 共同消费——
  见 `compound/2026-06-19-decision-ops-below-routes-layering.md`（T2.5 修正）。
- feature 域 audit/tender 互不 import；**ocr 降为 features 之下的服务层**——允许 audit/tender→ocr，
  禁止 ocr→audit/tender（单向守卫，2026-07-15 D1 F5 方案 i 拍板并经 D1 T5 落地，见
  `compound/2026-07-15-decision-ocr-service-layer.md`）。
- **tender feature 包已成型**：D1 落 `server/tender/`（eval 回归闸 + runner 评标核心下沉），
  **D2 迁入 worker/compare_worker/doc_pipeline，并把 `routes/tender.py`(912) 拆成 `routes/tender/`
  分节路由包（tasks/projects/docs/compare + 壳）**。**2026-07-18 `tender-schema-split`（F6 schema 分家 +
  F5 evidence 拆分）merge `f998969` 收全**：`tender_output`→`server/tender/output.py`（挂
  `TENDER_OUTPUT_SCHEMA_NAME`，`schema_path` 别名复用 audit-result.json，双解析点 apply_schema_semantics +
  build_output_format 统一走 `_resolve_physical_schema_name`）；`evidence_resolution` 拆成
  `server/common/corpus.py`（通用语料原语）+ `server/tender/evidence.py`（tender resolve + scoring 助手）；
  共享 audit-result 三函数 generic/tender 分家，expense/audit 不再跑 tender 校验。**tender 逻辑至此全部归位
  `server/tender/`，`common/` 零 tender 依赖。** 见 `compound/2026-07-16-decision-carve-f6-schema-split-from-d2.md`。
- **2026-08-14 爆窗事故后收口**：`runner.py`(419) 纯移动拆出 `doc_context.py`(122，底稿获取/OCR 完整性
  告警/`_index` 状态读取) 与 `criteria_context.py`(45，criteria 注入块拼装)；预算闸 `_bound_ocr_block`
  与重试环留 runner.py（拆分边界=测试打桩面 + logger 名保持，见
  `compound/2026-08-14-trick-runner-split-pure-move.md`）。确定性失败判定 `is_non_retryable`
  上提 `server/common/contract.py`，tender/audit-runner/audit-direct 三条契约重试环共用
  （`Prompt is too long` 命中即抛不重试，issue 档 `issues/2026-08-14-tender-context-overflow/`）。
- **D8 底稿瘦身（transcript-slimming，merge be85ec0）**：新增 `server/tender/context_slim.py`——按项目 criteria
  检索招标文件相关章节（内存 FTS5，复用 D6 `docstructure` + D7 `rag`），替代全量 32 万 token 灌注；`runner.py`
  loader 由 `TENDER_SLIM_CONTEXT`（默认关）门控，flag off = 同一 `_load_doc_layer_context` 函数对象、行为逐字节不变。
  页锚显式前缀保真，任一 criteria 项零命中则整档回退不部分丢。成本/质量四指标验收 = 部署机 runbook（待跑）。
- 守卫：`tests/test_layering.py`：routes 不 import api、platform 叶子、common 不依赖上层、
  feature 互斥（audit↔tender）、**ocr 单向（audit/tender→ocr 合法、反向禁止）**、ops 不 import
  routes/app/features、stores 只 import platform、server.tender 纳入 ops/common/stores 禁区、
  **feature 域(audit/tender)不上行 import routes/ops/api（D2 T5 新守卫 test_features_do_not_import_routes_ops_or_app）**。

## 存储

- 统一单库 `data/db/platform.sqlite3`（多表）：results/requests/sessions/review_deltas/
  memory_assets/audit_tasks/tender_tasks + **tender_projects/tender_compare_tasks/tender_compare_results**（招标数据模型）。
- **D7 新增 `rag_chunks`（FTS5 虚表，tokenize=trigram 支持中文 BM25）**：D6 文档结构化产物按章节子树分块入库，
  供 `server/ocr/rag.py::search` 带页锚出处检索（服务 tender S1 定位 + D8 底稿瘦身）；conn 注入、零侵入既有表。
- **OCR 结构化层（D6/D7，2026-07-18）**：`server/ocr/docstructure.py`（确定性章节树/语义标签/实体/跨页表格合并，
  页锚硬护栏）+ `server/ocr/rag.py`（分块+索引+FTS5 检索）+ `server/stores/rag_store.py`；均 ocr 服务层,不 import tender/audit。
- **OCR 流式任务层（D9，2026-07-20）**：`POST/GET /ocr/jobs`（`server/routes/ocr_jobs.py`）+ job worker
  （`server/routes/ocr_job_worker.py`：semaphore+超时+三态，与 audit_worker 同构）+ `TaskStore("ocr_jobs")` 独立表
  （`server/stores/ocr_job_store.py`，不改共享 schema）。页级部分结果落 **`<case_dir>/units.jsonl` 边车**
  （per-job lock append、单调不回退，已入 `_OCR_EXCLUDED_FILENAMES` 防被 `_iter_files` 重扫当文档）；
  progress 存 `progress_message` 定长 JSON `{done,total}`；路径一律服务端 `build_case_dir` 派生（跨租户 404）。
  `pipeline.extract_dir(on_unit_complete=...)` 回调接缝：native pdf_text 读后从最终 blocks 发、OCR 侧 buffer-then-fire，
  默认 None 零行为。前端 OCR 工作台 Tabs 双模式（识别+回填 / 流式识别渐进渲染）。
- **文档摄取格式层（2026-07-30）**：24 个 canonical 后缀由共享 manifest 单源派生；原生抽取不足时
  进入隔离 LibreOffice→PDF，再走 LiteLLM/OpenAI-compatible VLM→本地 Tesseract 的保守降级链。
  图片/PDF/Office 均有分配前资源门禁，空文本和仅页锚不算成功，degraded 结果不缓存。现状详见
  `architecture/system-document-ingestion.md`；目标 demo 成品镜像实跑仍由当前 sprint T6 验收。
- 大 blob 留文件：会话 event 流、上传原件。
- 详见 `sprints/2026-06-19-logging-and-storage/design-data-storage.md` + `architecture/system-tender-data-model.md`。
