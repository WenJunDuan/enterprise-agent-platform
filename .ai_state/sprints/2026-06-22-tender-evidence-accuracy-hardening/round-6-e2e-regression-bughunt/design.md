# R6 · 三层数据 e2e + 全回归 + 跨轮 bug-hunt（收官）

> Sprint `2026-06-22-...` · Round 6 · 路径 **验证/对账 + bug-hunt**
> 2026-06-22。

## 一、e2e / 多模型 / 三层数据 核查

| R6 项 | 结论 | 证据 |
|---|---|---|
| **全回归** | ✅ 681 全绿 + ruff clean | `uv run pytest -q` |
| **多模型** | ✅ qwen + deepseek 实跑（R1 无 BOQ / R2 含 BOQ 各一遍，bid_price 真值、verdict 正确、evidence_resolution 分布、零误杀） | R1/R2 dogfood §七/§八 |
| **三层数据 e2e（② criteria 首写赢+后续读）** | ✅ 既有测试覆盖 | `test_tender_p3_backend.py:50-148`（writes_when_none / first_writer_wins / skips_* / not_in_db / exception-safe）|
| **compare 横比排名/推荐** | ✅ 既有测试覆盖（compare 本 Sprint 未改） | `test_tender_compare.py:89-247`（schema / collect input / 两家门槛 / 不污染 results·roster）|

> compare 全链路真模型 dogfood（二建+四建）未跑：compare 命令本 Sprint **未改动**，且其逻辑由 `test_tender_compare.py` 覆盖；R1-R5 改的是 evidence_resolution/boq/pipeline（已各自 dogfood）。真模型多家 compare 验证留 backlog（需两家完整评标，~10min）。

## 二、跨轮 bug-hunt（用户指定"测完自己检测提 bug"）

并行两独立审查者审 Sprint 累计 diff（`26ab86d..HEAD`，~1000 行）找真 bug。

### reviewer subagent（VERDICT 报 5 findings，**全部已修 + 加回归测试**）

| # | 严重 | bug | 修复 |
|---|---|---|---|
| F1 | P1 | `boq._AMOUNT_LOOSE \d{5,}` 命中 5-9 位序号 → 投标总价可能选成序号（`_find_amount_near` 取首个） | loose 档改取窗口内**最大**金额（总价是大数）；+回归 `test_bidtotal_picks_max_not_sequence_number` |
| F2 | P1 | `_FILE_HEAD_SPLIT_RE` 在文件名普通 `[` 处切断（`file[1].pdf`→`file`）→ 短名子串误匹配 clarity | 正则只在已知标记 `[检出印章`/`[⚠?清晰度` 处切；+回归 `test_parse_file_head_keeps_bracket_in_filename` |
| F3 | P2 | `page_status` whole tier 无 key 时不回退 → page_mismatch 统计虚高（不影响降级） | `files is None` 即跨 tier 回退 |
| F4 | P2 | R1+R3 同项双触发时 R3 低置信 note 丢（elif 跳过） | if/elif 后独立补 R3 note；+断言双 note 都在 basis |
| F5 | P2 | `_FILE_META_RE` 死代码（R3 后未用） | 删除 |

### codex exec（bug-hunt 第二遍，找 reviewer 漏的）
_（运行中，完成后回填结论 + 处理）_

## 三、自测结果
- 修复后回归 **681 全绿** + ruff clean（含新增 F1/F2/F4 回归测试）。

## 四、进度回写（impl 后回填）
_（codex 完成后定稿）_
