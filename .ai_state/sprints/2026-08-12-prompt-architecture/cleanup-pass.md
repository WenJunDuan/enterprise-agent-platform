# Cleanup Pass（polish）— 2026-08-12-prompt-architecture

- 日期: 2026-08-13
- 触发: reviews/pass2.md VERDICT=PASS + path=Refactor（红区）
- 队列来源: pass2 evaluator 明文 defer 的 F4 / F5 / N1

## 改了什么

| 项 | 处置 | commit |
|---|---|---|
| reviews/ 入库 | pass1.md + pass2.md 提交 | `54e2c0e` |
| **F4** | `_verify_pending_reason` 的惰性 schema 加载（`global _PENDING_REASONS` 三行）下移到 `scoring` 确认为 list 的早退之后——expense 等无评分路径不再触发无谓文件读；加载点上方加一行说明注释。output.py 716→718 行（≤720 ✓）；14 条相关测试零修改全绿 | `c2bb7fa` |
| **F5①** | `test_prompt_budget.py` references glob `skills/*/references/*.md` → `skills/**/references/*.md`。**先测量**：`find .claude/skills -path '*/references/*.md' \| xargs wc -c` 得 9 档，最大 `s3-scoring-modes.md` 9,796B < 10,240 → 扩面不引入新红，放心扩（未走保守分支） | `1b3af47` |
| **F5②** | `_known_entities` 从"扫 md 前 6 行找 `name:`"改为按 frontmatter 边界（首个 `---` 到下一个 `---`）扫，新增 `_frontmatter_lines` 辅助函数。核实全部 13 个 SKILL.md + 6 个 agent md 均为 `---` 开头且 `name:` 在第 2 行 → 实体集合不变，仅去脆弱性 | `1b3af47` |
| **N1** | design.md L336 Round 2 历史记录「合计 ≤13,700」后加「（2026-08-13 修订为 13,750，见预算表修订块）」——只加指向，历史记录本体未改 | `ea4c943` |
| architecture | 新增 `.ai_state/architecture/system-prompt-architecture.md`（93 行）+ ARCHITECTURE.md 索引行 | `bd109d9` |
| compound | 新增 `compound/2026-08-13-learning-design-budget-must-account-own-mandates.md` | 见收尾 commit |

## 验证结果

- `uv run pytest tests/test_tender_pending_reason.py tests/test_tender_pending_reason_source.py tests/test_prompt_budget.py -q -p no:randomly` → **21 passed**（11+3+7，与 review 基线同数）
- `uv run ruff check server tests` → All checks passed
- `evidence/section_budget.py` 复跑 EXIT=0，8/8 节无 OVER，合计 12,442 ≤ 13,750，整文件 12,442 ≤ 15,000（polish 未改动骨架，数值与 pass2 逐值一致）
- 用户指示节省 token：本轮不跑全量 pytest，改跑上述受影响目标测试；`evidence/pytest-baseline.txt` 的全量 diff 核验沿用 pass2 记录（生产代码本轮唯一改动 = output.py 语句顺序，无新增依赖面）

## 记录不改的项

- **N2（骨架冻结）**：「执行方式+S0」节余量仅 4B（746/750）。polish 全程未触碰
  `tender-evaluate.md` 任何文案。doc-style 扫描在骨架与 5 个 references 中未发现 P0/P1 级
  缺陷（无 TODO/FIXME、无注释掉的代码、无悬空指向）；措辞层面的可优化点即使存在也不动，
  改动须回 design 预算表走修订流程。
- **N3**：containment 白名单的 STALE_WHITELIST 反向失效检测在位，机制无放水，记录在案不动。
- 未重开 F1/F2/F3（已闭合）；未碰 `server/tender/worker.py`；无队列外顺手改动。
- runtime-verify 4 项 + AC7 eval 基线仍 deferred，交部署机窗口（见 `evidence/runtime-verify-defer.md`）。

## doc-style 扫描（本次改动面）

1. 公开 API docstring：`_frontmatter_lines` 新增函数带完整 docstring（含"为什么不用固定前 N 行"）；
   `_verify_pending_reason` 原 docstring 未动且仍准确。
2. 注释位置：F4 新增注释在被解释行**上方**，无过长行尾注释。
3. `test_prompt_budget.py` 头注（超界须下沉、不得抬常量的棘轮流程）复核仍准确，未改。
4. 改动面 grep `TODO|FIXME|XXX|console.log|print(` 零命中；无注释掉的代码。
