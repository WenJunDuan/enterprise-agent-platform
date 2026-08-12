---
sprint_slug: "2026-08-11-compare-authority"
path: "System"
created: "2026-08-11"
last_updated: "2026-08-11"
executor: "generator subagent model=opus, isolation: worktree (红区)"
---

# Design — H1 横比修复：criteria 权威 + 触发后端化 + 可观测 + 价格项判定

## 背景

实跑症状"两个标段都有报价但价格对比没出来"。根因链（2026-08-11 评审，主 agent 已抽查坐实）：

- 横比**全系统唯一触发点**是前端 `use-tender-review-page.ts:532`
  `void triggerTenderCompare(projectId).catch(() => {})`——fire-and-forget，失败静默；
  某家评标 failed 也计入 allTerminal（:513-518），completed<2 时后端 400（compare.py:42-43）被吞。
- compare 任务失败态只写 `tender_compare_tasks` 表，**无任何路由暴露**（compare_worker.py:253-261）；
  `GET /projects/{id}/compare` 无结果恒 404 → 前端永远轮询 null。
- `_find_price_item`（compare_worker.py:129-151）命中**第一个** `tag=requires_cross_bid_comparison`
  项后，max 非有限非负数即 `return None` 提前退出——KD4(0730) 合法化 manual/null 后，价格项被模型
  标成 null 即全池封锁；后续合法价格项永不被考虑。且不校验项名，第一个 cross-bid 项不是价格项也当价格项。
- criteria 一致性判据 = 各家 result 自带 criteria 转录副本的 hash 字节等价（compare_worker.py:98-103）；
  两家并发评标 backfill 竞态（worker.py:294-300 首写者赢）下转录漂移几乎必然 → `criteria_inconsistent`
  全员 manual_review 不排名。`_strip_volatile_formula_data`（tender_compare_store.py:77-81）证明
  规范化军备竞赛已在发生。
- 一行结果缺 criteria 即封锁全池（compare_worker.py:80-81, 99-103）；封锁 note 硬编码"价格项满分
  未设"与实际 reason 不符（:177）；bid_price 无服务端数值校验（:90）；比较池按 result 行全捞不按
  bidder 去重（result_store.py:193-207）。
- 结构病根：`score: null` 承载 ≥6 种语义（等横比/需外部数据/需答辩/回查降级/manual 合法 null/
  实质性不响应），消费端各自立法解释。

## 目标

1. 横比触发不依赖前端在场：评标终态落库后服务端自动判定并入队。
2. compare 生命周期（无/排队/运行/成功/失败+原因/stale）对前端完全可观测，可手动重触发。
3. criteria 可比性判据从"转录字节等价"改为"引用同一项目级 criteria 版本"。
4. 价格项判定健壮：跳过非法项继续找、区分失败原因、note 与 reason 一致。
5. `score=null` 语义显式化：`pending_reason` 枚举随本次 schema 变更搭车。

## 非目标

- 不做"标段"实体建模（两标段建两个 project 的使用约定写入操作文档即可；跨标段合池是使用错误，
  本 sprint 只保证单 project 池正确 + 池内按 bidder 去重）。
- 不做 bid_price 万元/元自动换算（错一个数量级不可接受）：只做数值校验与不一致告警转人工。
- 不动评标 S0-S4 内联流程与 criteria 抽取本身。

## 关键决策

### KD1 · criteria 项目级权威 + 结论引用 ref

`tender_project_docs.criteria` 已是事实上的项目级存储（上传预抽 + worker.py:274-312 评标后
backfill），只是横比判据绕开了它。改为：

- `criteria_version` 语义 = 权威副本的内容 hash，**compute-on-read**（读取时现算，复用现有
  `compute_criteria_hash`，剥 volatile 逻辑保留但只算在权威副本上）：幂等、免 DB 迁移，存量
  `tender_project_docs.criteria`（有内容无 version 字段）自然获得 version——老项目重评即可解锁
  横比，闭环成立（Round1-F2）。runner 注入与 collect 判据**共用同一计算函数**，禁止两处各算。
- runner 注入 criteria 时（runner.py:243-263）把 `criteria_version` 一并注入 prompt 上下文；
  评标结论 `extracted_data` 新增 `criteria_ref: {version, source: "project"|"self_parsed"}`。
  模型仍可保留 criteria 快照供审计，但**判据只看 ref**。
- `collect_compare_input`：可比 ⇔ 全部参与结论 `criteria_ref.version` 相同且等于当前项目权威
  version。self_parsed（S1 自行解析、注入未就绪）结论视为旧版：不再直接封锁，改为提示
  "该家评标早于项目规则定稿，建议重评"并把该家排除出横比（其余 ≥2 家仍可比）；<2 家时才整池转人工。
- backfill 竞态消解：worker 落库结论前若项目权威已存在，结论 ref 必须指向权威 version；
  权威不存在时才允许 self_parsed（首写者赢逻辑保留，但写入即产生 version）。
- 兼容：存量结果无 criteria_ref → 按 self_parsed 处理（排除出池 + 提示重评），不走旧 hash 路径
  （避免两套判据长期并存）。

**备选比较**：a) 继续加强 hash 规范化——否决，模型换版即再漂移，军备竞赛；b) 横比直接用项目权威
criteria、无视结论副本——接近本案，但缺"该结论按哪版规则评的"审计维度，废标争议时无法回溯；
本案 ref+快照兼得。

### KD2 · 触发后端化 + 生命周期可观测

- eval worker 每家评标**终态**（completed/failed 均触发检查）落库后：同 project 内 completed
  bidder 数 ≥2 且无 active compare 且签名有变 → 自动入队 compare（复用现有 `has_active_compare`
  防重与 `_current_compare_signature` 签名）。
- `GET /projects/{id}/compare` 改为恒 200：`{status: "none"|"pending"|"running"|"failed"|"ready",
  error_detail?, stale?, result?}`。failed 时透传 compare_worker 写入的 error_detail
  （脱敏：不含 stack trace，security-checklist 错误处理条款）。
- `POST .../compare` 保留作手动重触发；前端加"重新横比"入口，stale=true 时显式提示可重跑。
- 前端 `use-tender-review-page.ts:532` 的 fire-and-forget 触发保留为冗余但去掉空 catch：失败 toast
  提示（错误可解释）。轮询消费新 status 机（404 分支删除）。

### KD3 · 价格项判定修正

**数据源改为项目权威 criteria 单源**（Round1-F3）：`_find_price_item` 与 `method` 均从项目权威
副本提取一次，供全池使用；各家结论快照仅作审计，不再作为 price item/max/method 的取值来源
（现码 compare_worker.py:99-112 逐家跑转录副本 + `price_items[0]` 的形态废除——否则 ref 同
version 而快照 max 漂移时，判"可比"却拿漂移值算分，转录信任 bug 换皮存活）。

`_find_price_item`：遍历权威副本全部 cross-bid 项，收集合法价格项；非法（max null/非有限/负）**continue**。
返回值区分三态：找到合法项 / 存在 cross-bid 项但全部 max 未知（reason=`price_max_unknown`）/
无 cross-bid 项（reason=`no_price_item`）。`enforce_price_comparison_block` 的逐家 note 按 reason
生成文案（修 F9 误导文案）。同名多合法项 → 取第一个并 warning（criteria 本身异常）。

### KD4 · bid_price 服务端护栏 + 池去重

- collect 时对每家 `bid_price` 做数值校验：缺失/非有限/**≤0**（0 与负数同判非法，兼防数量级
  比值除零，Round1-P2）→ 该家标注 `bid_price_invalid` 并转人工，
  **不封锁其余家**（≥2 家合法仍横比，警告注明缺席者）。
- 各家金额数量级差 ≥100 倍 → 疑似单位不一致（万元 vs 元），整池 warning + manual_review 不排名
  （宁可人工，不自动换算）。
- 比较池按 `(project_id, bid_id)` 取每家**最新**结论，替代按行全捞（消同家重评双行入池）。

### KD5 · pending_reason 枚举（搭车）

`.claude/contracts/common/audit-result.schema.json` 的 scoring item：`score=null ⇒ pending_reason`
必填，枚举 `cross_bid | external_data | live_event | evidence_unresolved | manual_mode |
non_responsive`。`tender-evaluate.md` prompt 同步产出义务；`server/tender/output.py` 校验；
前端 types/model 映射显示文案。存量结果无该字段 → 展示层按现行 tag+status 组合推断（只读兼容，
不回填）。

## 影响范围

```text
server/tender/compare_worker.py        KD1 判据 / KD3 / KD4（基线 299 行，改后仍须 ≤300 或拆 helper 模块）
server/tender/worker.py                KD1 ref 写入 / KD2 自动触发
server/tender/runner.py                KD1 version 注入
server/stores/tender_compare_store.py  KD1 任务签名纳入 version（compute-on-read 免独立存储，
                                       critic R2-P2d 澄清：此处不新增 version 列）
server/stores/result_store.py          KD4 按 bidder 取最新
server/routes/tender/compare.py        KD2 status 路由
server/tender/output.py                KD5 校验
.claude/contracts/common/audit-result.schema.json   KD5
.claude/contracts/tender/criteria.schema.json       KD1 criteria_ref（如需）
.claude/commands/tender-evaluate.md    KD1 ref 义务 + KD5 义务
.claude/commands/tender-compare.md     KD3/KD4 语义更新
agent-front/.../api.ts,model.ts,types.ts,use-tender-review-page.ts   KD2/KD5
agent-front/.../components/bidder-compare-cards.tsx 等展示组件        KD2 状态/KD5 文案
tests/test_tender_compare.py 等        全 KD 红→绿
```

## 已验证基线（2026-08-11 主 agent 实测）

- 全量测试收集数 = 1162（`uv run pytest --collect-only -q | tail -1`）。单写者 sprint，
  AC 用下界：改后收集数 ≥ 1162 + 新增测试数。
- `server/tender/compare_worker.py` = 299 行（`wc -l`）；已贴 300 行 P0 红线，KD1/KD3/KD4 落此文件
  必然越线 → **预先决策**：判据/护栏逻辑拆 `server/tender/compare_input.py` 新模块，compare_worker
  只留任务生命周期。
- `server/tender/runner.py` = 328 行（已越线，豁免：本 sprint 仅 +注入 ref 数行，不扩大，
  拆分并入 OCR 服务迁移期）。
- 【pass1-F5 补账 2026-08-11】实施后核数：runner 328→354（超出"数行"原表述，实为 ref 注入+
  确定性打标两段，豁免维持、上界 360）；另三个基线已越线文件本 sprint 继续增长，同豁免同理由
  （拆分并入 OCR 服务迁移期）：result_store.py 479→554（上界 560）、output.py 664→708（上界 720）、
  worker.py 369→420（上界 430）。AC7 行数门澄清：新建文件 ≤300；基线越线文件不超各自上界。
  【pass2-N4】实测 worker.py = 430，**上界已用尽**：下个 sprint 任何触碰该文件的改动开工前必须
  先拆分或重议上界，不得先写后补。

## 风险与缓解

- criteria_ref 是跨 prompt/schema/服务端/前端契约：一次改全链（同 0730 KD4 教训），联测用真实
  9 项 criteria 往返。
- 自动触发与前端手动触发并存的防重：复用 has_active_compare + 签名判断，双触发幂等（测试覆盖并发
  double-fire）。
- self_parsed 排除策略可能把"唯二"两家中一家排除 → 整池转人工：符合保守原则，warning 写明重评
  哪家可解锁。

## 验收标准

- [ ] AC1 触发：mock 两家评标完成（一家先 failed 后重评 completed）→ 无前端参与，compare 自动入队
  并产出结果；三家场景第三家迟到 → stale=true 且自动重算恰一次。
- [ ] AC2 可观测：compare 失败（构造超时/契约校验失败）→ GET 返回 failed+error_detail；前端可手动
  重触发成功。GET 全生命周期无 404。
- [ ] AC3 判据：两家结论 ref 同 version → 可比（即使快照文本漂移）；一家 self_parsed → 该家排除、
  其余照比；全部 self_parsed 或 <2 家 → 整池 manual 且 warning 指名。
- [ ] AC4 价格项：criteria=[manual/null cross-bid 项, 合法价格项] → 找到合法项正常横比（0730 自锁
  场景回归）；全部 null → reason=price_max_unknown 且逐家 note 文案与 reason 一致。
- [ ] AC5 bid_price：一家缺报价 → 该家缺席、其余两家照常排名；两家金额差 ≥100 倍 → 整池 manual +
  单位告警；同家双行结论 → 池内只取最新。
- [ ] AC6 pending_reason：评标输出 score=null 项均带合法枚举；缺失 → output 校验拒绝；前端按枚举
  显示对应文案；存量无字段结果展示不回归。
- [ ] AC7 质量门：先红后绿证据齐（tdd-evidence 八字段）；`uv run pytest -q` 全绿且收集数 ≥1162+新增
  构成式；`uv run ruff check .` 净；前端 test/build/eslint 绿；compare_worker.py ≤300 行。
  【evaluator 口径修订 2026-08-11】"全绿"在本机按 **NO_NEW_FAILURES** 执行：33 条既有环境失败
  （缺 ocr extra + AUDIT_DIRECT_CONNECT 未配，`git stash` 法实测，清单 /tmp/baseline_failures.txt）
  先于本 sprint 存在，验收判据 = 与基线清单逐条 diff 为空。原文"全绿"落笔时未核 pass/fail 基线，
  属措辞缺陷，此行补账（同 F5 先例）。

---

## Round 1 (initial draft by Fable 5)

criteria 项目级权威 + ref 判据、触发后端化、失败态可观测、价格项判定修正、pending_reason 搭车。

## Round 1 · Critic Findings

VERDICT: NEEDS_REVISION（三设计合审，本档相关项）

- F2 [P1] legacy 权威 criteria 无 version，"重评解锁"闭不了环。
- F3 [P1] KD3 未指明价格项/method 从哪份 criteria 提取，转录信任 bug 可能换皮存活。
- P2: bid_price=0/负未列入非法（数量级比值除零风险）。

## Round 2 (revised by Fable 5)

- F2 CLOSED：criteria_version 定为 compute-on-read 内容 hash，幂等免迁移，runner/collect 共用
  同一计算函数（KD1 已改写）。
- F3 CLOSED：price item 与 method 从项目权威副本单源提取，结论快照仅审计（KD3 已改写）。
- P2 CLOSED：bid_price ≤0 与缺失/非有限同判非法（KD4 已改写）。
- 另接受 roadmap 级 F7：本 sprint 与 H2 共享 audit-result.schema.json / tender-evaluate.md /
  前端 model.ts，合并序定为 H1→H2→H3，共享契约文件在 H2/H3 rebase 后做契约合并复核。