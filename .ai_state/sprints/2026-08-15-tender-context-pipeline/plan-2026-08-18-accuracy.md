# 评标准确率修复计划 · 2026-08-18

> **效力提示（2026-08-18 晚）**：本档 **D1 / D2 / P2.5 之外的部分已被
> `.ai_state/claude/Tender链路纠偏令 v2 20260818.md` 取代**（执行序列以
> `plan-2026-08-18-v2-execution.md` 为准）。D1 的修复梯首位已改为 vision-page
> 判定时刻问答（纠偏令二）；D2 修复授权仅限四项机械缺陷。
>
> 经 Fable critic 独立核验（VERDICT: NEEDS_REVISION）后修订。本档取代我在会话中口头给出的
> 「四层方案」——那份的因果排序建立在两个被证伪的事实上，已作废。

## 一、被证伪的先前结论（必须先记下，防止再犯）

| 先前主张 | 实际 | 错因 |
|---|---|---|
| 「补 OCR 的闸从不触发（空白页 10/9/8 < 阈值 10）」 | **闸会触发**：YD `_blank_page_count=59`、BL `107`，`_should_cloud_ocr_mixed_pdf=True` | 用 awk 统计存库底稿，awk `length()` 按**字节**计，中文膨胀 3 倍 → 严重漏计空白页 |
| 「检索 unresolved=0 却零判分 ⇒ 命中块是空的 ⇒ 瓶颈在摄取」 | 块**非空**，是**错位且过薄**。critic 离线复跑 `53f94fd0`：投标报价(82分)只注入 301 token 且内容是**招标层废标条款**；施工组织设计(6分)只注入 48 token（招标文件里的一行标题） | 把「命中」等同于「命中了证据」。该 bid 8,683 页仅 2 页 <20 字，摄取几乎无损 |
| 「摄取是主因，检索是次因」 | 二者是**并列**的独立瓶颈 | 同上 |

**保留成立的结论**：证书/业绩/人员页确为扫描图（YD p85–97 文本 2–21 字、含图占页 35–56%；
技术方案页 368–637 字、0 图像）；成品底稿里这些页仍是空的。**闸触发了而结果仍空 ⇒ 故障在闸之后**。

一个新证据支持「按页判定」：YD 59 个 <20 字页**全部含图像**（59/59），BL 107/107。
这两份文档里不存在「真空白页」。

## 二、验证基线（AC 引用此处，勿凭印象）

| 量 | 值 | 测量命令 |
|---|---|---|
| 测试总数 | **1,672** | `uv run pytest --collect-only -q --ignore=tests/test_tender_prewarm_oracle.py` |
| 脚手架提示词资产 | 38,213 字 | `uv run python scripts/measure_tender_scaffold.py` |
| `pipeline.py` 行数 | 868 | `wc -l server/ocr/pipeline.py` |
| `doc_pipeline.py` 行数 | 611 | `wc -l server/tender/doc_pipeline.py` |
| 部署 env | `TENDER_EFFECTIVE_CONTEXT_TOKENS=95000` / `TENDER_SCAFFOLD_RESERVE_TOKENS=50000` | `docker exec agent-backend printenv` |

> 全量回归须带 `--ignore=tests/test_tender_prewarm_oracle.py`（否则约 34 分钟耗在它上面），
> **不要**用 `TENDER_TIMEOUT_SEC` 覆盖加速（会制造 6 条假失败）。

---

## P0 · 止血（改动小、确定性高、当前正在造成线上故障）

### P0.1 修预算悬崖 —— 本次会话自己引入的回归

切 qwen 时设的 `95000/50000` 造成：

```
criteria= 5,000tok → evidence=16,250 (per_item 1,354)
criteria=15,000tok → evidence= 6,250 (per_item   520)
criteria=21,000tok → evidence=   250 (per_item    20)
criteria=22,342tok → InjectionBudgetExhausted 硬失败（critic 实测川姜花苑即此值）
```

`plan_injection` 的账目 `evidence = effective − scaffold − criteria − effective/4` 里，
**criteria 是变量而 scaffold/margin 是常量**，大 criteria 项目会被挤成负数。

**改法**：不是继续调常数（那是拟合）。加一条**结构性保护**——当
`evidence_tokens` 低于「每项至少 1 个完整 chunk」的下界（`query_count × MAX_CHUNK_CHARS` 的某个
可论证下限）时，不要静默产出一个无用额度，而是**产出显式的、用户可见的容量不足信号**
（与 `InjectionBudgetExhausted` 同族，但要能区分「窗口装不下」与「配置压过头」两种原因，
错误消息须带实际数字与 `CALIBRATION_DOC_PATH`）。

同时：部署 env 回到与模型窗口相符的值。若继续用 qwen(131,072)，须显式承认
「大 criteria 项目在本机模型下不可评」而不是让它静默出烂分。

**AC**
- 新增测试：大 criteria（≥22,000 tok）+ 95K/50K 配置 → 抛出带实际数字的显式异常，且异常消息
  同时含「实测 criteria token 数」「当前 effective/scaffold」「标定档路径」
- 新增测试：evidence 额度跌破下界 → 同样显式失败，不产出 per_item < 一个 chunk 的计划
- 测试总数 ≥ 1,672 + 本项新增数

### P0.2 `_VALID_EFFORTS` 与端点实际能力对齐

`server/common/agent_bridge.py:57` `_VALID_EFFORTS = {low, medium, high, xhigh, max}`。
Qwen3.8 的 chat template 自校验 `reasoning_effort`，只认 `{xhigh, medium, low}`，
收到 `high`/`max` 直接 400（`vllm/renderers/hf.py:800`）。

现状是靠 `.env` 里 `CLAUDE_REASONING_EFFORT=medium` 压住——**但任何 per-call 传
`high`/`max` 的路径仍会 400**，且换端点后又要重踩。

**改法**：effort 白名单来源改为**可按部署声明**（env 覆盖，默认维持现状），非白名单值
**剔除并留一条 WARNING**（现在是静默 pop，见 `agent_bridge.py:338-341`）。不硬编码任何具体模型名。

**AC**
- 测试：声明白名单为 `{xhigh,medium,low}` 时传 `high` → 被剔除 **且** 产出 WARNING 日志
- 测试：未声明时行为与现状逐字一致（零行为变更）

### P0.3 抽取路径补齐评标路径已有的两道保护

`server/tender/doc_pipeline.py:247-256` `_extraction_call_kwargs`：

- **无超时**：评标侧 `worker.py:161` 有 1200s，抽取侧没有 → 线上实测单次跑 16 分钟未结束
- **未锁工具面**：回落 `agent_bridge.py:292` 的 6 工具白名单
  （实测进程实参 `--tools Read,Glob,Grep,Write,Skill,Task --max-turns 50`）。
  底稿已由 `context` 注入，评标侧 2026-08-17 已为此锁成 `DRAFT_INJECTED_TOOLS=["Bash"]`
  （理由：模型无视「无需再 Read」的提示，每轮重新预填充底稿），抽取侧漏了

**改法**：抽取加超时（可配，默认与评标同量级）；底稿在场时锁工具面。
**复用评标侧既有常量与形态，不新建机制**。

**AC**
- 测试：抽取调用带上超时；超时触发 → `criteria_status=failed` 且 `criteria_error` 含可执行解锁动作
- 测试：`context` 非空时 `tools`/`allowed_tools` 被锁；`context` 为空时不锁（降级路径仍需自己读文件）
- 测试总数 ≥ 基线 + 新增

### P0.4 criteria 未就绪时拒绝评标

线上实测：评标可在 criteria 抽取仍 `running` 时启动（相差 24 秒），
结果是证据层跳过 → 整份注入 → 截断 → 强制转人工，**整单作废且用户白等**。

现有 `doc_layer.py:239` 有等待，但 cap 到点仍**放行降级**。

**改法**：等待 cap 到点后**服务端拒绝**（4xx，消息说明"评分标准仍在解析，请稍后再提交"），
不再放行一个注定作废的任务。`criteria_status=failed` 时同样拒绝并给出重传指引。

**AC**
- 测试：`criteria_status ∈ {pending, running}` 且等待超时 → 提交评标返回 4xx，**不建任务、不烧 token**
- 测试：`criteria_status=failed` → 4xx 且消息含重新上传指引
- 测试：`criteria_status=ready` → 行为与现状一致

### P0.5 `total_score` / `total_max` 落地

4/4 条线上结论该两字段恒 `null`（schema `extracted_data` 是 `additionalProperties:true`，未强制）。
前端拿不到总分。

**改法**：**服务端按 `scoring[]` 汇总**，不指望模型产出。必须同时给出
`pending_count` / `pending_max`（`score=null` 的项数与其满分合计），
否则「总分 12/100」会被误读成「得了 12 分」而非「88 分待定」。

**AC**
- 测试：混合 `scored` 与 `score=null` 的 scoring → `total_score` 只累加非 null，
  `pending_count`/`pending_max` 正确
- 测试：`score=null` 的项**不得**被当作 0 计入

---

## P1 · 诊断（不写产品代码，只产出结论；决定 P2/P3 的形态）

> critic 的核心意见：**先确诊为何本应触发的子集 OCR 未生效，再谈改判据**。
> 我同意。我原提的「图像覆盖 ≥15% + 文本 < 中位数 20%」是**双常数拟合**，且试算捕获集
> 与现行判据几乎相同（71 vs 68 页）——改它修不中真因。**该方案否决。**

### D1 · 摄取：子集 OCR 到底发生了什么

已知：闸触发（59/107 空白页）；成品底稿头是 `kind=pdf_text, route=native`，
**与「子集回填成功」一致**（`_augment_mixed_pdf_blocks` 保留 `**route`）——若回退整份云 OCR，
`kind` 会变成 `ocr`。故三条 `return None` 回退路径**大概率都没走**。

剩下的最可能解释在 `pipeline.py:314`：

```python
if markdown.strip():   # 空 OCR 文本不覆盖，保留原空白页跳过逻辑
    blocks[true_idx] = markdown
```

**云 OCR 对证书页返回空/近空 markdown → 静默跳过 → 页面保持空白，全程无任何日志。**

**要跑的实验**（在部署机容器内，有完整 OCR 栈；本地缺 paddleocr）：

1. 取 `投标-YD.pdf` 第 85–90 页（软件企业证书 / 体系认证 / 著作权 / 检测报告）
2. `extract_pdf_subset` → `recognize(purpose=证书类)`，打印每页 markdown 长度与前 200 字
3. 分三种结果定性：
   - **返回有内容** → 故障在我们代码（静默跳过 / 页数不匹配 / 缓存），修代码
   - **返回空** → 云 OCR 读不了盖章证书页，需换识别姿势（`run_seal` / 提高渲染 DPI / 换引擎），
     与判据无关
   - **抛异常** → 走了回退整份云 OCR，但 `kind` 应变 `ocr`，与观测矛盾，需再查

**无论哪种，`pipeline.py:314` 那条静默跳过都必须补可观测量**：
「本次回填 N 页，其中 M 页云 OCR 返回空」要进日志与 `ocr_warnings`。
这是 `compound/2026-08-18-learning-the-investment-was-dark-in-production.md` 那条教训的直接应用
——**交付一条路径就要同时交付「这条路径今天被走过几次、成功几次」的可观测量**。

### D2 · 检索：命中块的相关性实测

critic 已复现：`53f94fd0` 的 34 块里，投标报价(82分)拿到的是**招标层废标条款**、
施工组织设计(6分)拿到 48 token 的招标文件标题行、业绩项拿到的是「主要人员简历表」
而真正的「近年完成的类似项目情况表」被记账到「资格审查:安全生产许可证」名下。

**要产出的结论**：
- 逐项列出「查询串 → 命中块所属层(招标/投标) → 块首 100 字 → 是否为该项证据」
- 量化：命中块中**属于投标应答**的比例（现在投标层优先只是排序偏好，不是硬约束）
- 判定三个候选主因的权重：
  (a) BM25 命中规则文本而非应答文本（相关性错位）
  (b) `chunks_per_item` 恒 1 + `per_item` 对高分值项过小（额度错配）
  (c) 查询串形态（若 criteria 项名是合成复合标签则命中率必低——**此条在可达 DB 中未证实**，
      三份可查 criteria 的项名都是干净短名，须重新取样）

---

## P2/P3 · 摄取与检索修复（形态待 D1/D2，本档不预设实现）

**已可确定的方向性约束**（无论诊断结果如何都成立）：

- **摄取判据若要改，走「逐页相对判据」不走「新增双常数」**：
  「该页含图像对象 **且** 页文本 < 空白阈值」→ 该页送 OCR；去掉文档级 `MIN_COUNT` 绝对门槛。
  真空白页因不含图像对象天然排除（`classify.py:44-52` 已论证），正文嵌图/Logo 由文本量一侧排除。
  **不引入任何新常数**——这是 critic 给的替代方案，比我的原案好。
- **`_CACHE_VERSION` 必须随摄取逻辑变更同步 bump**，否则旧缓存继续供旧产物、「修好」不生效。
  应在改摄取的同一次提交里 bump，并加测试钉住这个联动。
- **检索额度应按分值加权**：82 分的项和 2 分的项现在拿同样的 `per_item`。
- **验收要看「命中块是不是投标应答」**，不能只看 `unresolved` 计数——这正是 F3 踩的坑。

## P4 · 拆调用 / 去模型化（最大工程量，需先解决三个前置）

critic 指出的三个必须先解决的问题：

1. **两个不变量会被按批检索破坏**：`evidence_retrieval.py:253` 续接停止点 = **全项命中块并集**；
   `:173-221` 跨项去重账本按调用顺序共享。
   → 必须设计成「**检索一次做完，只把判分分批**」；「按批各自检索」会缩小停止点集
   （续接串到邻项）并分裂去重账本（同块重复注入 / 假 `truncated`）。
2. **prefix cache 前提未验证**：实测 hit 10.1%。要靠它省 prefill，前缀须**逐字节相同**；
   evidence 块顺序随批变化即失效。**先做一次前缀稳定性实测**再决定是否押注这条收益。
3. **去模型化与契约冲突**：`policy_refs` 在 `audit-result.schema.json:151` 是 **required**。
   确定性代码产出的结论也必须带真实 `rule_id` 的 `policy_refs` 与 `evidence_chain`。
   现有先例 `build_manual_review_result` 写 `policy_refs:[]` 能过 schema 但违反
   「承重 policy_refs 只引通则层真实 rule_id」的纪律 —— 可解，但必须显式设计，不能顺手抄那个先例。

---

## 执行顺序与理由

```
P0（止血，可立即做，互不依赖）
 └─ P0.1 预算悬崖   ← 我今天引入的回归，最急
 └─ P0.2 effort 白名单
 └─ P0.3 抽取超时+锁工具
 └─ P0.4 criteria 未就绪拒绝评标
 └─ P0.5 total_score 落地
      ↓
P1（诊断，不改产品代码）
 └─ D1 摄取实验（部署机容器）
 └─ D2 检索相关性实测
      ↓
P2/P3（按 D1/D2 结论定形态）—— 摄取与检索是**并列**的，不是串行
      ↓
P4（拆调用 / 去模型化，需先解决三个前置）
```

**为什么 P0 先做**：五项全是小改动、确定性高、且 P0.1/P0.4 正在造成线上任务作废。
它们不依赖任何诊断结论。

**为什么摄取和检索并列**：F3 被证伪后，「摄取修好检索自然好」这条推断没有支撑。
`53f94fd0` 是摄取几乎无损（8,683 页仅 2 页空）而检索仍交付错位证据的反例。

---

## 前提修订（2026-08-18 用户定调）

**目标形态 = 不挑剔模型的 harness。** 模型与上下文窗口都会被切换，harness 不得依赖任一模型的
能力。因此：

- **不再把"用什么模型/什么算力"当作决策输入**。提示词与输出的瘦身是**无条件**工作，
  不取决于任何模型或硬件的答案。
- P4（拆调用）不再由"纯内网与否"决定优先级，改由**时间预算**这一能力维度驱动。

### 今日一次换模型踩到的 11 处模型假设（全部待收敛）

| # | 位置 | 写死的假设 |
|---|---|---|
| 1 | `agent_bridge.py:57` `_VALID_EFFORTS` | effort 值域 |
| 2 | `injection_budget.py:37` `=200_000` | CLI 实际可接受输入 |
| 3 | `injection_budget.py:50` `=90_000` | 窗口大到能吸收固定脚手架 |
| 4 | `_BYTES_PER_TOKEN=3` / `estimate_tokens=len()` | 分词器行为 |
| 5 | `runner.py:87` 重试=2 | 某模型的 JSON 失败率 |
| 6 | `structured: False` | 结构化输出不可用 |
| 7 | `runner.py:91` `effort=xhigh` | 模型专属调参 |
| 8 | 单次巨型调用 | 输出吞吐 |
| 9 | `CLAUDE_CODE_MAX_OUTPUT_TOKENS=32000` | 与窗口耦合 |
| 10 | thinking 块处理 | 输出即 JSON |
| 11 | CLI `unrecognized_model` | 认识模型名 |

**已存在的正确骨架，在其上生长而非重造**：`MODEL_PROFILES_JSON`（per-model
`{context_window, max_output_tokens}`，由 `_resolve_model_budget` 消费）、
`scripts/measure_tender_scaffold.py`（证明脚手架可测）、`server/tender/eval.py --model`
（环境无关的跨模型 A/B 跑道）。

---

## P0.6 · 削减输入脚手架与输出体量（无条件，模型无关）

### 实测构成

输出侧，三份真实结论（12/12/5 项）合计 120,862 字：

| 字段 | 字数 | 占比 |
|---|---|---|
| `extracted_data.criteria` | 61,828 | **60.4%** ← 模型把服务端注入的 criteria 原样抄回 |
| `extracted_data.eligibility_checks` | 18,288 | 17.9% |
| `extracted_data.scoring` | 9,226 | 9.0% |
| `evidence_chain` | 10,758 | 8.9% |
| `explanation` | 3,480 | 2.9% |

> 修正：先前口头判断「`explanation` 千字总结冗余可砍」有误——实测仅 2.9%，砍它无意义。
> 大头是 criteria 回显。**测了才知道。**

输入侧脚手架 38,213 字：`tender-evaluate.md` 20,396 / `criteria.schema.json` 12,279（**32%**）/
`audit-result.schema.json` 4,119 / SKILL 1,419。

### 一个运行时条件同时管住两端

| | `criteria_ref.source=project`（常态） | `self_parsed`（首家/兜底） |
|---|---|---|
| 提示词 | 不加载 `criteria.schema.json`（省 12,279 字） | 加载 |
| 输出 | 不回显 `extracted_data.criteria`（省 ~20,600 字/单） | 回显 |

**依据**：`worker.py:175/337` 的 criteria 回填读 `payload.extracted_data.criteria`
（自解析时必须保留）；`compare_input.py:9` 明确「各家结论里的 criteria 快照仅作审计，
不再参与取值」（已注入时回显无价值）。`output.py:478` 也读该字段，需查清用途。

**效果**：脚手架 38,213 → 25,934 字；输出 33,200 → 12,600 字/单。零信息损失。

**最大回归风险**：削断首家评标的 criteria 提权链路。必须加测试钉住
「自解析 → 回显在 → 回填成功」。

---

## P2.5 · 能力档案与部署时校准（新增，排在 P1 之后 / P4 之前）

P4 的批次大小必须由 `observed_output_tps` 与窗口算出来，没有能力档案就只能再拍一个常数。

1. **能力档案**：`MODEL_PROFILES_JSON` 扩展为
   `{context_window, max_output_tokens, accepted_efforts[], supports_structured_output,
   observed_output_tps, json_contract_retries}`。上表 11 处全部改为从此派生，
   **harness 里不再出现任何模型名**。
2. **部署时校准**：把今日手工做的探测固化成一条命令——端点协议 / effort 值域 /
   实际可接受最大输入（二分探，即现在手工标定的 `TENDER_EFFECTIVE_CONTEXT_TOKENS`）/
   输出吞吐 / structured output 支持 / JSON 契约可靠性。产出即上述档案。
   **能力靠实测不靠人手填**（铁律[证据与出处]）。
3. **时间预算**：现只有 token 预算。新增
   `estimated_wall_clock = expected_output_tokens / observed_output_tps`。
   窗口装不下这套提示词时，正确反应是**显式报告"该模型跑不了这套 harness"或切精简档**，
   而不是把证据额度压到 0（今日 95K/50K 即此错）。
4. **专有特性走 capability gate**：structured output / thinking / effort / prompt caching，
   有则用、无则降级。现 `structured: False` 已是该形态，只是写死而非查出。
