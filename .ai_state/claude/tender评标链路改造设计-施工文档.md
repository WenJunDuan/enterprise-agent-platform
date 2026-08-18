# Tender 评标链路改造设计 — 以实跑参照链路为蓝本

> 用途：作为 Claude Code 的**唯一施工依据**。每个 Phase 独立开 sprint（沿用 `.ai_state/sprints/` 惯例：design → plan → ship），**过回归闸才准进下一 Phase**。本文件之外的"顺手改进"一律禁止。
> 参照系：2026-08-17 真实评标实跑（ZJ直播间标，招标 .doc + 投标 400 页混合 PDF，45MB，xref 损坏），35 次工具调用，渲染 20/400 页，产出 P0×3 + P1×4，全部结论带页码锚定。

---

## 〇、五条设计公理（参照链路的本质，所有 Phase 的判据）

| # | 公理 | 现行架构违反点 |
|---|---|---|
| A | **取证是运行时决策**："看到A才知道要查B"。跨文件缺陷（声明函↔报价品牌矛盾、检测依据↔参数错配）只能由这条因果链发现 | KD3b 把检索钉死在会话前；`DRAFT_INJECTED_TOOLS=["Bash"]` 砍掉 agency |
| B | **上下文只装当前步所需**。参照链路峰值上下文 ≈ 数千 token/步 | 单发注入逼近 200K，`bound_draft` 截断=主动丢证据 |
| C | **像素证据在判定时刻看图**。章的归属、大写金额、证书等级、CMA标识——转写即失真 | 判分模型全程只见 OCR 文字，`multi-ocr/seal` 与主链路断开 |
| D | **算术不过模型**。分项求和、日期窗口、限价比较由代码算 | 报价勾稽、有效期判断仍在模型侧 |
| E | **输出小粒度**。坏一处只重试一处 | 单个巨型 JSON，爆炸半径=整单，催生修补轮/回查闸/重试环 |

## 〇.5、保留清单（这些是对的，禁止动）

- criteria 上传时预抽 + 注入复用（`criteria_context.py`、`compare_input.py`）
- 页锚坐标系（`【第N页】`/`【转换稿第M页】`）与 `corpus.py` 解析
- quote 回查闸 `evidence.py`（新路径同样接它）
- A1-A9 判分仲裁决策表的**内容**（形态要改：从 20K 字命令里拆出为可引用参考文件）
- `output.py` 汇总、stores 层、worker 调度壳
- 旧单发路径 `runner.py`：**灰度共存，不删不改**，`TENDER_EVAL_MODE` 切换

---

## 一、目标架构

```
上传期（已有，小改）
  doc_pipeline ──→ ①修复(qpdf) ②逐页清点(manifest) ③底稿落盘为可grep语料 ④criteria预抽(不变)

评标期（新路径 TENDER_EVAL_MODE=itemized）
  Phase-A 确定性预检（python，不调模型）
      报价勾稽 / 大小写待核标记 / 限价比较 / 日期窗口 → facts.json
  Phase-B 按评分项并行判分（N 个小调用，4 路并发）
      每调用 = 该项规则 + 决策表引用 + 初始检索片段 + 有界工具(Grep/Read/ocr-page/vision-page)
      输出 = 单项小 JSON（~1-2K token）
  Phase-C 交叉一致性核对（1 个独立调用）
      固定 10 条跨文件核对清单 + 全语料 grep 权限 → 矛盾清单 JSON
  Phase-D 资格审查 + 废标 gate（1 个调用，最先跑或与 B 并行）
  Phase-E 确定性汇总（python：output.py + evidence.py 回查闸 + verdict 合成）
```

**Token 账（对照现行）**：单项调用 scaffold（项规则+决策表引用+schema切片）≈3-5K + 初始证据 5-15K ≈ **10-20K/调用**；现行单发 150-200K。14 项 4 路并发，墙钟 ≈ 单项时长 × 4 批 ≪ 现行单发+重试。JSON 失败重试成本 = 1 项而非整单。

---

## 二、Phase 0 — 回归闸先行（先造尺子，再动刀）⚠ 不做完这步不许改任何链路代码

**目的**：终结瞎改。之后每一刀的好坏由数字裁决。

**做什么**
1. 金标准案例库 `eval/golden/`：
   - case-1 = ZJ标（招标 doc + 投标 400 页 PDF），`expected.yaml` 记录：
     - 必须召回的缺陷：中小企业声明函数据雷同+制造商覆盖矛盾（P0）、检测报告依据标准与参数错配（P0）、投标函/有效期缺失待核验（P0）、常规参数 0 正偏离（P1）
     - 客观分基线：企业实力 6/6、业绩 9/9、负责人 3/3、报价合计 1,316,033.66 勾稽通过
   - 后续每遇一个真实标就沉淀一个 case（对齐你回补工作流）
2. 评测脚本 `scripts/eval_tender_regression.py`（沿用 `measure_tender_recall.py` 风格），输出四指标：
   - **墙钟时间**（含重试）
   - **manual_review 项数**（越低越好，前提是不误判）
   - **跨文件缺陷召回率**（expected 缺陷命中数 / 总数）
   - **客观分准确率**（与基线逐项比对）
3. 现行单发路径先跑一遍，**记下基线数字写进本文件附录**——这是所有 Phase 的对照组。

**验收**：脚本可一键跑双路径出四指标对比表。
**Claude Code 纪律**：本 Phase 只准新增 `eval/` 与 `scripts/eval_tender_regression.py`，不准触碰 `server/tender/`。

---

## 三、Phase 1 — 语料落盘 + 页清单（纯增量，零行为变更）

**参照链路对应**：我的"逐页字符数索引"——一次廉价扫描给出全文档地图，图片页清单即证据页清单。

**做什么**
1. `doc_pipeline` 产出底稿时同步落盘 case 工作区：
   ```
   data/tenders/<case>/corpus/
     ├── manifest.json          # 每文件每页: {page, chars, kind: text|image|blank, source_artifact}
     ├── <招标文件名>.txt        # 带页锚的全文（现有底稿原样落盘）
     └── <投标文件名>.txt
   ```
2. `manifest.json` 的 `kind` 判定：复用 `pipeline.py` 现有 blank/native 判定（`MAX_BLANK_CHARS`），chars≈0 且有渲染内容 → `image`。
3. 顺手修一个已知坑：doc_pipeline 入口对 PDF 先 `qpdf --check`，损坏则修复后再进管线（参照链路第一发现：损坏文件 pdfinfo 报 5 页实为 400 页）。

**验收**：ZJ case 跑完上传，corpus 目录存在；manifest 标出 p319-328/330-344/364-371/376-383/385-399 等为 image；回归闸四指标与基线持平（本 Phase 不该动指标）。
**改动范围白名单**：`server/tender/doc_pipeline.py`、`server/ocr/pipeline.py`（manifest 输出）、新增 `server/tender/corpus_materialize.py`。

---

## 四、Phase 2 — 按项并行判分路径（核心刀口，灰度共存）

**参照链路对应**：我 35 次调用里每次只处理一个审查焦点；对应到你这就是"一个评分项一个小会话"。

**做什么**
1. 新增 `server/tender/itemized_runner.py`：
   - 输入：预抽 criteria + Phase-A facts.json + 每项的初始检索片段（**复用** `evidence_retrieval.retrieve_evidence`，从"唯一证据来源"降级为"初始线索"）
   - 按 `criteria.items[]` 分组（同 category 可合批，单批注入 ≤30K token），`asyncio.Semaphore(4)` 并发
   - 每批调用新命令 `/tender-eval-item`，输出对齐**新增小契约** `.claude/contracts/tender/item-result.schema.json`（单项 `{item, max, score, status, basis, hits, evidence}`）
   - 单项 JSON 失败只重试该项（沿用 contract_repair 机制，作用域缩小）
2. 命令拆分（`.claude/commands/`）：
   - `tender-eval-item.md`：≤3K 字。只含：本项判分流程 + 决策表**引用**（"仲裁口径见注入的 arbitration 块"）+ 输出契约
   - 决策表 A1-A9 + score_mode 细则从现 20K 字命令**原文迁出**到 `.claude/skills/tender-eval/references/arbitration.md`，由服务端按需注入（每项只注入其 score_mode 对应细则 + 决策表，≈2K 字）
   - `tender-evaluate.md` 旧命令不动（旧路径用）
3. Phase-A 确定性预检 `server/tender/facts_precheck.py`：分项报价逐行复算与总价勾稽、报价 vs 限价、业绩日期窗口、证书有效期 vs 投标截止日（criteria 里能结构化的先算），结果作 `=== 已验事实（代码计算，直接采信）===` 块注入相关项。
4. Phase-E 汇总：`output.py` 收集各项小 JSON 拼装成现有 audit-result 契约（**下游 store/前端零改动**），quote 回查闸照跑。
5. `TENDER_EVAL_MODE=single|itemized` 环境开关，默认 single。

**验收**：itemized 路径四指标 vs 基线——墙钟 ≤50%、客观分准确率 ≥基线、manual_review ≤基线；契约重试次数（`meta.retry_count` 汇总）下降。
**改动范围白名单**：新增 `itemized_runner.py`/`facts_precheck.py`/`tender-eval-item.md`/`item-result.schema.json`/`references/arbitration.md`；修改 `worker.py`（模式分派）、`output.py`（拼装入口）。**禁触**：`runner.py`、预算三件套（`injection_budget/draft_budget/context_budget`——新路径不需要它们，但旧路径还在用）。

---

## 五、Phase 3 — 有界 agency（恢复"看到A去查B"）

**参照链路对应**：我的 grep→切片→再取证循环。这是对 KD3b 的**定向翻案**：08-14 事故根因是盲截+指令自相矛盾+弱模型，不是 agency 本身；Phase 2 已把单调用上下文缩到 10-20K，复发条件已拆除。

**做什么**
1. 单项调用工具面从锁死改为：`Bash`（既有 ocr-page hook 约束）+ `Grep` + `Read`，`add_dirs`/cwd 钉死到 `data/tenders/<case>/corpus/`（settings 层面 deny 其余路径）
2. 命令指令：初始片段头保留"未注入≠未提供"，追加一句"**可对 corpus 目录 grep 定位后按行区间 Read 补证；单次 Read ≤200 行；引用页码取所读文本中的页锚**"
3. 护栏：`max_turns` 单项调用降到 12（单项取证用不了 30 轮）；PreToolUse hook 校验 Read 路径在 corpus 内

**验收**：跨文件缺陷召回率显著抬升（ZJ case：声明函矛盾、检测依据错配至少命中其一，目标全中）；墙钟不劣于 Phase 2 的 120%；无 error_max_turns。
**风险与回滚**：若弱模型驱不动 grep（乱查/空转），`TENDER_ITEM_TOOLS=locked` 一键回 Phase 2 形态——这正是模型路由决策（见第八节）的实证数据。

---

## 六、Phase 4 — 交叉一致性步 + 定向 vision

**做什么**
1. 新命令 `tender-cross-check.md`（独立调用，Phase-B 后运行）：固定核对清单（现 S2 里那段跨文件核对**原文迁出**），全 corpus grep 权限，输出 `cross_findings[]` 小 JSON，汇总期并入 ambiguities/risk 与相关项 basis。单发路径里这段与 14 个评分项抢注意力；独立成步后它是唯一任务。
2. `vision-page` 工具（`.claude/skills/vision-page/vision.py`，仿 ocr-page 形态）：输入 `(文件, 页, 问题)` → `page_render_worker` 渲染 → `vlm_client` 带图提问 → 返回答案文本。**判定时刻的定向问答，不是转写**。
3. 命令层接线：涉及章的归属/大写金额/证书等级字样/检测报告标识的判定，指示模型优先 `vision-page` 而非采信 OCR 文字；A2（读不清）的首选升级路径从 ocr-page 重转写改为 vision-page 定向问。

**验收**：ZJ case 图片证据类判定（大写金额一致性、CS2 有效期、检测报告无 CMA 标识）由 vision 通道给出且正确；cross-check 步召回 expected 全部跨文件缺陷。

---

## 七、Phase 5 — 收尾

itemized 灰度转默认（`TENDER_EVAL_MODE` 默认值翻转，single 保留一个版本周期）；预算三件套在 itemized 路径确认零调用后加弃用注释（不删，旧路径仍依赖）；修补轮/回查闸统计量对比写进 `.ai_state/compound/` 收编记录。

---

## 八、需要人拍板的两个决策（Claude Code 无权自定）

| # | 决策 | 影响 |
|---|---|---|
| 1 | **判分步模型路由**：内网网关能否给 Phase-B/C/D 挂更强模型（哪怕只这三步）？Flash 继续兜底还是仅做 OCR 转写？ | 决定 Phase 3 的 agency 上限与 Phase 4 vision 问答质量；这是全案第一杠杆。Phase 3 验收数据出来后用数字复议 |
| 2 | 单项小契约的粒度：严格一项一调用（最细、最并行）还是按 category 合批（省调用、单批稍大）？ | 建议先合批（≤30K/批），指标不达再拆细 |

## 九、Claude Code 会话纪律（防瞎改，逐条写进每个 sprint 的 plan.md 头部）

1. 一次会话只做一个 Phase；Phase 内先写 design.md 过人审再动代码
2. diff 只准落在该 Phase 的"改动范围白名单"内；白名单外的问题记 `proposals.md`，不顺手改
3. 每 Phase 收尾必跑 `eval_tender_regression.py` 双路径对比，四指标进 ship.md；任一指标劣化即回滚重议
4. 禁止删除/重写旧路径与"保留清单"内组件；灰度开关是唯一切换手段
5. 提示词改动同样过回归闸——命令/skill 文案调整视同代码

---

## 附录A：参照链路实测数据（校准锚点）

| 量 | 值 |
|---|---|
| 工具调用总数 | ~35 |
| 渲染页数 | 20 / 400（5%） |
| 单步峰值上下文 | 数千 token（grep命中/页区间切片/单张图） |
| 发现 | P0×3（声明函数据雷同+覆盖矛盾、检测依据错配、投标函缺失待核验）+ P1×4 |
| 页码锚定 | 全部结论带页码；不可机读项→待人工核验清单（7项）而非猜测 |

## 附录B：现行基线（Phase 0 跑完回填）

| 指标 | single 路径 | itemized（各 Phase 后追记） |
|---|---|---|
| 墙钟 | [待回填] | |
| manual_review 数 | [待回填] | |
| 跨文件缺陷召回 | [待回填] | |
| 客观分准确率 | [待回填] | |
| 契约重试均值 | [待回填] | |
