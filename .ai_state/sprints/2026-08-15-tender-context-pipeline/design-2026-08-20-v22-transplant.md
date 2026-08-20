---
sprint_slug: "2026-08-15-tender-context-pipeline"
parent_design: "design.md"
created: "2026-08-20"
status: "R1 critic NEEDS_REVISION 已全响应（F1 基线复测 / F2 超时账+重试分家 / F3 改口三防线 / F4 锚页AC+残留声明 / P2 七条），可开工"
authority: "v2.2 行为移植令（.ai_state/claude/，效力最高）+ handoff-2026-08-19（含四之二节三裁决）"
executor: "红区（Refactor 路径）：代码刀 generator subagent + isolation worktree 强制"
---

# Design 增补 — v2.2 行为移植批次（K0–K11）

## 背景

v2.2 双跑对照的裁决：**指令层已对，差距在运行时手段**（工具面锁死 / 单发无补证轮次 /
vision 未进判定流）。移植主体 = 把手段还给模型 + 确定性工作下沉代码 + 契约与回归闸验收行为。
本档把 v2.2 五节白名单 7 项 + handoff 三节队列的前置件落成可实施设计；每刀均以本会话
侦察实测的 file:line 为锚（三路只读侦察 + 主 agent 复核，2026-08-20）。

**覆盖**：K0 历史抹净扩围 / K1 case-4 金标准 / K2 office native / K3 混合页 manifest /
K4 抽取重试+心跳 / K5 tool_call 计数 / K6 attempted 契约+回查闸两刀 / K7 D2 四修 /
K8 度量列 / K9 facts_precheck 三扩 / K10 示教 references / K11 vision 支线。
**不覆盖**：Step 5/6 实验本体（按 plan-v2 + v2.1/v2.2 执行）、vision 端点部署（卡 qwen VL）。

## 已调研的现成方案

| 需求 | 候选 | 判定 |
|---|---|---|
| office→PDF/docx 转换 | LibreOffice soffice | **采用（已在用）**：`server/ocr/office_convert.py:106` `convert_office_to_pdf(target="pdf"|"docx")`，禁宏 profile + 魔数校验齐备，零新增 |
| docx 结构化抽取 | python-docx==1.2.0 | **采用（已在用）**：`read_word` 现役，表格走原生 XML，镜像已装 |
| 页图面积 | v2.2 提议 `pdfimages -list`（poppler-utils） vs pymupdf | **选 pymupdf**：主依赖（pyproject:34），`read_pdf_text` 页循环本就逐页持有 page 对象（`native.py:363-371`），`get_image_info()` 顺手 ~10 行。poppler 否决：新增系统依赖 + 子进程 + 解析文本输出，全仓现零使用 |
| 结构失败重试环 | 自建 vs 复用 contract_repair | **复用**：`_run_extraction`（`doc_pipeline.py:288`）已有失败喂回-resume 修补环，K4 只是把结构校验挪进环内 |
| 历史重写 | git filter-repo vs BFG | **filter-repo**：需要 `--replace-text`（串级抹除，BFG 只擅长整文件/单串），且支持 `--invert-paths` 同跑 |

## 已验证基线（量化 AC 出处，单写者下界口径）

| 基线 | 实测值 | 测量命令/出处 |
|---|---|---|
| 全量回归 | **17F / 1,965P 逐名稳定** | `uv run pytest -q`（主 checkout；17F 全为 OCR 可选依赖既有失败，handoff 六节） |
| 评标命令提示词 | **39,966 B**（预算 40,000，余 34） | `wc -c .claude/commands/tender-evaluate.md`（2026-08-20 实测） |
| 行数（本批触碰文件） | facts_precheck 262 / corpus_materialize 298 / draft_render 166 / native 424 / classify 133 / office_convert 193 / **evidence_retrieval 275** / **evidence_continuation 125** / **SKILL.md 22** | `wc -l <逐文件>`（2026-08-20 主 checkout 复测，R1-F1 订正）。**均未越 300 硬线**（298 与 275 贴线，改动落其上若越线随刀拆） |
| 行数（既有越线债，本批只挂靠不扩张） | doc_pipeline 712 / output 717 / evidence 478 / **regression 1,134** / worker 510 / pipeline 884 / agent_bridge 690 | 同上；**豁免声明**：基线已越线对象，本批各刀增量 ≤40 行/文件且不新增越线文件（K9 例外见其节） |

> **R1-F1 订正记录**：本表初稿有 4 行系从旧档转述而非实测（evidence_retrieval 误作 332、
> evidence_continuation 误作 103、regression 误作 1,135、SKILL.md 误作 23）。已全行复测改正。
> 教训同 coding-standards「引用他处数字须注出处或复测」——**K7 的落点理由据此重述**（见 K7）。
| ZJ语料 | 400 页；图页+混合页 ≈24%（81+16/400） | v2.2 §三.6 实测 |
| 抽取随机性诊断 | 同文件 11:38 `item_max_invalid` / 11:41 通过 | proposals P1（2026-08-19 实测）——K4 重试上限=2 的数据支撑 |

---

## K0 · git 历史抹净扩围（程序刀，主 agent 执行，无产品代码）

**新事实一（本会话侦察）**：除已知两份 ignored 真名档（历史 5ea30c2..000761a）外，
**v2.2 移植令本身被 git 追踪且已随 `7753d22` 推上 origin/main**，正文含真实人名、
完整身份证号、公司名（附录A）。此前 Step 0 的既定策略是"真名档留本地不入库"
（plan-v2 Step 0 第 4 条），v2.2 落库破了这条线——根因：真名守卫扫描面不含 .ai_state。

**新事实二（2026-08-20 全 tracked 扫描，推翻本节初稿的范围假设）**：污染远早于、远宽于 v2.2。

| 串类 | tracked 文件数 | 涉及提交数 | 最早 |
|---|---|---|---|
| 个人身份信息（3 人名 + 2 身份证号 + 1 信用代码） | 1（v2.2） | 1–3 | 2026-08-19 |
| 招标人/项目名 A | 15 | 24 | **2026-06-23**（`d26d90d`） |
| 其他客户项目名 B / C、招标编号 | 5–6 / 1 | 2–7 | 2026-08 / 2026-06 |

仓库为 **私有仓**（GitHub 匿名不可见），总提交 818。

**用户裁决（2026-08-20）：全范围抹除**——个人信息 + 客户项目名 + 招标编号一并抹。
代价已知并接受：重写自 `d26d90d`(2026-06-23) 起的全部提交（hash 全漂移），
十余份设计档的叙事被代号替换、可读性下降。

**代号映射**：沿用 `eval/golden/` 既有约定（case-zj-live 已用 zj 代号），一表通用于
K0 / K1 / K10；映射表存 ignored 备份区（`.ai_state/backups/`，已加 gitignore），不入库。

**执行序（一次重写覆盖全部，避免二次 force push）**：
1. 导出 P0.6 冻结 worktree `agent-aceea5e2cd5e05986` 改动为 patch，存 ignored 备份位
   （兼作 Phase 2 对新 main 重对齐底稿；force push 后该 worktree 基提交失效）
2. 工作副本匿名化：v2.2（及 `git grep` 复扫全部 tracked 文件）中人名/证号/公司名 →
   角色代号（**与 K1 case-4 用同一张映射表**，映射表本身存 ignored 位置），commit
3. 全历史敏感串清单：逐串 `git log -S<串> --all --oneline` 核对波及面，产出
   filter-repo `expressions.txt`（串→代号）
4. fresh clone → `git filter-repo --invert-paths --path <真名档1> --path <真名档2>
   --replace-text expressions.txt`
5. `ATHENA_ALLOW_PUSH=1 git push --force origin main`（守卫放行走既定 flag，不绕行）
6. 本地重整（重 clone 或 fetch+reset）；handoff 补一行 hash 映射注（08-18 起 hash 全漂移）

**风险**：部署机走 rsync 不依赖 git 历史，无影响；单人仓无协作者重 clone 成本。
**记 proposals（不顺手改）**：真名守卫扫描面扩到 tracked `.ai_state/`，防复发。

## K1 · case-4 金标准落盘（v2.2 #3，先于一切代码改动）

**落点**：`eval/golden/case-zj-full/{expected.yaml, corpus.pointer.yaml}`。
规范全盘照 case-zj-live（侦察实测）：角色代号 + 页锚 + 类别枚举，不出现真实机构/人名
（`eval/golden/case-zj-live/expected.yaml:6-8`）；语料只留 sha256 指纹不留路径
（corpus.pointer.yaml 刻意设计）；守卫 `tests/test_no_real_corpus.py` 罩 eval/。
与 case-zj-live 同源语料 → pointer 的 sha256/bytes/pages 直接复用。

**8 判定点 → expected.yaml 结构映射**（期望值底稿 = v2.2 附录A）：
- `defects[]`：制造商矛盾+营收雷同（cross_doc_contradiction，锚 p12+p6-7）/
  投标有效期缺席（`absence: true` + must_include）/ 混合页证书判出（锚 p315-316）/
  检测依据两跳链（锚 p364+p369）/ 常规 0 正偏离（zero_positive_deviation，锚 p349-360 区间）/
  CS2 等级语义（数字升序，口径**待验证**记弱键）/ 大写金额勾稽（图页，锚 p5，attribution=pixel）/
  信用代码末位差异（弱键，低置信）
- `objective_scores[]`：企业实力 6/6、业绩 9/9、负责人 3/3（attribution 按 K8 扩后四列登记）
- `price_check`：`total: 1316033.66`（金额保留有 case-zj-live 先例；case-2/3 停用勾稽是
  各自匿名化口径，不适用本 case）

**锚页纪律**：锚在证据实际页（p5/p7/p12/p315-316/p345-348/p349/p361/p364/p369/p376），
不锚系统输出页——v2.1 一节冻结的金标准规范。
**AC**：`--dry-run` `check_case` 过（`eval/regression.py:1106`）；真名守卫全绿；8 判定点全登记。
**依赖**：attribution 四列枚举在 K8（先落 K1 用现枚举 text|pixel，K8 落后回补两条归因值，
期望值语义不变——只改登记列不改命中判定，合规）。

## K2 · office native 优先摄取（v2.2 #1，P0，≤60 行）

**现状与 v2.2 判词的出入（侦察实测，设计必须先对齐事实）**：`.doc` 现行链路**不是**
"转 PDF → OCR"——`read_legacy_word`（`native.py:301`）首选 `_legacy_word_via_libreoffice`
（`:267`）：soffice→PDF→**文本层直读**（`:284-285`，`read_pdf_text` 用 pymupdf
`sort=True` + 逐页 `find_tables`，表格带真实页号），失败才降 docx→`read_word`（`:291-295`）。
且 PDF-first 是 08-17 `57ce023` 特意改的：**docx 路线无页号，页锚是证据链前提**。

**张力裁决**：57ce023（页锚）与 v2.2（表格保真）都对，对象不同——页锚服务**证据底稿**，
表格保真服务 **S1 规则抽取**。方案按消费者分流，不全局改道。

**步骤一（复现实验，先于改码，本地跑真语料）**：ZJ招标 .doc 分别过
(a) 现行链路（soffice→PDF→read_pdf_text）(b) soffice→docx→read_word
(c) 检查 (a) 中 find_tables 对评分表页的输出，diff 评分表"序号 2 行"区域，
定位损坏环节（soffice PDF 导出 / get_text / find_tables 三选）。匿名摘要记 evidence.yaml。

**步骤二（按实验结果分支）**：
- **首选（docx 线无损时）**：S1 侧增补而非摄取链改道——criteria 抽取上下文装配处
  （`doc_pipeline.py:395-405`）对 .doc/.docx 招标文件追加「原生表格附录」块
  （soffice→docx→python-docx 抽表，按章节标题锚定），底稿与页锚主链**零改动**，
  S1 拿到无损评分表。criteria 出处仍引底稿页锚（同内容在 PDF 线有页有锚，只是表行残）。
- **备选否决**：全局 docx-first（毁 57ce023 页锚，否决）；双转换页码对齐（复杂度超预算、
  无第二消费者，反过度工程否决）。
- **若 docx 线同损**（soffice 转换本身打坏）：不盲改，实验数据记档、列D 归因修订报用户裁决。

**残留面声明（R1-F4，防列D 被误记为"已闭"）**：本刀只治 **S1 规则抽取**这一个消费者。
**不治**：①底稿与 corpus 里的残缺表行原样留存（agency 臂 Grep 看到的仍是残行）；
②投标侧 .doc 表格损坏同样不治（v2.2 #1 原令是摄取级 native 优先，本刀降为 S1 级增补）。
两项残留归 Step 5 列D 记账，不得计入本刀战果。

**AC**：既有 `.doc` 夹具（`tests/test_legacy_doc_table_recovery.py` 一族）扩评分表形态：
红=现行链路评分表行缺损断言（复现），绿=S1 上下文含完整表行；
**＋锚页正确性断言（R1-F4）**：夹具须断言 criteria 逐项 `source_ref` 页号指向该表行真实所在页
——附录块给的是无页号的原生表格，若 S1 拿附录内容却对不上底稿残行所在页，会产出
"附录有内容、锚点指残行"的错位，比不修更坏。对不上时 criteria 该项须落
`source_ref` 缺省而非猜页。回归 17F/1,965P 逐名不回退。

## K3 · manifest 混合页列 + 底稿占位（v2.2 #2，P0，≈30 行）

**现状（侦察实测）**：`kind` 按**文件级** route 判（`corpus_materialize.py:144-153`）：
blank（`pipeline._blank_page_count`，阈 `MAX_BLANK_CHARS=20`，`pipeline.py:84`）→
route=="ocr" 全记 image → 否则 text。**混合页（标题文本+图像正文）恒记 text**——
v2.2 判的"伪装成已命中"正是它。全仓无任何页级图面积字段。

**方案（单一事实源：摄取时算，渲染时标，物化时读）**：
1. `read_pdf_text` 页循环内（`native.py:371`，FITZ_LOCK 已持有）`page.get_image_info()`
   求 `ratio = Σ图 bbox 面积 / 页面积`（截 1.0），result 增 `image_ratios: list[float]`
2. `draft_render._render_paged_blocks`（`draft_render.py:113`）：非 blank 且
   `ratio > OCR_MIXED_PAGE_IMAGE_RATIO` 的页，页锚后写占位行字面量 **【本页正文为图像】**
   ——A3 与 A8 从此在底稿文本上可分（v2.2 要求）
3. `corpus_materialize._page_kind`：页文本含该字面量 → `kind="mixed"`（新枚举值）；
   `agency_context_block` 文案（`corpus_materialize.py:84`）同步 text/image/blank/mixed
4. OCR route 页与 blank 回填链（`_augment_mixed_pdf_blocks`）**不动**——混合页走判定期
   vision（v2.2 §三.1 路由裁决），不走摄取期回填

**阈值校准（新常数禁令合规前置）**：一次性脚本跑ZJ 400 页 + case-2/3 语料的
ratio 分布，以已知混合页 p315/316/345-348/372-375 与普通文本页的分离点定值；
数据落 evidence.yaml，常数上 env `OCR_MIXED_PAGE_IMAGE_RATIO`（默认=校准值）。
**三条实施约束（R1-P2）**：
1. **mixed 判定必须先于 blank**：占位行本身很短，"短标题 + 占位符" 可能 <`MAX_BLANK_CHARS`(20)
   而被翻成 blank，正好抹掉本刀要立的信号。`_page_kind` 内先查占位标记再查 blank
2. **占位符不得成为可引用证据**：该字面量进底稿后 `existence_ratio` 对它恒命中 1.0
   ——模型引用"本页正文为图像"就能拿到 `confirmed`。回查闸须把它列入不可引清单，
   **专测**：引占位符的 quote 不得判 resolved
3. **字面量提常量**，写侧（draft_render）与读侧（corpus_materialize / 回查闸）共用同一符号，
   禁两处各写各的字符串

**AC**：合成混合页 PDF 夹具红→绿；上述三条各 ≥1 测试；校准数据在档；
`corpus_materialize.py`（298 行贴线）若越 300 随刀拆 `_page_kind` 族；回归不回退。

## K4 · criteria 抽取自动重试 + 抽取段心跳（proposals 两条 P1 合刀，同落点）

**现状（侦察实测）**：`_run_extraction`（`doc_pipeline.py:288`）已有契约失败 resume 修补环
（`EXTRACT_CONTRACT_MAX_RETRY=1`，`:59`），但结构校验 `criteria_usability_problem`
（`:141`）在环**外**（`:428-429` 抛 `CriteriaUnusableError`）——结构非法（如
`item_max_invalid`）直接整单失败，零重试；心跳只罩 OCR 段
（`prewarm_scheduler.run_prewarm_with_heartbeat`，60s 间隔 vs 300s stale 线），
抽取段（`:616-631`，在心跳结束后运行）零 touch——慢抽取 >~300s 被误判僵尸。

**方案四件**：
1. **结构校验入环，但两类失败各记各账**（R1-F2/P2 订正）：normalize + usability 校验挪进
   `_run_extraction` 每轮 attempt 后，不过则以 problem 文案作 last_error 喂 repair 重抽。
   **不动 `EXTRACT_CONTRACT_MAX_RETRY=1`**——该值旁有在码理由（`doc_pipeline.py:55-59`：
   "修补轮是常数级短指令，一轮还不听话多半这次就是不听话，再加轮次只会把 criteria 等待期拖长"），
   针对的是**契约失败**（模型不吐 JSON）。K4 治的是**结构失败**（同文件不同骰子，11:38 坏/11:41 好），
   两者失败机理不同、重试价值不同，故新增独立预算 `EXTRACT_STRUCTURE_MAX_RETRY=1`
   （结构失败额外重掷 1 次），不与契约计数共享。
   **超时账（R1-F2 硬约束）**：`EXTRACT_TIMEOUT_SEC=1200` 包住**整个重试环**
   （`doc_pipeline.py:60-63`，注释载"线上实测一次抽取跑到 16 分钟仍未结束"）。加轮次不加墙钟
   ⇒ 慢文档上第二轮会被 `wait_for` 掐死，用户看到超时文案而非本刀要给的结构文案，
   AC「双重试仍败给结构文案」落笔即不可达。**故本刀开工前置**：先测单 attempt 时长基线
   （含修补轮，真语料 ≥2 次，命令与实测值落 evidence.yaml），据数据二选一——
   ①超时随重试预算联动上调；②按 attempt 分预算（每轮独立 wait_for）。**基线未测不得改重试上限。**
2. **失败文案分家**：按 problem 码给准确文案（结构非法 ≠ 扫描件无文字层），
   落 `_criteria_failure_message`（`:349`）与 docs-status 的 `criteria_error` 出口
3. **数字归一收严**：全数字字符串满分 `"10"`→10 归一；含糊形态（`"10-15分"`）不猜，
   留给重试环
4. **抽取段心跳**：复用 `_heartbeat_loop` 模式包住抽取段，新 store 函数
   `touch_project_doc_criteria`（UPDATE updated_at WHERE criteria_status='running'，
   仿 `touch_project_doc_ocr`，`tender_doc_store.py:323`）

**①与④必须同刀**：重试×3 使抽取耗时上限×3，300s 误判窗被放大，无心跳则重试刀自伤。
**AC**：四形态单测（非法满分喂回后通过 / 双重试仍败给结构文案 / `"10-15分"` 不猜 /
mock 慢抽取 updated_at 持续刷新）；回归不回退。

## K5 · tool_call_count 进任务记录（proposals P1，Step 5 出数前置）

**事实链已闭合（侦察实测），纯装配**：
采集点 `SessionLogger` ToolUseBlock 分支（`session_logging.py:113-122`，所有消息单点过此）
加计数器字段 → `json_bridge` 读走塞 `AgentRunMeta`（slots，**须声明字段**，先例
`retry_count`，`agent_bridge.py:448`；唯一构造点 `json_bridge.py:312-324`）→ 写入点
`worker.py:218-235` completed 分支 upsert（同处已消费 `result_file`/`session_id`）→
表 `TaskRecord`（`task_store.py:29-46`）加列 + 幂等 ALTER（先例 `group_id`，`:120-123`，
`_FIELDS` 自动派生免改 upsert）。读侧**已就绪**：`regression.py:54` `TOOL_CALL_FIELD`，
缺席 n/a 绝不回退 0（`:801-820`）。
**口径与聚合点（R1-P2 补）**：计数含重试轮，但**每次 attempt 各建一个 `SessionLogger`**
（`json_bridge` 每轮新建），故须在 `runner.py` 的重试环内**逐轮累加**再交给 meta，
不能只取末轮——否则重试单的计数偏小。评标 CLI 路径若 `wall_s` 恒 0，不引它作参照口径。
**AC**：mock 会话 N 个 ToolUseBlock → 任务记录 `tool_call_count=N`；
**含重试的两轮会话累加正确**（专测）；回归报告该列出数字非 n/a。

## K6 · attempted[] 契约 + 回查闸两刀（v2.2 #5，≈40 行）

**schema 事实（侦察实测）**：scoring.items 层 `additionalProperties:true`（schema:62）且
`pending_reason` 正声明于此层——`attempted` 同层声明是**加声明+闸校验**，不破既有结论
兼容；顶层 `additionalProperties:false` 勿动；`eligibility_checks` 在 schema 完全未声明，
本刀**不挂**（Step 5 度量只看 scoring pending，反过度工程）。

**刀① attempted 硬闸**：schema scoring.items 声明
`attempted: [{tool, target, result}]`（required: tool, result）；`output.py`
`validate_tender_result` 调用序（`:689-693`）加 `_verify_pending_attempted`：
`score=null` 且 `pending_reason ∈ {evidence_unresolved}` 且 attempted 缺/空 →
`JSONContractError` 打回（走既有 contract_repair resume 修补环，打回文案即三段义务教程，
**提示词零增字**——预算余 34B，v2.2 原则"行为是被契约验收出来的"）。
**豁免**：`cross_bid`/`live_event`（结构性正当待人工，`regression.py:61` 同口径）、
`manual_mode`/`external_data`/`non_responsive`（非标书内可检项）——对这些强制 attempted
只会逼模型编造，违背 A9 无证据不编原则。豁免判据 = "证据可能在标书里而没找到"才须举证。

**改口后门与三道防线（R1-F3）**：豁免按**模型自报**的 `pending_reason` 触发，而
`_verify_pending_reason`（`output.py:422`）只验枚举成员不验语义——模型找不到证据时
改报 `external_data`/`non_responsive` 即可免举证，且 K8 覆盖率分母＝豁免补集，
**改口后覆盖率反而显 100%**，Step 5 读数走偏。故本刀含三道防线：
1. **`manual_mode` 确定性交叉核验**：与已注入的 criteria 该项 `score_mode` 比对
   （criteria 在场、零成本），自报 manual_mode 而该项 score_mode ≠ manual → 打回
2. **K8 报告面输出 per-reason 分布**（`count_pending` 已有分列 dict，只差渲染），
   让改口漂移在数字上可见——**这是主防线**：不试图穷举语义，让分布异常自证
3. **case-4 expected 钉死已知项的 reason**（如价格分＝cross_bid），改口即回归闸红

**刀② 否定断言反证**（治"p349 空白"断言错，回查闸盲区：只验引文存在不验断言为真）：
`resolve_audit_evidence` scoring 循环（`evidence.py:379-427`）内，basis 含否定标记
（"空白/未提供/未定位/未见/未找到"）且带页锚的断言 → 查 corpus index 该页 chars，
超阈则 `validation_warnings` 加 `{"code":"claim_page_not_blank", item, page, chars}`
（软告警不打回，Step 5 数据后再议硬化）。否定词表属**验证面**非检索面（同 v2.1 五节
"度量侧不受词表禁令约束"法理）；chars 阈用校准数据定（被否定页实测 3,000 字级 vs
空白页 <20，分离度大）。
**AC**：打回/豁免/反证三形态单测 + schema 契约测试；既有结论样本重放零误伤。

## K7 · D2 检索四项机械修复（授权范围照旧）

按 plan-v2 Step 4 授权：**仅**额度按分值加权 / chunks_per_item / 投标层硬过滤 /
查询串留痕四项；**禁**查询串措辞、词表、权重系数开放调参。先跑 D2 本地重建索引实验
（现役 criteria + 本地直读底稿 → evidence_chunks → retrieve_evidence 逐项打印
查询串/命中块/记账），实验记账落 evidence.yaml 后按数据落四修。
**行数纪律（R1-F1 理由重述）**：`evidence_retrieval.py` 实测 **275 行**（非初稿转述的 332），
距 300 硬线尚有 **25 行余量**——原"已越线故禁止落此文件"的前提为假。改为：四修增量优先落
本文件，**累计逼近 300 时按变更轴拆**（拆法沿用 design.md 实施修订②的先例：续接边界已拆
`evidence_continuation.py`，实测 125 行）。查询串留痕属可观测面，若单独成块优先落新文件。
**AC**：四修各留痕可见（查询串/命中差异入日志与 evidence）；回归闸期望值与命中判定禁改。

## K8 · 度量侧：attempted 覆盖率列 + 归因四列（白名单 eval/regression.py + 报告模板）

**挂点（侦察实测）**：计算 `count_pending`（`regression.py:742-761`，唯一遍历
score=null 行处）+ `PendingOutcome`（`:731-739`）加覆盖率字段；汇入 `RunMetrics`
（`:843-854`）/ `evaluate_result`（`:857-872`）；输出 `_v21_metric_rows`（`:941-967`）
加一行 + `_run_details`（`:1033-1062`）补明细。覆盖率口径 = 须举证类 pending
（K6 豁免口径的补集）中 attempted 非空占比。**同批出 per-reason 分布**（K6 第 2 道防线，
`count_pending` 已有分列 dict，只差渲染）。
**分母排除项（R1-P2 表态）**：回查闸服务端降级产生的 `score=null + evidence_unresolved`
（`evidence.py:251` `_downgrade_scoring_item`）**不进分母**——那是代码判的、模型无从举证，
计入会把覆盖率永久压低并掩盖模型侧真实变化。`evidence_resolution.downgraded_items` 已有计数可据以剔除。
**归因四列**：expected `attribution` 枚举 text|pixel（`:334`）扩 `mixed`/`ingest`
（v2.2 §二 列C/列D）；归因表（`:1002-1030`）按四列记账禁跨列。扩枚举是登记面，
命中判定逻辑禁改红线不触。
**AC**：新列出数（K6 落地前显 n/a，沿用 `_optional_row` 缺席语义）；`--dry-run` 兼容
新旧 expected；1,135 行文件增量 ≤40 行，超则按既定下刀线拆 `eval/report.py`。

## K9 · facts_precheck 三扩（v2.2 #4，≈120 行）

**现状**：`facts_precheck.py`（262 行）仅一类核对（项目名/编号，`NAME_LABELS`/`CODE_LABELS`
`:31-32`），注入点 `runner.py:247`（OCR 底稿块后、criteria 前）。
**三扩（v2.2 §三.1，原则：模型不为确定性算术承担概率风险）**：
1. **金额三处勾稽**：regex 扫"合计/小写/大写"三处互验；大写在图页抽不到 → 注入块登记
   一条「vision 待问」条目（这即 D1"摄取期回填 vs 判定期问答"的路由判据，免单独实验）
2. **制造商覆盖核对**：中小企业声明函制造商集合 ⊇ 报价明细品牌集合，差集直接注入
   （本案最高价值发现的确定性化）
3. **隐藏无效标触发点登记**：承诺函/常规参数负偏离/付款方式三处触发词扫描并注入所在页，
   与 S1 触发词兜底互为校验
**词表边界声明**：禁令约束链路侧**检索**词表；本刀是代码侧确定性核对面，v2.2 白名单授权。
触发词/标签一次性定义并被测试锁死，不开放调参。
**行数纪律**：262+120=382 越 300 硬线 → 三扩落新文件 `server/tender/facts_checks.py`，
`facts_precheck.py` 保持装配职责（SRP，设计明示免 generator 踩线）。
**AC**：每扩 ≥2 单测（命中/不命中），跨投标人隔离沿用既有五专测模式；注入块头格式
与现有 `facts_precheck_block` 一致；回归不回退。

## K10 · 示教 references（v2.2 #6，文本）

新建 `.claude/skills/tender-eval/references/exemplar-escalation.md`（≤60 行，两段真实
调用序列：声明函起疑→grep 品牌列→差集记 ambiguity；证书页标题→渲染→三问→判分），
**全角色代号**（映射同 K0/K1）。skills 侧 SDK 按需加载，**不占 40K 常驻预算**
（实测该预算属 `.claude/commands/tender-evaluate.md`）；SKILL.md（23 行）加一行指引。
归属 Step 5 agency 臂手段包，实验报告注明其在场。
**AC**：真名守卫扫过；行数 ≤60；SKILL.md 指引可达。

## K11 · vision 支线（卡 qwen VL 端点，就绪即插）

三点冒烟（大写金额 p5 / CS 证书 p316 / 检测报告 p364+p369 两跳）→ 三跳协议
**写进 `.claude/skills/vision-page/SKILL.md`（22 行）而非评标命令**（R1-P2 订正：
评标命令预算只剩 34 B，加不下；skill 由 SDK 按需加载，不占常驻预算）；
按跳三问用 `vision.py` 现行一页一问即可（`SKILL.md:49`）；`--pages N-M` 实装
**缓议**——反过度工程：多次单页调用已可用，仅当 Step 5 数据显示调用数超预算再做。
exit 5（VLM 未配置）语义与回落 ocr-page 纪律照旧。

---

## 实施顺序与任务表（Sisyphus）

| # | 刀 | 区色/执行者 | 依赖 |
|---|---|---|---|
| T1 | K0 历史抹净 | 程序刀，主 agent（git 操作） | 无（**最先**：越早抹越少重写） |
| T2 | K1 case-4 | 红区 generator+worktree（纯文本） | K0 映射表 |
| T3 | K2 office native | 红区 generator+worktree | T2（基线先行）；步骤一实验先行 |
| T4 | K3 混合页 | 同上（可与 T3 同 worktree 串行，单写者） | T2；校准先行 |
| T5 | K4 重试+心跳 | 红区 generator+worktree | — |
| T6 | K5 tool_call 计数 | 同上 | — |
| T7 | K6 attempted 契约 | 同上 | — |
| T8 | K8 度量列 | 同上 | T7（读 attempted 字段） |
| T9 | K9 precheck 三扩 | 同上 | — |
| T10 | K7 D2 实验+四修 | 实验主 agent / 修复 generator | 实验数据先行 |
| T11 | K10 示教 | 绿区可主 agent（单文件文本） | K0 映射表 |
| T8b | K1 归因回补：case-4 的 attribution 补 mixed/ingest 两值 | 绿区，主 agent | T8（枚举扩完） |
| T13 | **对照臂基线 post-Phase-A 重测**（n=3，与 K5 同批） | 实验，主 agent | T6（否则重测的基线仍缺 tool_call 列） |
| T12 | K11 vision 支线 | 卡端点 | qwen VL 部署 |

**T13 的由来**（2026-08-20 生产检验，`prod-check-2026-08-20-conclusion-duty.md` 四节①）：
附录B 的墙钟基线 299 s 测于 **Phase A 之前**；实测同案 post-Phase-A 单发为 486 s
（等待 111 + 实跑 375）。沿用旧基线会让 agency 臂替 Phase A 背账，v2.1「墙钟 ≤120%」验收线失效。

纪律：一次一刀、落地即回归+commit；白名单外记 proposals；回归闸期望值与命中判定逻辑
禁改；每刀 tdd-evidence 八字段（复现实验类用 backfill 记法者须给真实缺口证据）。

## 全局验收标准

- [ ] 回归 `uv run pytest -q` ≥ 1,965P 且 17F 逐名不变（基线见上表；各刀新增测试数随
      tdd-evidence 登记，单写者下界口径）
- [ ] `wc -c .claude/commands/tender-evaluate.md` ≤ 39,966（**提示词零增字**，
      K6 义务全靠契约打回文案承载）
- [ ] 真名守卫 + `git grep` 复扫：tracked 文件零真名/证号（K0 后全历史亦零）
- [ ] 无新增越 300 行文件（K9 拆分、K3/K8 贴线文件随刀拆）
- [ ] 新常数（混合页 ratio 阈、反证 chars 阈、重试上限）各附校准/诊断数据于 evidence.yaml

## 明确不做

Step 5/6 实验本体；vision 端点部署与 `--pages` 实装；`eligibility_checks` 层 attempted；
legacy/inline 路径空 corpus 承诺（proposals 留档）；行数债偿还（除各刀拆分义务）；
`OCR_PREWARM_STALE_SEC` 口径改动（K4 只加心跳不改判定线）。
