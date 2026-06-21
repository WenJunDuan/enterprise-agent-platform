# Goal · 多模型评标优化 Sprint（2026-06-22 起）

> 用户设定（2026-06-21 晚）：多模型轮换测试持续优化评标质量与性能，自测 + 自调优，每轮 codex 配合。

## 一、目标（优化方向）

1. **OCR 速度与效率** —— 上传即 OCR 已解耦（第6轮），继续压速度/准确度（扫描件/盖章/表格还原）。
2. **招投标审核速度与准确度**：
   - **抓取招标评分点和分数**（criteria 提取：评分项/满分/扣分点/废标条款，准确不漏不错）。
   - **应标数据正确抓取 + 对应上下文**（投标抓点：投标人/报价/业绩/资质 + evidence_chain 对应到正确出处页）。
3. **数据存储**（三层数据结构正确性：招标层项目级一份 / 投标层每家 / criteria 回填复用）。

## 二、工作方式

- **多模型轮换测试**（.env 切 MODEL_NAME + MODEL_BASE_URL + MODEL_AUTH_TOKEN）：
  - **DeepSeek**：`deepseek-v4-pro` @ api.deepseek.com/anthropic
  - **qwen3.7-max**：`qwen3.7-max` @ dashscope.aliyuncs.com/apps/anthropic
  - ~~claude-opus-4-8 @ anyrouter.top~~ **（2026-06-22 用户：去掉 anyrouter，偶发 429）**
  - **openrouter**：`z-ai/glm-5.2` @ openrouter.ai/api/v1/chat/completions（替代 anyrouter；注意 base 是 OpenAI-compat `/chat/completions`，与本项目 Anthropic-protocol SDK 是否兼容**待 R3 轮换实测**）
- **每改完一版自测**：起后端(`uv run python -m server.cli serve`) → 调 API(上传/评标) → 看 serve.log + 评标结果(verdict/scoring/claim_id/耗时) → 自己定下一步调优方向。
- **范围**：`.claude/`(prompt/契约) + Python `server/`(OCR/评标/store) + `agent-front/`(前端对接)。
- **每轮 codex 配合** review（codex exec --sandbox read-only）。每轮可 generator subagent(worktree) 实施大块。
- 模型差异要点：**思考流式实时性依赖端点是否流式吐 partial**——claude/deepseek 文本模式吐多片段(实时)，**qwen 一次性返回(不实时)**，见遗留①。

## 三、本会话遗留问题（待本 Sprint 处理）

| # | 问题 | 现状/方向 |
|---|---|---|
| ① | **qwen 思考流式不实时** | qwen 端点一次性返回(session log 仅 1 个 assistant_text)，on_progress 只在结束触发一次、flusher 已 cancel → progress 停"运行中"。修：开 `include_partial_messages` + run_agent_json 处理 StreamEvent partial(要试 dashscope 是否支持流式 SSE)；或简单兜底 flusher 退出前最后 flush 一次。 |
| ② | **criteria 项目级回填验证** | 第6轮已实现 `update_project_doc_criteria`(评标后回填、后续家复用治"每家重复解析")，**待端到端验证**首个写入赢 + 后续家读已存。 |
| ③ | **compare 首次横比 refetchInterval 停** | codex r5 P1-5 未修：triggerTenderCompare 异步，compare 查询 404/null 时 refetchInterval=false → 首次横比没生成停空。多家完成后边缘。 |
| ④ | **delete 磁盘目录清理** | 第6轮 delete 级联清了两表，但 `data/submissions` 下 OCR 产物目录可能未清(codex P2 P1-5)。 |
| ⑤ | **G5 S2 公式变量清单** | 第3轮 codex P1-2 backlog：限价类 formula 单家算需 S2 抽 limit_value/bid_component/formula_variables 结构化(现 S3 靠模型从底稿临场找)。 |
| ⑥ | **招标人侧合规 MVP** | design-r2 未 impl：排他性条款/可量化性/废标清单/投标时限规则。先 /init-rules 补 tender_regulation_032 + 时限到 knowledge/tender。 |
| ⑦ | **OCR 置信度深化** | design P2：扫描盖章页/手写低置信 → file_clarity 标注 + 提示人工(接 G3 触发)。 |
| ⑧ | **effort 对各端点支持** | effort=xhigh(tender per-call) 对 Claude 原生支持；deepseek/qwen 兼容端点是否透传/有效待验(qwen 评标跑通但 effort 是否生效未确认)。 |

## 四、已有基础（本会话第1-6轮成果，git main，29 commits 未 push）

- **第1-2轮**：criteria 提取从2项→20项精准(C 根因 normalize 剥未知字段 + cowork G1-G7 prompt) + A absence-not-zero + OCR 性能轮(并行/缓存/线程安全)。
- **第3轮 G5**：formula 公式变量结构化 formula_spec(限价类单家可算/白名单派生/拆子项/阶梯走 banded)。
- **第4轮**：thinking effort(tender per-call xhigh) + logs 三项(清噪音/思考日志/轮转) + 思考流式(轮询伪流式 progressByRid)。
- **第5轮 A+B**：长任务体验解耦(评标不阻塞前端/独立轮询/可离开回来恢复/不超时掉回/完成跳分析中心)+ 后端 TENDER_TIMEOUT_SEC 3600 兜底。
- **第6轮 C(P2+P3)**：三层数据(tender_doc_store) + 上传即 OCR 解耦(tender-doc/bids 端点后台 OCR 预热 + docs-status 轮询 + 评标读层单家) + 前端三区布局 + 拆"上传/开始分析"两步。codex P2 REWORK→全修(读层单家防污染/OCR并发/失败failed/强制文件/tenant)。+ ClientDisconnect 捕获 + analyzing 假死能返回列表。
- **端到端验证(qwen3.7-max)**：评标 completed 225s(比之前 537s 快一半，OCR 解耦+读层命中) / verdict rejected(投错标废标正确) / 20项 scoring / claim_id 正确。
- **558 passed + ruff + 前端 lint/build**。git 干净(只 main、零未 commit)。

## 五、关键操作备忘

- **dogfood**：项目级 `POST /tender/projects/{id}/evaluate`(无绑定 /tender/evaluate 要 __unbound__ 路径)；素材 `data/submissions/default/tender/tp-f856d66c0e244467/case`；绝对路径 + `mode:"directory"`；token = `.env` TENANT_KEYS JSON 的 `.default`。
- **上传即 OCR 测**：`POST /tender/projects/{id}/tender-doc`(招标)、`POST .../bids`(投标 + bidder_name form 字段)、`GET .../docs-status`(轮询)。multipart `-F "files=@路径"`。
- **mac mini 部署**：rsync(非 git)；SSH 直连 `mac@100.107.151.115` ConnectTimeout30 + StrictHostKeyChecking=no(.ts.net 域名解析慢用 IP)；远程登录需开。
- **cat 被 alias 成 bat(未装)**——用 Read/grep 别用 cat；查 mac mini 日志用 ssh 远程 grep。
- **本机 cat 别用**(bat alias)；读 token 用 `rg -o 'TENANT_KEYS=\{[^}]*\}' .env | sed | jq -r '.default'`。

---

## 六、6 轮执行计划（2026-06-22 用户扩定，本 Sprint 主线）

> 用户指令（2026-06-21 晚二次澄清）：跑 **6 轮 PACE + 接口自测**，**每轮自己测**，**每轮至少切 3 家 AI 环境自测**。
> 关注面（用户原话优先级）：OCR 速度/准确度 · 流式输出与审核速度 · 数据挖掘速度/准确度 · 页面显示正确+美观+交互；
> **最核心 = 招投标审核数据准确 + 扣分项准确 + 上下文定位与显示**。
> 原则：短增量、每轮 commit + 回写本节、codex 配合 review；长任务 agent 必断（见 memory 教训）。

### 三模型轮换机制（已核实可用，2026-06-21）

`.env` 顶部 4 个模型块（注释切换，token 均在）：①本地 litellm `127.0.0.1:4000` ②DeepSeek `deepseek-v4-pro[1M]` @api.deepseek.com/anthropic ③claude-opus `claude-opus-4-8[1M]` @anyrouter.top（强制[1M]+偶发429）④qwen `qwen3.7-max` @dashscope（当前激活）。
`server/platform/config.py:97-100` 读 `MODEL_BASE_URL/MODEL_AUTH_TOKEN/MODEL_NAME`（os.environ 覆盖 .env）→ **非破坏切换**：起 serve 前在 shell `export MODEL_*`（值从 .env 注释块取），不动 .env。每轮 3 模型各跑一遍核心自测。

### 本会话用户新提 3 个 bug（已定位根因，并入对应轮）

- **B-A 区1 基本信息显示不全**（analyzing-view.tsx:101 `Zone1ProjectInfo`）：只读 `projectForm` 手填表单，空字段被 `.filter` 滤掉 → 默认大片空。根因：项目元数据从不由 OCR 回填。→ **R1**
- **B-B 区2 应显示招标信息**（analyzing-view.tsx:152 `Zone2OcrOverview`）：只显示 OCR 状态圆点 + 占位；`docs-status` 仅回 `ocr_status`，无任何抽取内容；criteria 仅评标 S1 抽、评标后才回填、且无读接口。→ **R1**
- **B-C 返回列表后回不到"分析中"界面**（use-tender-review-page.ts:396 `exitAnalyzing` 清 activeEval+localStorage；dashboard `onOpenProject`→`openAnalysis('detail')`→`screen='analysis'` 分析中心，非 'analyzing' 进度页）：进行中项目从列表点开落到空的分析中心，无法 re-attach 实时进度。→ **R3**

### 后端数据流现状（Explore 已核实，R1 据此改）

OCR 上传（`tender.py:741` POST .../tender-doc）只产 `ocr_text` 原文 blob，**不抽结构化招标信息**；`tender_project_docs` 字段：project_id/tenant/tender_files/ocr_text/ocr_clarity/ocr_status/**criteria**(评标后回填,首写赢,无读接口)/created_at/updated_at；criteria 仅评标 worker S1 抽（`tender_worker.py:291-297 _backfill_criteria`）；`tender_projects` 元数据(tender_no/tenderee/control_price/method)**只来自建项目表单，从不由 OCR 回填**；`docs-status`(`tender.py:864`) 只回 `{tender_doc:{ocr_status}, bids:[{bid_id,bidder_name,ocr_status}]}`。

### 轮次划分（主题可随发现微调；每轮含设计 `round-N-{slug}/design.md` + 3 review subagent + codex）

| 轮 | 主题 | 范围要点 | 并入 bug/遗留 | 3 模型自测重点 |
|---|---|---|---|---|
| **R1** | 招标信息抽取前移 + 区1/区2 显示 | tender-doc OCR 完成即抽「招标信息」(criteria 评分项/满分/扣分点/废标 + 元数据 招标编号/招标人/控制价/评标办法 + G5 formula 变量)→存 project-doc，解耦 per-bidder S1 重复解析；新增读接口 GET .../tender-doc(criteria+元数据)；前端区1 fallback(extracted→form)、区2 显真实招标信息 | B-A B-B 遗留②⑤ | criteria 抽取准确度(评分项数/满分/扣分点 不漏不错) |
| **R2** | 扣分项准确 + 上下文定位显示（**核心**） | 投标抽取 evidence_chain 对应正确出处页(投标人/报价/业绩/资质)；扣分项 basis 引用准确出处；一致性风险(项目负责人vs业绩经理不一致 data_conflict)；前端 analysis 中心证据定位(点要点跳出处)+扣分明细 | 核心诉求 | 已知 case 扣分项命中 + evidence loc 准确度 |
| **R3** | analyzing 状态机 + 流式实时 | 返回列表→点进行中项目重进 'analyzing' 并 re-hydrate activeEval(re-attach 轮询)、按 status 路由；qwen 思考流式不实时(include_partial_messages / flusher 退出兜底 flush) | B-C 遗留① | 流式实时性 + 离开/回来恢复 |
| **R4** | OCR 速度 + 准确度 | OCR perf 再压；扫描件/盖章/表格还原完整度；file_clarity 低置信标注+提示人工 | 遗留⑦ | OCR 速度 + 评分表格/扣分行还原完整度 |
| **R5** | 数据存储 + compare + 清理 | 三层数据端到端验证(criteria 首写赢+后续读已存)；compare 首次横比 refetchInterval；delete 磁盘 OCR 产物目录级联清 | 遗留②③④ | 多家 e2e + compare 排名 + delete 干净 |
| **R6** | 页面美观+交互 + 招标人侧合规 + effort + 全回归 | UI polish(美观/交互/4 态/空态/a11y)；招标人侧合规 MVP(排他/可量化/废标清单/时限,先 /init-rules 补规则)；effort 各端点透传验证；整体回归 | 遗留⑥⑧ + 页面美观 | 3 模型 full e2e 回归 |

### 每轮自测协议（接口级，非仅单测）

1. `uv run pytest -q` 绿 + `ruff check .` + 前端 `bun run lint && bun run build`。
2. 起后端 `uv run python -m server.cli serve`（background）→ curl 走真实端点（建项目/上传即OCR/docs-status/evaluate/结果/compare）。
3. **3 模型轮换**：export MODEL_* 切 DeepSeek→qwen→opus 各跑核心自测，记录耗时/verdict/scoring/扣分项/evidence loc 差异到本轮 design 的「自测结果」。
4. 看 `logs/serve.log` 思考流式 + 错误；结果对 `audit-result.schema.json` / criteria.schema.json。
5. 局限：真·视觉美观需用户在 mac 跑 dev 确认（我只验 build/lint/逻辑/契约）。

### 进度回写（每轮完成追加）

- R1：✅ **招标信息抽取前移 + 区1/区2 显示**（治 B-A/B-B + 遗留②⑤部分）。后端：tender-doc OCR ready 后台抽 criteria+tender_info（信号量外，不阻塞开始分析）→ 存 project-doc（新 criteria_status/tender_info 列）+ 回填项目空字段；新 `GET .../tender-doc`；docs-status 加 criteria_status；评标 worker 注入已存 criteria 跳 S1。前端：区1 fallback(extracted→form)、区2 渲染评分项/扣分点/废标/score_mode。契约：新 tender-info.schema。**3 模型自测**：qwen✅163s/deepseek✅142s(覆盖最佳) 各 14 项 Σmax=100；opus❌ anyrouter429(基建,优雅降级)。590 passed+ruff+前端 lint/build。codex(P1/P2)+reviewer(F1-6)+spec-compliance(PASS) 全处置。详见 round-1-tender-info-extraction/design.md。**遗留**：opus 重试验证；criteria 复用读路径端到端验证留 R5。
- R2：🟡 **扣分项展示 + verdict 一致性**（核心的"显示"半 + verdict 修复已做；"扣分项准确度调优"按用户决策待匹配投标）。①前端：model.ts 透传 scoring[].deduction_hits/award_hits/manual_review_reason/score_mode → 分析中心区3 展开显逐条扣分(扣分值+命中条件+投标原文quote+出处页) + manual 原因徽章（治"上下文定位与显示"）。②后端 verdict 纠偏：normalize_audit_result 对 disqualification_hits 非空/eligibility fail → 强制 rejected（治"投错标判成 manual_review"，实测真实结论 manual_review→rejected✓）。**基线发现**：dogfood 烛照=投错标→20项全 manual_review（absence-not-zero 正确，无扣分可评）；deepseek 全量评标不可靠（漏 reasons 3次重试），qwen 可靠(335s)。593 passed+ruff+前端 lint/build+17前端tests。**待用户**：提供一份对应「华为南通」项目的投标文件，才能实测+调优扣分项命中/明细/出处页准确度。
- R3：🟡 **analyzing 状态机 + 流式**。①**B-C bug ✅**（用户原话"返回列表回不到分析中界面"）：新 `resumeOrOpenProject`——进行中项目从列表/历史点开→重建 activeEval + 'analyzing' 屏 re-attach 实时轮询，非落空分析中心；全完成→分析中心；失败回退。前端 lint/build/17tests 绿（待用户 dev 眼验）。②**遗留①流式 + openrouter 兼容实测 待做**：flusher 退出兜底 flush + include_partial_messages；openrouter(OpenAI-compat) 与 Anthropic-SDK 兼容性 R3 三模型轮换实测。
- R4：_pending_
- R5：_pending_
- R6：_pending_
</content>
