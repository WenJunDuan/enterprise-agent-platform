# 架构现状档 · tender 评标证据可验证性管道（evidence-resolution + BOQ + confidence）

> 子系统：评标结论的**证据可验证性**——回查模型引用的出处是否真在本案底稿、超大报价清单抽取、低置信消费。
> 现状基线：2026-06-22 `tender-evidence-accuracy-hardening` Sprint（R1-R6，12 commits，681 测试绿 + ruff）。
> 交叉审查：每轮 critic + codex 二审 + TDD；reviewer R6 bug-hunt 5 bug 全修。完成详情见
> `sprints/2026-06-22-tender-evidence-accuracy-hardening/goal.md` §九。
> 焦点：从「评分逻辑正确」推进到「**证据可验证 + 报价规模正确 + 置信度消费**」。

## 子系统职责（治什么）

评标结论里模型引用的每条出处 `(文件, 第N页, 原文 quote)`，此前**无任何代码**回查它是否真在本案
底稿——靠提示词自检不可靠（R2024-007 单标 8636 页远超模型可核实范围，会脑补页码/原文）。本子系统
在结论后处理做**确定性回查**，把「定位不准 / 引文不实」从静默通过变成可抓、可降级。

## 核心数据流（底稿 → 校验透传管道，R1）

```
tender_worker._run_evaluation
  └─ ocr_block (本案底稿: 每文件 ### 文件: <name> + 逐页 【第 N 页】 锚点)
     └─ run_command_json(evidence_source=ocr_block)        ← 显式命名参数,非 **opts(否则漂进 build_options 报错, codex P2)
        └─ run_agent_json(evidence_source=...)             ← 喂校验,不进 prompt(prompt 走 context, 见下)
           └─ apply_schema_semantics(schema_name, output, request_id=, evidence_source=)
              ├─ 1. normalize   盖 server 元数据(claim_id/reviewed_by/timestamp)+拍平 envelope
              ├─ 2. json-schema 硬『形』校验(normalize 后/enrich 前)
              ├─ 3. validate    语义承重闸(verdict/policy_refs/评分一致性,不放松)
              ├─ 4. enrich      派生 result/conclusion
              └─ 5. resolve     evidence-resolution 闸(仅当透传底稿+schema 注册了 resolve hook)
```

- **关键：`evidence_source` = 原始 `ocr_block`，不是 `context`**——`context` 尾部已追加 criteria 注入块 +
  OCR 头注释，会干扰 tier/page 解析（design critic blind-spot C）。喂模型的是 `context`，喂校验的是裸底稿。
- **resolve 是第 5 步（最后）**：其写的额外标注键（`resolution`/`clarity_flag`/`evidence_resolution`）不再过
  schema 硬校验，返回值直接归档；若 resolve 内升 verdict 会重跑 enrich 保持一致。
- **向后兼容**：resolve hook 注册在 audit-result schema 上（`output_contracts.py`），但仅当调用方透传
  `evidence_source` 才触发——audit/expense 不透传 → 跳过，行为零变化。

## evidence-resolution 闸（`server/common/evidence_resolution.py`，622 行）

回查 `evidence_chain` + `scoring[].deduction_hits/award_hits` + 废标/资格 hits 的每条出处：

1. **底稿解析** `parse_corpus`：切成 `[{tier, file, page, text, clarity}]`。两态统一——有 `=== …底稿 ===`
   外层标记（doc-layer）按它定 tier；无标记（inline OCR）按 `### 文件:` 文件名推断（招标→tender / 投标→bid）。
2. **索引** `CorpusIndex`：file-level 索引 + 各 tier 规范化全文。`normalize_text` 激进规范化（NFKC 全半角 +
   小写 + 去空白 + 去标点/符号），quote 与底稿用**同一套**，治模型转述/全半角差异。
3. **存在性匹配** `existence_ratio`：逐字子串命中→1.0；否则 k-gram 覆盖率（连续片段在底稿出现比例）作软度量。
   全程 C 级 `str.find`，亚秒级。
4. **双阈值三档** `_classify`：≥0.65→`resolved`；≤0.30→`unresolved`；中间→`weak_match`（**不降级**）。
   file/page 精度（`confirmed`/`file_ambiguous`/`page_mismatch`/`no_page`）仅在 resolved 后作细化标注。
5. **降级**：仅 `unresolved` 承重 scoring 项 → `manual_review`（score=None，basis 追警示，幂等）。
   **verdict 一致性回填**（codex P1）：有新 manual_review 项且 verdict=approved → 升 manual_review
   (`insufficient_evidence`) 重跑 enrich；rejected 终局更强不翻盘。废标/资格依据**仅标注不动 verdict**（高代价决定）。

## BOQ 感知抽取 + 截断策略（R2 + perf，`server/ocr/boq.py` 269 行）

- **问题**：已标价工程量清单（BOQ）动辄数千页（R2024-007 二建 `1.05` = 8417 页 / 8M 字符）。
  `build_extraction_block` 旧逻辑从头截 `MAX_FILE_BLOCK_CHARS`（200000，env `OCR_MAX_FILE_BLOCK_CHARS`）→
  总价虽在 p2 扉页未被截，但**淹没在 ~210 页密集表行噪音里**，模型不稳定识别。
- **`is_boq`**（文件名关键词 或 内容表头特征）→ **`extract_boq_summary`**：确定性抽**投标总价**（扉页/前5页 +
  小写 + 大写校验候选打分，非取首个）/ 各类合计 / Top-N 高价 → 几 KB 紧凑摘要替代从头截
  （`pipeline._render_body`：`len>MAX` 且 is_boq 时注入摘要，否则回落首尾各半截 0.7/0.3，绝不只取前 N）。
- **perf**（`server/ocr/native.py`）：超大 PDF（>500 页，env `OCR_FIND_TABLES_MAX_PAGES`）**跳过逐页
  `find_tables`**（8417 页耗 324s + 产 17970 冗余表）→ BOQ 首跑 OCR **324s→28.9s（11×）**。
- 摘要页锚点**独占行** + 逐字保留金额（满足 R1 `_PAGE_RE` 回查）。扫描件 BOQ（OCR pages 表格）留 backlog。

## confidence 消费（R3）+ scoring 明细（R4）

- **R3**：`### 文件:` 头解析 clarity（`清晰度低`→low / `清晰度未知`→unknown / else clear）。
  `low_clarity_files` 随结论 emit（可见性）；evidence 命中 low 文件打 `clarity_flag`；**G3 兜底**：scored 且
  score==0 且点名 confirmed-low 文件（「读不清≠没提供」嫌疑）→ 降 manual_review。unknown（云 OCR 常态）不降级，仅可见。
- **R4**（`output_contracts._verify_score_mode_consistency`）：扣分项 scored 却无 `deduction_hits` 逐条明细、
  或加分项 score>base 却无 `award_hits` → warning（违 tender-evaluate.md「禁止笼统扣X分」，提示人工核验）。

## 关键架构决策

1. **存在性=主信号，file 级索引**：19 家投标各自 `【第N页】` 从 1 重置，按 `(tier, page)` 索引会跨文件误命中 →
   必须 file 级。「原文是否在该 tier 底稿里」是抗编造的稳健硬信号，file/page 只作细化标注，绝不单独支撑 resolved。
2. **宁漏勿误杀**：双阈值 + 中间带 `weak_match` 不降级（模型转述非逐字易触发，先漏报勿误杀）。
   开关 `EVIDENCE_RESOLUTION_DOWNGRADE=0` 可只标注不降级，dogfood 看纯命中率/假阴性率再开降级。
3. **失败安全**：闸内任何异常 → 原样返回结论 + log warning，**绝不因回查崩评标**。BOQ 抽取失败 → 回落截断（不更差）。
4. **k-gram 语料上限**首尾各半截（默认 4M，env `EVIDENCE_MAX_CORPUS_CHARS`），绝不只取前 N（重蹈 BOQ 尾部丢失）。

## 配置（env，运行时动态读，便于灰度调参）

| env | 默认 | 作用 |
|---|---|---|
| `TENDER_EVIDENCE_RESOLUTION` | 1 | evidence-resolution 闸总开关 |
| `EVIDENCE_RESOLUTION_DOWNGRADE` | 1 | unresolved 项是否降级（0=只标注） |
| `RESOLUTION_ANNOTATE_RESOLVED` | 1 | resolved 项是否也写 resolution 标注 |
| `EVIDENCE_RESOLVE_THRESHOLD` / `EVIDENCE_ABSENT_THRESHOLD` | 0.65 / 0.30 | 双阈值 |
| `OCR_MAX_FILE_BLOCK_CHARS` | 200000 | 单文件底稿截断上限 |
| `OCR_FIND_TABLES_MAX_PAGES` | 500 | 超此页数 PDF 跳过 find_tables |

## grounding 纠偏（深潜数据有误，已实读修正）

- **真投标总价 = 381,574,199.97 @p2 扉页**（非深潜的 851,886@p8414，那是单位工程税金合计）。
- **OCR 非「占比可忽略」**：`find_tables` 对 8417 页耗 324s 才是 BOQ 真瓶颈（深潜误判 OCR 不是瓶颈）。

## 待办（backlog，goal §九 移交）

- 招标人侧合规 MVP（v2，需法规源 + 用户确认，CLAUDE.md 定 v1 不含程序合规）。
- compare 多家真模型 dogfood；真扫描件 confidence 触发率验证（R2024-007 全 native 不触发 R3 降级路径）。
- 扣分命中 / 限价 formula 调优（需满分扣减制 + 限价标作素材）；扫描件 BOQ 抽取（OCR pages 表格路径）。
