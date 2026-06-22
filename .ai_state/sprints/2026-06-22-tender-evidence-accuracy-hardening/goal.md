# Goal · 评标证据可验证性 + 报价规模 + 准确度 durable 硬化（2026-06-22 起）

> 合并来源：
> ① **R2024-007 深度优化深潜**（`r2024007-deepdive.md`，本目录，cowork 跑全量 PDF + 提示词产出，已实测 grounded）。
> ② **上一 Sprint 遗留**（`2026-06-22-multimodel-tender-optimization/goal.md` §三 8 个遗留 + R7 deferred）。
> 用户指令（2026-06-22）：读深潜总结 + 结合未完成项 → 合并出一个新 Sprint，文档全部记录，新开会话执行。

---

## 一、对深潜总结的针对性评审（Athena 复核，2026-06-22 已 grounding）

深潜的方法论**正确且与本项目既有哲学一致**（"靠校验层兜底，不靠提示词"——见 `compound/2026-06-22-learning-jsonschema-too-brittle-for-llm-output.md`、`compound/2026-06-18-learning-absence-is-not-zero.md`）。四条结论我**逐条核实**：

| 深潜结论 | 复核 | 证据 |
|---|---|---|
| 点评不对基本被校验层治住（verdict 纠偏 / absence 硬降级 / score_mode 自洽） | ✅ 属实 | 本会话 output_contracts.py 已含 `_has_hard_disqualification` 强制 rejected、scored_zero 硬降级、score_mode 一致性校验 |
| **定位不准根因 = 缺 evidence-resolution 闸（无代码回查模型引用的「文件/页/原文」是否真在底稿）** | ✅ **已确认仍空** | `grep evidence_unresolved\|resolve_evidence server/` 零命中；这是最高价值的一刀 |
| OCR 不是瓶颈（8636 页全文本层 native 抽取 3.6s + content-sha256 cache） | ✅ 合理 | 真 OCR 仅盖章/证书 ~10-15 页；**校正了上轮"OCR 提速"的优先级——OCR 占比可忽略** |
| **报价规模炸弹：8417 页 BOQ 被 `MAX_FILE_BLOCK_CHARS=200000` 从头截 → 投标总价（合计 851,886 @p8414）丢** | ✅ **已确认** | `pipeline.py:24` 常量 + `:250 body=full_body[:MAX_FILE_BLOCK_CHARS]` 从头切；构造类标必踩 |

**我补充的 caveat（impl 时注意）**：
1. **evidence-resolution 的假阴性风险**：模型转述（非逐字抄）quote → 模糊匹配失败 → 误标 `evidence_unresolved`。缓解：激进规范化（去空白/标点/全半角）+ 最长公共子串阈值 + **只降级 `needs_review` 不直接 reject**（深潜已主张，对）。先在 R2024-007 上调阈值，宁漏报勿误杀。
2. **底稿→校验管道是硬前置**：`apply_schema_semantics`（`contract.py:124`）当前只看模型输出、看不到输入底稿。要做 resolution 闸，必须把本案底稿（`prewarm_and_text` 产物，tender_worker 已持有）透传进校验上下文——**这是 R1 要先打通的管道，不打通后面都做不了**。
3. **BOQ 抽取的鲁棒性**：靠"文件名 + 表头特征"识别大表是启发式，需多同义词兜底（投标报价/合计/总计/价款/总价）+ 识别不到时回落现有截断（不致更差）。Top-N 高价行用于异常价抽查。
4. **深潜代码行号是 2026-06-21 的**，本会话改过 output_contracts.py/tender.py → **行号仅作指引，impl 时重新 grep**。

**结论**：深潜的优先级表（evidence-resolution > BOQ > 出处带文件名 > confidence 消费 > 基建债）我**全盘采纳**作为本 Sprint 主线，并把上轮仍开的遗留（⑤⑥⑦⑧ + ② 验证 + R7 扣分调优）并入对应轮。

---

## 二、核心目标（本 Sprint 焦点：从"评分逻辑"推进到"证据可验证性"）

1. **证据可验证性（最高价值）**：模型引用的每条出处 `(文件名, 第N页, 原文 quote)` 必须能在本案底稿里**确定性回查**；查不到 → 抓出来、降级，而非静默通过。同治"定位不准"与"点评引文不实"。
2. **报价规模正确**：超大 BOQ（已标价工程量清单）不再从头截丢总价；按需抽结构（合计/总价/Top-N 行）注入紧凑摘要。
3. **置信度消费**：底稿已采集 confidence，低置信（盖章/扫描/手写）页 → 标注 + 该项 manual_review（接 G3），不当客观 0。
4. **扣分项准确度（R2024-007 解锁）**：用真实全量标（118p 招标 + 2 家×19 投标）dogfood，实测扣分命中/明细/出处页准确度并调优。
5. **收尾遗留**：招标人侧合规 MVP、effort 各端点透传、三层数据 e2e、round4 基建债。

---

## 三、上轮遗留 reconciliation（合并入本 Sprint）

| # | 遗留 | 状态（2026-06-22） | 归入本 Sprint |
|---|---|---|---|
| ① | qwen 思考流式不实时 | ✅ **已修**（上轮 R3：include_partial_messages + StreamEvent partial，实测 qwen 1253 回调） | — 闭环 |
| ② | criteria 项目级回填验证 | 🟡 代码已落（上轮 R1），端到端首写赢+后续家读已存**未验** | **R6 e2e** |
| ③ | compare 首次横比 refetchInterval | ✅ **已修**（上轮 R5：null 时继续轮询 3s） | — 闭环 |
| ④ | delete 磁盘目录清理 | ✅ **已修**（上轮 R5：remove_project_submission_dir 删整树） | — 闭环 |
| ⑤ | G5 S2 公式变量清单结构化 | 🟡 formula_spec 已做（上轮 R3），S2 侧 limit_value/bid_component 结构化抽取仍弱 | **R4** |
| ⑥ | 招标人侧合规 MVP（排他/可量化/废标清单/时限） | ❌ 未做（设计有，未 impl） | **R5** |
| ⑦ | OCR 置信度深化（低置信→manual） | ❌ 底稿采集了 confidence 但**无消费** | **R3** |
| ⑧ | effort 各端点透传验证 | 🟡 qwen 跑通但 effort 是否生效未确认；deepseek/glm 待验 | **R5** |
| R7-a | **扣分项准确度调优**（曾 blocked：需匹配投标） | ✅ **解锁**：R2024-007 全量已在 `knowledge/external/交易大脑/` | **R4** |
| R7-b | 扫描件/盖章 OCR 准确度 | 部分：R2024-007 全文本层，仅印章需多模态（样本有限） | **R3** |
| R7-c | knowledge/external 离线 OCR 优化 / 本地 PaddleOCR | 待启 | **R3 视情况** |
| R7-d | 慢评标子代理并行 | 待启（OCR 非瓶颈，主耗时在模型；优先级低） | backlog |
| 基建债 | round4 F2 目录越权 / F4 同步 SQLite 阻塞事件循环 / F5 超时不杀子进程 | ❌ 未做 | **R5** |

---

## 四、实测素材（grounded，2026-06-22 已核实路径）

**R2024-007「川姜花苑施工总承包」全量标**，位于 `knowledge/external/交易大脑/`：
- **招标文件**：`川姜花苑（R2024-007）项目施工总承包招标文件.pdf`（118p；**第三章 评标办法 @p27**，本标有明确章名 → 定位逻辑须覆盖"有章名/无章名"两态）。
- **投标人 A**：`江苏通州二建建设工程集团有限公司/`（19 文件）。
- **投标人 B**：`江苏通州四建集团有限公司/`（19 文件）。→ **两家真实投标，够做 evaluate + compare 横比**。
- **BOQ 炸弹**：每家 `1.05 已标价工程量清单.pdf` = **8417 页**（占 97%）；合计 851,886 在 **p8414**，现有截断从头切 ~210 页 → 总价丢。
- **三类不可判定齐全**（验 manual_review 不判 0）：项目负责人**现场答辩 @p31**（live_event）、**评标基准价 @p9**（cross_bid）、**资质动态监管 @p28**（external_data）。
- **全文本层**：native 可直读（pymupdf），仅印章/证书是文本层上的图。

---

## 五、轮次计划（每轮：`round-N-{slug}/design.md` + 3 review subagent + codex；适用轮含 3 模型自测）

| 轮 | 主题 | 范围要点 | 治 | 自测重点 |
|---|---|---|---|---|
| **R1** | **底稿→校验管道 + evidence-resolution 闸（最高价值）** | ①打通 `apply_schema_semantics`/contract 校验接收**本案底稿**（tender_worker 已持有 ocr_text/doc-layer，透传进校验上下文）。②实现 resolution 闸：解析每条 `evidence_chain[i]`/`scoring[].basis` 出处 `(文件,页,quote)`→按底稿 per-file `### 文件:` + `【第N页】` 锚点切片→规范化模糊匹配 quote→匹配不上打 `evidence_unresolved` + 降该项 `needs_review`/explanation 标注。③提示词：evidence 出处统一「文件名+第N页+章节」对齐回查键。 | 定位不准 + 引文不实（深潜 #1/#3） | R2024-007 上：引文回查命中率、假阴性率（调阈值） |
| **R2** | **BOQ 感知抽取 + 截断策略** | ①BOQ 抽取器：识别"工程量清单/已标价清单"大表（文件名+表头特征）→确定性抽 分部分项合计/措施费/规费税金/**投标总价**/Top-N 高价行→注入紧凑摘要（几百字，非从头截 8M）。②通用截断"从头切"→"按需切"：大文件先抽结构/锚点索引，bulk 不进模型。③识别不到回落现有截断（不更差）。 | 报价失据 + 总价丢（深潜 #2/#4） | 两家 BOQ 总价正确抽出（851,886 量级）+ 报价分有据 |
| **R3** | **confidence 消费 + OCR 置信度（遗留⑦/R7-b）** | 底稿已采 confidence → 低置信（盖章/扫描/手写）页 → `file_clarity` 标注 + 该 scoring 项 confidence→`manual_review`（接 G3，"读不清≠没提供"）。印章/证书页按需多模态/PaddleOCR-VL（仅 ~10-15 页）。 | 盖章读不清误判 0（深潜 #4） | 印章页识别+低置信标注；OCR 仅必要页 |
| **R4** | **扣分项准确度调优（R7-a 解锁）+ G5 S2 公式变量（遗留⑤）** | 用 R2024-007 全量 dogfood：实测扣分项命中/明细/出处页准确度并调优；一致性风险（项目负责人 vs 业绩经理 data_conflict）。G5：限价类 formula 的 limit_value/bid_component/formula_variables 抽到 **S2 结构化**（现 S3 靠模型临场找）。 | 扣分准确 + 限价价格分单家可算 | 已知 case 扣分命中 + evidence loc + 两家价格分 |
| **R5** | **招标人侧合规 MVP（⑥）+ effort 透传（⑧）+ 基建债** | ①招标人侧：排他性条款/可量化性/废标清单/投标时限规则（先 `/init-rules` 补 tender_regulation + 时限到 `knowledge/tender`）。②effort 各端点（deepseek/qwen/glm）透传验证。③基建债：F2 submissions 目录越权、F4 同步 SQLite 阻塞事件循环（→ to_thread/异步）、F5 超时不杀子进程。 | 合规 MVP + 稳定性/隔离 | 合规规则命中 + effort 生效 + 越权/阻塞回归 |
| **R6** | **三层数据 e2e（②）+ 全回归 + 多模型** | criteria 首写赢+后续家读已存端到端；两家 compare 排名/推荐；3 模型 full e2e 回归；整体 UI/契约校验。 | 数据存储正确 + 总回归 | DeepSeek/qwen/glm full e2e + compare |

> 主题可随发现微调；长任务 agent 必断（见 memory 教训），短增量、每轮 commit + 回写「进度回写」节、codex 配合 review。

---

## 六、工作方式

- **多模型轮换**（`.env` 顶部模型块，`export MODEL_BASE_URL/MODEL_AUTH_TOKEN/MODEL_NAME` 非破坏切换，`config.py:97-100` os.environ 覆盖 .env）：
  - **DeepSeek** `deepseek-v4-pro` @api.deepseek.com/anthropic
  - **qwen3.7-max** @dashscope.aliyuncs.com/apps/anthropic
  - **openrouter** `z-ai/glm-5.2` @**`https://openrouter.ai/api`**（Anthropic skin，**非** OpenAI `/chat/completions` 路径；上轮 R3 实测抽取 81s 最快、SSE partial 支持）
  - ~~anyrouter~~ 已去（偶发 429）
- **每轮自测协议**：①`uv run pytest -q` + `ruff check .` + 前端 `bun run lint && bun run build`。②起 serve（background）→ curl 真实端点。③3 模型各跑核心自测，记耗时/verdict/scoring/扣分/evidence loc 差异到本轮 design「自测结果」。④看 `logs/app/<YYYYMMDD>/app.log`。⑤局限：真·视觉美观需用户 mac 跑 dev 确认。

---

## 七、关键操作备忘

- **dogfood 评标**：项目级 `POST /tender/projects/{id}/evaluate`（`mode:"directory"` + 绝对路径 + `directory_path`）。token = `.env` `TENANT_KEYS` JSON 的 `.default`（用 `rg -o 'TENANT_KEYS=\{[^}]*\}' .env | sed ... | jq -r '.default'`，**别用 cat**——本机 cat 被 alias 成未装的 bat）。
- **上传即 OCR**：`POST .../tender-doc`（招标）、`POST .../bids`（投标 + bidder_name form）、`GET .../docs-status`、`GET .../tender-doc`（criteria+tender_info）。multipart `-F "files=@路径"`。
- **R2024-007 素材**：`knowledge/external/交易大脑/`（招标 PDF + 二建/四建两家 dir）。BOQ = 各家 `1.05 已标价工程量清单.pdf`。
- **关键代码锚点**（2026-06-22 grep 实测）：截断常量 `server/ocr/pipeline.py:24`、截断点 `:250`；契约语义入口 `server/common/contract.py:124 apply_schema_semantics`（**当前不接收底稿，R1 要改**）；底稿锚点 `pipeline.py` per-file `### 文件:` + `【第N页】`；evidence-resolution **零实现**（待 R1 新建）。
- **mac mini 部署**：rsync（非 git）；`mac@100.107.151.115` ConnectTimeout30 + StrictHostKeyChecking=no；前端改动需 rebuild bundle。`./deploy/deploy.sh` 或 scp `server/` + compose build。
- **写盘注意**：别 `cd` 进子目录（断 write hook）；`cat`/heredoc 受 bat alias 影响 → 用 Write/Edit 或 `command cat`。

---

## 八、起点状态（接上一 Sprint）

- 上一 Sprint `2026-06-22-multimodel-tender-optimization` 至 R7 + 非阻塞热修：**main 与 origin 同步**，616 测试绿 + ruff + 前端 lint/build。
- 三模型评标均可靠跑通（qwen 300s/retries=0、deepseek 370s、glm 评 135s[D 降重试后]）；verdict 纠偏/evidence_chain 归一/criteria 归一全绿。
- 本 Sprint 从"评分逻辑正确"推进到"**证据可验证 + 报价规模正确 + 置信度消费**"。

---

## 九、完成状态（2026-06-22，R1-R6 全部完成）

main 累计 11 commits（`1a96db7`..`6d3edbe`），**681 测试绿 + ruff clean**。每轮 design + critic + codex 二审 + TDD impl + dogfood（适用轮）。

| 轮 | 交付 | 状态 |
|---|---|---|
| **R1** | evidence-resolution 闸 + 底稿→校验透传管道（`evidence_resolution.py` 新模块 + contract/json_bridge/command_adapter/tender_worker 透传） | ✅ qwen/deepseek dogfood 零误杀 |
| **R2** | BOQ 感知抽取 + 截断策略（`ocr/boq.py` 新模块） | ✅ 两模型捕获真投标总价 381,574,199.97（原埋噪音） |
| **perf** | 超大 PDF 跳过 find_tables | ✅ BOQ OCR 324s→28.9s（11×） |
| **R3** | confidence 消费（低置信→manual_review，接 G3）+ low_clarity_files emit | ✅ 单测；R2024-007 全 native 不触发不破 R1/R2 |
| **R4** | scoring 明细完整性（笼统扣/加分无明细→warning）；grounding 纠偏（本标无 deduction/限价，G5 兜底上轮已具备） | ✅ |
| **R5** | 基建债 F2/F4/F5 + effort **逐项核对均已完成**（SDK 杀子进程已处理）；补 worker 超时 graceful-fail 回归 | ✅ 招标人合规 MVP 移交 v2（CLAUDE.md 定 v1 不含程序合规 + 缺法规源） |
| **R6** | e2e/多模型/三层数据/compare 验证（既有测试覆盖）+ 跨轮 bug-hunt（reviewer 5 bug 全修 + codex 关注点自验） | ✅ |

**两个 grounding 纠偏**（深潜数据有误，已实读修正）：① 真投标总价 = 381,574,199.97@p2 扉页（非深潜的 851,886@p8414，那是单位工程税金合计）；② OCR 非"占比可忽略"，`find_tables` 对 8417 页耗 324s 才是 BOQ 真瓶颈。

**移交 backlog**：招标人侧合规 MVP（v2，需法规源 + 确认）；compare 多家真模型 dogfood；真扫描件 confidence 触发率验证；扣分命中/限价 formula 调优（需满分扣减制 + 限价标作素材）。
