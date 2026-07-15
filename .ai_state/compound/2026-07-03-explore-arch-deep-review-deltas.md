---
doc_type: explore
slug: arch-deep-review-deltas
date: 2026-07-03
sprint: 2026-07-02-eval-tender-scaffold
tags: [architecture, ocr, prompt-delivery, stores, roadmap-2026-07]
---

# 全仓二轮深度 review：对 2026-07-02 架构评估的修正与新机会

> 三路 Explore 并行核验（ocr 域 / common+stores / routes+prompt 机制）。
> 本档只记**与既有评估不一致或评估未覆盖**的增量；一致部分不重复。

## 翻案项（修正 2026-07-02 评估）

1. **"三域三套 prompt 双源漂移"半证伪**：tender 的 command 文件**本来就是单一真相源**——
   `build_command_prompt`（command_adapter.py:20-31）只发 `/tender-evaluate` 字面量，正文由
   SDK CLI 经 `setting_sources=["project"]` 加载，Python 侧零复制。真正的双源事故
   （2026-06-12 audit.md 改了不生效）根因是 **expense 同域两份**（audit.md 休眠 +
   AUDIT_INSTRUCTIONS 生产）。→ D3 目标应从"三选一统一机制"改为"**消灭同域双份**"；
   两机制本身是两种合法执行模式：lean-inline（expense/ocr-form-fill，setting_sources=[]，
   prefill 优化有 config.py:387 明文动机）vs command+tools（tender，需要 Skill/Task/Read
   escape hatch，ocr-page 重识别只在此模式可达）。expense 走 command 的 spike 预期反向。
2. **"39 tender 测试文件"已修**（实测 14 文件名/25 引用，见 D1 design Round 2 F7）。
3. **task store 抽象已完成**：audit/tender/compare 三个 task store 已是泛型
   TaskStore（task_store.py:3-7 明文）薄包装。别再立重复项。

## 新发现（评估未覆盖）

4. **ocr 域内部切分线**：除 runner.py 外全部模块自述"确定性、无模型"
   （classify/native/engine/pipeline/cache/boq/locks/prewarm_scheduler）。runner.py
   （form-fill，调 run_agent_full + core 私有名）是 OCR 的**消费者**不是服务本身——
   ARCHITECTURE.md 本来就写"ocr（文档识别能力，喂其它域）"。→ 强化 D1-F5 方案 i：
   守卫单向化=把守卫对齐档案既有事实；runner.py 形态归属 D4 时一并收口。
5. **cache._engine_fingerprint 已失同步（correctness bug，不等 D4）**：只含
   OCR_CLOUD/OCR_VL_MODEL_NAME/OCR_VL_USE_PADDLE_PIPELINE（cache.py:27-39），漏
   OCR_VL_SERVER_URL/OCR_VL_BACKEND/OCR_VL_PIPELINE_VERSION——换 server/backend 不换
   fingerprint → 旧缓存被当新结果（正是 codex P1-2 当年要防的 poisoning）。绿区小修。
6. **死代码**：`ocr/runner.py:456 run_doc_extract` 全仓零调用者（routes/ocr.py 分开调
   run_doc_recognize + map_extraction_to_form）。删。
7. **output_contracts 单 schema 多域共用处理器**：tender 专属校验（scoring/plan/
   disqualification，:30-37 import）**无条件跑在 expense 结果上**；evidence_resolution
   resolve hook（:460-469）也挂在共享 schema 名上。干净解=**schema 分家**：注册
   `tender/audit-result.schema.json` 处理器，tender hooks+resolve 挂 tender 名，
   expense 用纯通用处理器——同时解开 D2-F6 迁移阻塞（tender_output 随 tender 处理器
   迁入 server/tender/ 合法）。附带修 contract.py:252 import-time 副作用注册
   （纯 audit 调用也拉入 tender_output+evidence_resolution）。
8. **worker 三胞胎骨架 60-70% 重复**：audit/tender/compare worker 的
   准入闸+强引用集+信号量+超时+三态 upsert 同构；差异（tender 流式进度/重试、compare
   先写后调度）均可参数化/hook 化。第三消费者已在 → 抽 background job harness 合理，
   落 D2（tender worker 迁包时顺手）。
9. **stores admin/tenant 双份查询模式**跨 4 文件（session_sqlite:129 vs 235、
   result_store:133 vs 205、request_store:264 vs 291、review_delta:237 vs 265）
   ~150-200 行重复，比"三处重复"账面大。参数化 `tenant: str | None` 一次解决，
   顺带把 session_sqlite/result_store 拉回 300 行内。
10. **evidence_resolution(642 行) 三段可拆且 (a)(b) 是 D7 现成资产**：语料解析/索引
    （:103-270）+ 匹配打分（existence_ratio/页窗口/k-gram，:278-453）是**通用检索原语**，
    audit-result 集成（:453-642）才是 schema 专属。→ D7 结构化 RAG 不必从零建匹配层，
    升格 (a)(b) 为共享检索内核，出处回查与 RAG 共用页锚语义（护栏天然对齐）。
11. **tender 每次评标加载 .claude/CLAUDE.md 全量路由章程**（业务路由表对单次评标是
    纯冗余 prefill）→ .claude 瘦身对 tender 有直接收益，D8 底稿瘦身后占比还会放大。
12. **tender.py(912) banner 分节已就位**（:133/223/441/627/854），tasks(~250)/
    projects(~185)/docs(~225)/compare(~60) 拆分低风险，D2 方案确认可行。
13. 小项：`purpose` 参数只有 openai-compatible 引擎真消费（engine.py:224-227，另两路
    显式丢弃）；paddle-pipeline 分支不写 `engine` 元数据键（:293）——D4 注册表化时统一。

## 对 roadmap 的净效果

- D2 范围+：schema 分家（解 F6）、worker harness、stores tenant 参数化（或独立绿区项）。
- D3 目标改写：统一机制 → 消灭同域双份 + .claude 瘦身（tender prefill 直接受益）。
- D4 首任务提前：fingerprint 同步修复是存量 bug（绿区可先行）；死代码删除同批。
- D7 起点变更：evidence_resolution 匹配内核升格复用，不从零建。
- D1-F5 方案 i 证据+：ARCHITECTURE.md 档案与 routes 7 处消费均已把 ocr 当服务层。
