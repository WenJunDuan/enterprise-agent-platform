# Tender 域路线图（2026-06-tender-program）

> 由 11-agent 规划 workflow(wf_9eade0e9-475) 深度分析 + 完整性 critic 综合而成。
> 两条并行流：**技术债整理**(审计 F1-F6 + OCR 合并) 与 **产品方向**(2026-06-29 会议纪要)。
> 来源：[audit.md](../../sprints/2026-06-26-tender-domain-cleanup/audit.md) + 会议纪要 2026-06-29。
> **本文件是规划，不是实现。** 每个 sprint 启动时再出独立 design + TDD。

## 不可违反原则（每个 sprint 守住）

- 招标文件 criteria 是评分规则唯一来源；通则层法规只作法律底座。
- 不可判定项绝不判 0（价格横比/外部信用/现场/读不清 → manual_review + score:null）。
- **重构类 sprint = 零行为变更**，judgment 输出不变，以 `uv run pytest -q` 全绿守住。
- review-delta/reviewer dormant-by-design，勿删。
- agent-front 改动是红区（铁律[零写入]）：subagent + worktree 隔离，且需用户明确授权（见 compound/2026-06-19-decision-agent-front-cc-out-of-scope.md）。

## Sprint 清单（9 个，3 条流）

### 流 R — 技术债整理（refactor，零行为变更）

#### S1 · tender-store-dry（effort S）
- **目标**：消除 stores 跨文件 `_utc_now()` 重复，归一到 `server/platform/sqlite_store.py`。
- **范围**：tender_project_store:48 / tender_doc_store:27 / tender_compare_store:33 三处私有 `_utc_now` → 公共 `utc_now()`。
- **审计裁剪**：F3 的 `_initialize_schema×10` 合并 + `tender_task_store` 并入 **本轮不做**（各表结构不同，收益低风险高）→ 入 Backlog。
- **测试**：`test_layering.py::test_stores_only_import_platform` + 全量回归（纯别名替换）。
- 依赖：无。refs：审计 F3。

#### S2 · tender-claude-cleanup（effort S）
- **目标**：S1 定位逻辑单一权威 + 27 处注释 triage，零判分语义变更。
- **范围**：新建 `.claude/skills/tender-eval/references/s1-locate-criteria.md`(≤60行) 作权威；tender-extract-info.md / evaluator.md / SKILL.md 改引用；tender_worker.py(9)/tender.py(5)/output_contracts.py(10)/evidence_resolution.py(3) 注释升正式或去版本号前缀。
- **风险**：references 文件须控长防截断；保留「⚠ S3 评分细则以命令为权威」「不臆造补充」等护栏句。
- 依赖：无（纯文档/注释，pytest 不受影响）。refs：审计 F4+F5。

#### S3 · tender-doc-layer-split（effort L）★ 含用户强调的 OCR 合并
- **目标**：tender.py(1370行) 路由/ops 分层 + **OCR 编排合并进 `server/ocr/`，tender 仅消费**。（合并原 ocr-consolidation+f1，critic 建议同 worktree 顺序做，避免 tender.py 683-919 区块 merge 冲突。）
- **OCR 通用能力 → `server/ocr/`**（用户明确：不重复定义实现）：
  - `server/ocr/pipeline.py` 补公开 `OCR_ERROR_PREFIX` + `is_ocr_text_valid()`（消除 tender.py:683 对错误标记知识的重复定义）。
  - 新建 `server/ocr/prewarm_scheduler.py`：`get_upload_ocr_semaphore()` / `track_upload_ocr_task()` / `cancel_project_ocr_tasks()`（迁 tender.py:85-148）。
- **tender 业务 ops → `server/ops/`**：新建 `server/ops/tender_doc_pipeline.py`（OCR 编排 run/start + store 写入 + criteria_status）+ `tender_criteria_ops.py`（_criteria_looks_usable / _normalize_criteria_enums / _sanitize_tender_info / _extract_project_doc_info）。ops→ocr 合法下行。
- **tender.py** 瘦身到仅 HTTP 编排（1370→~880）。tender_worker.py 的 `TENDER_OCR_PURPOSE` 消重（改 import）。
- **风险/已 critic 修正**：`is_ocr_text_valid` 归属 `server/ocr/pipeline.py`（**不**进 ops），ops 侧 `from server.ocr.pipeline import is_ocr_text_valid`；test_codex_p2_rework_fixes.py/test_tender_p3_backend.py 的 inspect.getsource/私有名断言需同步改引用。
- **测试**：test_layering 守卫 + 新增 test_ocr_prewarm_scheduler.py + 全量回归零行为变更。
- 依赖：建议在 S1/S2 之后（干净起点）。refs：审计 F1 + 用户 OCR 合并指令。

#### S4 · tender-output-split（effort M）
- **目标**：output_contracts.py(930行) 抽 ~430 行 tender 专属到 `server/common/tender_output.py`，根治 D0 类跨域污染；expense 路径零变更。
- **迁出**：_verify_score_mode_consistency(192行)/_finalize_user_explanation 链/_has_*_disqualification/_eligibility/_score_summary 等。**留 output_contracts**：_load_known_rule_ids / _AUDIT_SCHEMA_TOP_FIELDS / normalize_audit_result / enrich_audit_decision（测试 monkeypatch 锚点）。
- **风险**：避免循环 import（tender_output 只依赖 common/contract）；桥接 import 保 enrich/normalize 调用点。
- **测试**：expense 回归(test_core_pure)+tender(test_tender_criteria_flow)+新增 test_tender_output.py。
- 依赖：S3 之后（软依赖，降 merge 噪声）。refs：审计 F2。

### 流 P — 产品方向（product，前端红区，需授权）

#### S5 · expert-advisory-repositioning（effort M）★ 本周优先
- **目标**：专家侧 UI 从"评分结论"改"辅助评审/风险提示"。隐藏终局 verdict 标签与明确总分，改七类问题清单：废标风险/资格不符/扣分点/形式问题(签字盖章)/材料缺失/参数正负偏离/待核验。后端 verdict/score 字段**不删**（供监督场景）。
- **范围**：model.ts 新增 `buildIssueList()` + `getAdvisoryLabel()`；types.ts 加 IssueItem；analysis-workbench-view/report-view 改风险卡 + IssueListPanel，去"建议推荐为第一中标候选人"措辞。后端/提示词/schema 不改。
- **原则风险（critic）**：`confirmed:false` 的 disqualification_hits 必须归 **待核验** 而非 废标风险（守 2026-06-23 R2b 纪律）；测试覆盖此边界。
- **测试**：TDD model.test.ts(buildIssueList 七类+边界) + `uv run pytest -q`(后端零改) + 手测。
- 依赖：D6 报告维度（已 ship）。refs：会议结论1-2/待办1-2。

#### S6 · scenario-split（effort L）
- **目标**：单一 UI 拆三场景：投标人自查(互联网区)/专家辅助(政务内网)/评后监督复核，共享后端内核。
- **范围**：tender_projects 加 scenario 列(默认 expert_assist，零迁移)；API 透传+过滤；前端三入口路由 + `VITE_ENABLED_SCENARIOS` 开关；投标自查"报告下载后销毁"(复用 delete_project_cascade)；评后监督只读视图。**补架构文档** `.ai_state/architecture/product-tender-three-scenario.md`（critic gap）。
- **原则风险（critic）**：阶段一场景隔离是 **UI 层过滤非 RBAC**，须在交付说明标注"真正权限隔离待 RBAC sprint"，防安全边界误判。
- **测试**：新增 test_tender_scenario.py + 前端 bun test + 自查端到端(上传→下载→销毁→404)。
- 依赖：**S5**（复用 getAdvisoryLabel；同改 analysis-workbench/report-view，须顺序避冲突）。refs：会议结论1-3/8、待办5。

### 流 I — 基础设施（infra）

#### S7 · model-eval-flash（effort M）★ 本周优先
- **目标**：固定标书样本量化 Flash vs DeepSeek V4Pro 的 速度/成本/准确率/上下文截断风险，工程层加截断防护。
- **范围**：新建 tests/eval_tender.py(复用 audit/eval.py 骨架) + tender_golden_manifest.json；config.py 加 `get_flash_model_config()`；tender_worker 加 `TENDER_EVAL_MODEL` 覆盖 env；agent_bridge 加 `MODEL_CONTEXT_WINDOW` 不匹配 WARNING。只加新文件/旁路，不改判分。
- **测试**：纯离线单测(env 注入/context warning) + 部署机手跑评测对比。
- 依赖：无（可与任何 sprint 并行）。refs：会议结论5/待办3。

#### S8 · security-data-lifecycle（effort M）
- **目标**：任务完成销毁源文件+全量 OCR 文本；管理员不可见原始标书；session 日志脱敏；可信数据空间接入点 ADR。满足会议结论4。
- **范围**：session_start prompt 截断(168KB→500字)；评标完成即删 submission + 清 bid_doc.ocr_text（**保留招标 project_doc.ocr_text 至全部家评完**——critic 标的行为变更红线）；results.payload TTL NULL 化；DELETE /tasks/{id}/submission 端点；maintenance 改周期后台任务；RBAC ADR + 可信数据空间 ADR + **docker-compose 容器加固**(非root/只读fs，critic gap)。
- **测试**：test_security_lifecycle.py(销毁/脱敏/幂等/payload NULL) + 全量回归。
- 依赖：建议在重构流后（降 merge）；backend 端点可独立先做，前端"下载后删除"触发在 S6 集成。refs：会议结论3-4。

#### S9 · kb-and-external（effort L）
- **目标**：补全通则层 KB 缺口法规 + 为外部数据源(信用中国/公共资源交易/四合一/营业执照/在建工程/业绩资质)建统一适配抽象；有配置自动查降 manual_review，无配置优雅降级。
- **范围**：/init-rules 补 knowledge/tender 法规；server/ops/ 加 ExternalDataAdapter Protocol(仿 credit_api.py)+各源 stub+.claude/contracts/tools schema；标注采购/函件依赖(external-sources-catalog.md)。**只建脚手架，不接真实接口**(采购未定)。
- **原则风险（critic）**：新增通则层 rule_id 注意幻觉闸误报（notes 写精确条款限制）；通则层不得混入项目评分标准。
- **测试**：各适配器四路径单测(仿 test_credit_api.py) + test_kb_rules_schema.py。
- 依赖：**S3 + S4**（ops 结构稳定后落点才定）。refs：会议结论6-7/待办7-8。

## 执行波次（并行 + 依赖）

| 波次 | Sprints | 说明 |
|---|---|---|
| **Wave 1（本周）** | S1, S2（重构热身·CC后端）｜S5（advisory·前端红区·本周优先）｜S7（model-eval·独立只加文件） | 互不冲突，可并行 |
| **Wave 2** | S3（OCR 合并+分层）→ S4（output 抽离） | S3 是用户强调项；S3→S4 顺序降 merge |
| **Wave 3** | S6（scenario，依赖 S5）｜S8（security，重构后做更稳） | — |
| **Wave 4** | S9（kb+external，依赖 S3+S4） | 收尾 |

> 注：S3（OCR 合并）虽排 Wave 2，但相对独立、是用户明确优先项，如想先啃可提前到 Wave 1（与 S1/S2 同 worktree 顺序）。

## 待用户决策（启动前需拍板，汇总自各 sprint open_questions）

1. **[S7 阻塞] Flash 具体模型 ID + 端点**：是 deepseek-chat / v3 / 其他？与 V4Pro 同网关(只换 MODEL_NAME)还是独立 base_url？
2. **[S6] 场景隔离强度**：阶段一用 UI 过滤(用户可绕路由) 还是三套 tenant token/独立部署？
3. **[S5/S6] 专家侧 verdict 展示**：完全隐藏只留风险清单，还是显示"通过(供参考)"？监督场景同页 role 分支还是独立路由？
4. **[S8] SQLite at-rest 加密**是否纳入（platform.sqlite3 含全文+结论，不加密则磁盘访问绕过 API 隔离）？session JSONL tender 域删除天数(建议3天)是否满足留痕？
5. **[S9] KB 范围**（除 evalmethod/regulation 外要不要财政部87号令/地方规范）+ **外部数据采购优先级**（信用中国最高？）。
6. **[S5/S6 执行] agent-front 红区授权**：前端改动需你明确授权 + worktree 隔离，确认才动。

## Backlog（critic 标的延期项，勿遗忘）

- 审计 F3 余量：`_initialize_schema×10` 合并 + `tender_task_store` 并入 task_store（跨域、面广）。
- 容器运行时隔离实落（S8 出加固，TEE/机密容器实现待排期）。
- 可信数据空间具体实现（TEE/网络隔离，依赖方案团队）。
- 外部数据**真实接口**联调（依赖采购/政府函件）。
- RBAC 实现（S8 只出 ADR）。
