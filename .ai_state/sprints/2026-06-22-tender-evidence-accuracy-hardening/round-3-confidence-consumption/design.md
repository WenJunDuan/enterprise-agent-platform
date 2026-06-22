# R3 设计 · confidence 消费（低置信→manual_review，接 G3）

> Sprint `2026-06-22-tender-evidence-accuracy-hardening` · Round 3
> 路径: **Feature**（扩展 R1 evidence_resolution + pipeline clarity 传递；~3 文件）
> 行号 2026-06-22 实测。

## 一、背景（WHY）

底稿**已采集** OCR 逐页 confidence（`engine.py:_page_confidence`）并经 `file_clarity`（`pipeline.py:214`）归为 clear/low/unknown/failed，且在底稿文件头注 `_CLARITY_NOTE`（`pipeline.py:293`，`[⚠清晰度低…]`/`[清晰度未知…]`）。但——
- **只是提示词信号**：`grep file_clarity server/common server/routes` **零命中** → 校验层完全不消费，全靠模型自觉（违项目"靠校验层兜底，不靠提示词"哲学，与 R1 evidence/absence 同源）。
- **clarity 被丢弃**：评标结论里看不到"哪些文件读不清"——人工/下游无从知晓低置信风险。

痛点：盖章/扫描/手写件读不清时，模型可能把"读不清"误判成"没提供→客观 0 分"（范畴错误，G3）。提示词已大量叮嘱（`tender-evaluate.md:63-67`），但靠模型自觉必有漏。

## 二、方案（HOW）—— 扩展 R1 `evidence_resolution`（底稿已透传，复用管道）

### A. parse_corpus 捕获 per-file clarity
- 底稿文件头 `### 文件: <name> (...) [检出印章 N 枚] [⚠清晰度低：…]`。R1 `_FILE_RE` 已捕获文件头整串。
- 扩展：从文件头串检测 clarity 标记 → 建 `{file_name: clarity}`（low/unknown/clear）。`_FILE_META_RE` 剥 `(kind=...)` 后，clarity 标记在尾部 `[⚠清晰度低`/`[清晰度未知`/`[检出印章` → 按子串判 clarity，并清出纯文件名。

### B. 结论里结构化 emit（消费①：可见性，零风险）
- `extracted_data.evidence_resolution.low_clarity_files: [{file, clarity}]`——把"哪些文件读不清"持久化进结论（原来只在 OCR 期一闪而过）。`extracted_data` 是 `additionalProperties:true`，安全。

### C. G3 确定性兜底（消费②：低置信→manual_review，保守）
- 对每个 scoring 项的 evidence 命中（`deduction_hits/award_hits[].evidence.source`，R1 已解析）：若 **source 文本点名了某低置信文件**（按文件名子串匹配 clarity map 里 low/unknown 文件）→ 该 evidence 标 `clarity_flag`。
- **降级条件（窄、保守，治 G3 误判 0）**：scoring 项 `status=="scored"` 且 `score==0`（"读不清却判 0"嫌疑）且其某 evidence source 点名低置信文件 → 降 `status:"manual_review"`、`score:null`、`basis` 追加「⚠ 出处文件 OCR 低置信，'读不清≠没提供'，已降人工复核」。**复用 R1 的 verdict 一致性回填**（approved→manual_review + 重派生）。
- **不点名低置信文件 / score≠0 / 非 scored → 不降级**（保守，无 source 归属时绝不误杀；absence 项无 hit→不动，交提示词侧 + 人工）。
- 受 R1 同一开关 `EVIDENCE_RESOLUTION_DOWNGRADE` 控制。

### D. 提示词（已厚，仅微调对齐）
- `tender-evaluate.md` G3 段已充分（:63-67）。补一句：结论 `extracted_data.evidence_resolution.low_clarity_files` 由服务端确定性给出，低置信文件里的"缺失/未提供"判 0 前必复核。低风险，不依赖。

## 三、影响范围
| 文件 | 改动 |
|---|---|
| `server/common/evidence_resolution.py` | parse_corpus 捕获 clarity；resolve 加 low_clarity_files emit + G3 兜底降级 |
| `tests/test_evidence_resolution.py` | 加：clarity 解析 / low_clarity_files emit / 点名低置信文件 score:0→降级 / 未点名不降 / clear 文件不触发 |
| `.claude/commands/tender-evaluate.md` | G3 段微调（引用 low_clarity_files） |

**不改**：pipeline OCR/clarity 计算（已对，仅消费它）；schema。
**范围边界**：R2024-007 全 native 文本层（file_clarity=clear，无低置信）→ R3 **无法在 R2024-007 真模型 dogfood**；以单测（合成低置信底稿）+ 逻辑验证为准，真扫描件验证记 backlog（需盖章/扫描样本）。

## 四、风险与缓解
| 风险 | 缓解 |
|---|---|
| **误杀**：把可读文件的 score:0 误降 | 仅当 evidence source **点名低置信文件**才降（精确归属）；未点名→不动 |
| **absence 项无 hit 覆盖不到** | 已知局限：absence（score:0 无 evidence）交提示词侧（已厚）+ 人工；确定性兜底只覆盖可归属的命中项（诚实，不谎称全覆盖） |
| **文件名子串误匹配** | 用规范化后的完整文件名子串（含扩展名），避免短词误中 |
| **clear 文件误判低置信** | 仅 `[⚠清晰度低`/`[清晰度未知` 标记触发；clear 无标记不触发 |

## 五、验收
1. 单测：clarity 解析（low/unknown/clear/印章共存）；low_clarity_files 正确 emit；scoring score:0 + 点名低置信文件 → manual_review + verdict 回填；同项 score>0 不降；未点名不降；clear 文件不触发；开关关闭不降。
2. 回归 `pytest -q` 全绿 + ruff。
3. R2024-007（全 native）回归：无低置信文件 → low_clarity_files 空、零降级（不破 R1/R2 既有 dogfood 行为）。
4. 合成低置信底稿端到端（apply_schema_semantics 经 evidence_source）：低置信文件的 score:0 项被降级。

## 六、实施（TDD）
1. 测试红 → 2. 实现 parse clarity + emit + G3 兜底 → 3. 回归+ruff → 4. 提示词 → 5. commit。

## 七、设计审查记录（impl 前）—— critic NEEDS_REVISION + codex NEEDS_REVISION，findings 全部纳入

**修订决策（覆盖两轮 8 findings）**：
1. **F1[P0] 文件名提取脏污**：新 `_parse_file_head(head) -> (name, clarity)`——先从整串判 clarity（`[⚠清晰度低`→low / `[清晰度未知`→unknown / 否则 clear），再 `re.split(r"\s*\(kind=|\s*\[", head, 1)[0]` 取**首个 `(kind=` 或 `[` 之前**的纯文件名（同时治 R1 既有"标记文件名不洁"小债）。
2. **codex#1[P1] emit 被吞**：`low_clarity_files` 放进同一 `summary`；写出条件 `summary["checked"]>0 **or** low_clarity_files`。加"只有低清晰文件无 quote 仍 emit"单测。
3. **codex#2[P1] 字段覆盖**：per-evidence 用**独立字段** `ev["clarity_flag"]`，绝不碰 R1 写的 `ev["resolution"]`。测 resolved/unresolved 项 clarity_flag 与 resolution 并存。
4. **codex#3[P2]+幂等**：抽 `_downgrade_scoring_item(sitem, *, note, resolution_status, summary) -> bool`（scored→manual_review 仅迁移一次返 True；已 manual_review 只补 note 不重复、返 False）。**R1 既有降级也改用此 helper**（统一幂等）。`any_new_manual |= ...`。测"同项 unresolved+low_clarity 双触发"幂等（不重复 downgraded_items/basis）。
5. **F3[P1] unknown 不降级**：G3 降级**仅 `low`**（confirmed 低置信）；`unknown`（云 OCR PaddleOCR-VL 常态）→ 只进 low_clarity_files 可见性，**不降级**（避免云 OCR 路径全量误降）。
6. **codex#4[P2] 文件名匹配**：`_normalize_filename(s)`=basename+NFKC+lower+去路径分隔；匹配=低置信文件**完整名或 stem(≥4 字符)** 出现在规范化 source 里（不反向短子串）。测 path/case/ext/stem 四类。
7. **F2[P1] source 无文件名局限**：方案 C 显式声明"source 不含文件名→不降级（已知局限，交提示词侧+人工）"；加单测 `source="投标文件第3页"`(无名)+有低置信文件 → 不降。
8. **F4[P2] 合成测试局限**：验收注明合成底稿验代码路径，真实触发率受 F2 约束，真扫描件验证留 backlog。

**触发面诚实声明**：R3 确定性降级仅在「scoring scored+score:0 且 evidence.source 点名 `low` 文件」触发——native 标书(clarity=clear)永不触发、云 OCR(unknown)不降级、模型 source 不带文件名时不触发。**主价值=可见性 emit（low_clarity_files）+ 精确归属时的兜底**；absence 项与无名 source 仍靠已厚的提示词侧 + 人工。不谎称全覆盖。

## 八、自测结果（2026-06-22）

- **单测**：`tests/test_evidence_resolution.py` +11 R3 例（_parse_file_head clarity+洁净名 / _normalize_filename / clarity_map+low_clarity_files / 无 quote 仍 emit / score:0+点名low→降级+verdict回填 / score>0不降 / 未点名不降 / unknown不降仅emit / R1+R3双触发幂等不重复）。全绿。
- **回归**：`uv run pytest -q` **672 全绿**（R2 663 + 9 净增）+ `ruff check .` clean。
- **R2024-007 验证**：全 native 文本层 → `file_clarity=clear` → `low_clarity_files` 空、零降级 → **不破 R1/R2 既有 dogfood**（无低置信文件，R3 静默不触发，符合预期）。
- **真扫描件 dogfood 受限**：R2024-007 无低置信文件，R3 确定性路径无真模型素材验证（合成底稿单测验代码路径）；真盖章/扫描件触发率验证留 backlog（需样本）。

## 九、进度回写（2026-06-22）

- **状态**：R3 impl 完成 + 自测通过。
- **交付**：扩展 `server/common/evidence_resolution.py`——parse_corpus 捕获 per-file clarity（`_parse_file_head` 洁净文件名）、CorpusIndex.clarity_map + low_clarity_files()/source_names_low_clarity_file()、`_downgrade_scoring_item` 幂等 helper（R1/R3 共用）、`extracted_data.evidence_resolution.low_clarity_files` emit、G3 兜底（scored+score:0+点名 low 文件→manual_review）。提示词 G3 段加 low_clarity_files 引用。
- **两轮设计审查**（critic + codex 各 NEEDS_REVISION，共 8 findings）全部落地（§七）。
- **诚实声明**：R3 主价值=可见性 emit + 精确归属兜底；absence/无名 source 仍靠提示词侧+人工；unknown（云 OCR 常态）只 emit 不降级。
- **Followup**：真盖章/扫描件触发率验证（需样本）；absence 项无 evidence 归属的更强兜底（待 R4/思路）。

## Round 3 · Critic Findings (critic, 2026-06-22T10:00:00Z)

### VERDICT: NEEDS_REVISION

### 评分

| 维度 | 评分 (1-5) | 关键 finding |
|---|---|---|
| 边界条件 | 2 | 文件名含印章标记时 clarity 解析脏数据；unknown clarity 处理不明 |
| 错误处理 | 4 | 继承 R1 失败安全兜底，可接受 |
| 测试覆盖 | 3 | 核心缺：source 无文件名时不触发降级的单测；印章共存文件名 |
| 历史决策对齐 | 4 | 无明显冲突；开关复用合理 |
| 复杂度 | 4 | ~3 文件，规模适中 |
| 历史教训 | 3 | absence-is-not-zero 部分对齐；但 source→filename 归属失败时的静默不触发未充分暴露 |
