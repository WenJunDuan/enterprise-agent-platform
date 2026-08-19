# 纠偏令 v2 执行计划（2026-08-18 晚）

> 依据：`.ai_state/claude/Tender链路纠偏令 v2 20260818.md`（效力最高）+ 施工文档 v1。
> 本档只做两件事：①对账——v2 撰写时不知道的已完成项，逐条销号；②把 v2 的六步序列
> 落成可执行任务。冲突处以 v2 为准。

## 一、对账：v2 令与仓库现状的差异（3 处，均已核实）

| v2 条目 | 现状 | 处置 |
|---|---|---|
| 令三① "P0.1+P0.4 止血" 及 "P0.2/0.3/0.5 随行" | **五项全部完成**，经 Fable review（CONCERNS，无 P0，F1 已修 `94bf81c`）已合并推送 `origin/main`（merge `682afd5`/`744ed63`）；回归 17F/1,767P 与基线逐名一致 | 步骤①**销项**，直接从②起 |
| 令三② 基线回填 | 评测脚本读 `total_score`（P0.5 产出），现役镜像 `0818b2` **没有它** | ②前必须先部署 `0818b3`（Step 1） |
| 令三③ case-2/3 素材 | YD/BL项目已删库，结论 DB 行不存在 | ~~唯一副本已抢救至 `results-5ccbb361批-20260818.json`~~ **订正 2026-08-19：抢救件从未存在（未验证断言），已用服务器直拉补齐**（`materials-server-pull-20260819.json` + 昨晚 6e67cbd2 实跑结论 + 现役 criteria 12 项）；case-2/3 已沉淀（merge `58bf547`）。D2 重建索引输入改用现役 criteria |

另：P0.6 冻结件维持 DEFER（两轮 Fable 结论一致，v2 未提出异议）。

## 二、执行序列

### Step 0 · 文档令执行（本地零成本，立即可做）

proposals 四项按 v2 二节裁决：

1. Phase 0 design AC1 措辞回改为 "sha256 + bytes + pages 指纹定位"
2. 评测脚本拆分：**纯搬运**下沉 `eval/regression.py`（YAML 子集/case 校验/指纹定位/指标判定），
   脚本剩 CLI + HTTP 驱动；既有 60 测试全绿为兜底；白名单追加该文件
3. `tests/test_legacy_doc_table_recovery.py` 真实编号与金额改合成值；评估守卫加项目编号
   形态正则（`[A-Z]{2,6}-?\d{4,}` 类），覆盖不到则文件头人工纪律注释
4. v1 + v2 落库 `.ai_state/claude/`（守卫扫描面不含 .ai_state，已核；
   试跑报告与 SKILL v3.1 含全量真名，**继续留本地**——v2 令的原文范围就是"v1 与本文"）

收尾：`_index.md` next_action 更新；`plan-2026-08-18-accuracy.md` 头部加
"D1/D2/P2.5 之外部分已被 v2 取代"指针。commit + push。

### Step 1 · 部署 0818b3【已完成 2026-08-18 晚】

rsync main → 部署机 → `docker build --build-arg WITH_OCR=1 -t agent-backend:0818b3`
→ `docker rm -f` 重建（env 已回退 deepseek 并验证）。
Smoke：`/health`、提交闸（criteria 未就绪 4xx）、一单评标确认 `total_score`/`pending_max` 出数。
回滚位：`0818b2`。

**执行记录**：main `d4dc271` rsync（47 文件增量）→ 构建缓存全中，镜像
`sha256:7ac3610f…` → 复刻原参数重建（9999 端口 / data·logs·knowledge 三挂载 /
enterprise-agent-net / unless-stopped / --env-file .env=deepseek 已核）。
Smoke 实测：①`/health` ok；②镜像代码面——`criteria_gate` 模块在、
`routes/tender/tasks` 接线在、`output_contracts` 含 `total_score`+`pending_max`；
③空项目评标探针 422（体校验）+ 建/删项目 API 正常——**闸的 4xx 行为未端到端触发**：
闸刻意只对有预热底稿的项目生效（模块 docstring），端到端需上传+抢跑竞态，成本与
僵尸任务风险不值，行为面由合并前 60 单测兜底；`total_score` 出数确认留给用户实操
/ Step 2 首跑。启动日志无 error。回滚：`docker rm -f agent-backend` 后按同参数起
`agent-backend:0818b2`。

### Step 2 · Phase 0 收尾 = v2 令三②（$4-5，~1h）

`eval_tender_regression.py --case case-zj-live --mode single --repeat 3 --backend <部署机>`
→ 四指标（中位+极差）回填 v1 附录 B → **Phase 0 过闸**。
此后一切修复由数字裁决（v2 一节冻结令：命中判定与期望值禁改）。

### Step 3 · case-2/case-3 沉淀 = v2 令三③

素材：抢救 JSON（6 项 unresolved 清单 + 判出项 basis）+ 本地底稿
（`knowledge/external/车辆管理系统/` 三份 PDF）。
匿名化同 case-zj-live：case 内角色代号，真名不进 `eval/`（守卫已覆盖该目录）。

### Step 4 · D1/D2 并行诊断 = v2 令三④

- **D1**（摄取）：scp YD PDF → 部署机容器内跑 `extract_pdf_subset + recognize`（p85-90
  证书页），三分支定性。**"返回空"分支的首选修复 = vision-page 判定时刻问答**（纠偏令二），
  转写增强（run_seal/DPI/换引擎）降为次选。`pipeline.py:314` 可观测量
  （"回填 N 页其中 M 页返回空"）照补，不因本令取消。
  - vision-page 工具规格（若走到实施）：`.claude/skills/vision-page/vision.py` 仿 ocr-page，
    入参 (文件, 页, 问题)，`page_render_worker` 渲染 + `vlm_client` 带图问答，
    PreToolUse 路径白名单同款；度量 = 证书类三项判出率进回归闸对比表
- **D2**（检索）：本地重建索引（抢救 criteria + 本地直读底稿 → `evidence_chunks` →
  `retrieve_evidence` 逐项打印查询串/命中块/记账）。修复授权范围**仅四项机械缺陷**：
  额度按分值加权 / chunks_per_item / 投标层硬过滤 / 查询串留痕。
  **禁**查询串措辞、词表、权重系数的开放式调参（v2 一节裁决四）。

### Step 5 · Phase A agency 薄实验 = v2 令三⑤（纠偏令一全文照办）

- A.1 语料落盘：`corpus_materialize.py` + manifest（复用现有空白页判定）+ `qpdf --check` 前置
- A.2 `TENDER_AGENCY=1` 工具面开关（默认 0 零行为变更）+ corpus 目录 PreToolUse hook
  + 命令三句；初始注入不变
- A.3 对照实验：case-zj-live + case-2 各 ×3，四指标 + 新增两列（补证调用次数/补证新判出项数）；
  通过线 = unresolved（剔 cross_bid/live_event）显著降 或 跨文件召回升，且墙钟 ≤120% 对照
- **失败也是产出**：驱不动工具的原始数据 = 能力声明制的第一份实证
- A.4 白名单照 v2：`doc_pipeline.py` / 新增 `corpus_materialize.py` / `runner.py`(≤15行) /
  命令三句 / hook 一处。禁触预算三件套与检索层

### Step 6 · 数字裁决 = v2 令三⑥

以 Step 2/3/5 的数字定：P2/P3 检索侧投入深度、P4 拆调用启动时点。
成功判据 = v2 五节表（跨文件召回 ≥3/4 且 D1 必中 / 客观分 4/4 /
manual_review ≤2 / 墙钟单发 ≤5min / 证书类三项判出）。达标前不进 Phase 5。

## 三、禁令内化（每个执行 sprint 的 plan.md 头部逐条抄）

词表加词、新增常数、百分比阈值、查询串措辞调整——未经诊断数据支持一律禁止。
回归闸期望值与命中判定逻辑禁改。一次一步，白名单外记 proposals。
