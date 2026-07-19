# D11 plan.md — tender 判分纪律残留收口包

- **sprint**: 2026-07-18-tender-discipline-residuals · **path**: System (wave1)
- **design**: `design.md`（critic round1 九条全应答；round2 定稿 in-flight）
- **depends_on**: D1 done · D2 done
- **分派**: 主 agent 设计 + review；codex 多 worktree 并行实现；全批次 worktree 强制（铁律[零写入]）
- **基线**: main `uv run pytest -q` 895 绿 + ruff 净（impl 前置断言，codex 首步复核）

## 并行单元（文件面 disjoint → 真并行安全，各分支独立 merge）

- **Unit B** (worktree `d11-b`, codex)：`server/tender/output.py` · `server/platform/config.py` ·
  `.claude/contracts/common/audit-result.schema.json` · `tests/`
- **Unit A** (worktree `d11-a`, codex)：`server/common/agent_bridge.py` · `.claude/skills/{ocr-page,tender-eval}` · `tests/`
  （与 B 无文件重叠）
- **Unit C**：条件项，不并行 launch（C1 glm 网关前置；C2/R7 待用户授权）

---

## Batch B · 服务端确定性（codex, TDD red→green）

### TB1 / F04 · evidence_chain 顶层派生 — `output.py:enrich_tender_result:570`
- **RED**：顶层 `evidence_chain` 空 + `scoring[]` 有带非零分 `award_hits`/`deduction_hits`
  → 断言派生 `{source, finding, conclusion}` 条目且保留【第N页】页锚。
- **GREEN**：`enrich_tender_result` 追加派生；复用 `evidence.py:_hit_moves_score:117` 判「带非零分命中优先」。
- **空链精确定义（critic F4）**：None / 缺字段 / `[]` / 经 `_normalize_evidence_chain` 拍平后
  `source+finding+conclusion` 全为空串。
- **顺序（critic F3）**：`apply_schema_semantics` 实际序 normalize→schema→validate→**enrich→resolve**；
  派生在 resolve 闸**之前**，派生条目被同次 resolve 当普通项标 `resolution`，但降级只挂
  `scoring[]._check_hits/_downgrade_scoring_item` → **不会二次误降级**。
- **5 断言**：空链派生（含全空串假非空）/ 非空链不覆盖 / 无 scoring 安全跳过 / 页锚保真 /
  **派生条目即便标 unresolved 也不改 verdict 与 scoring**。

### TB2 / R5 · schema 与语义对齐 — `output.py:normalize_tender_result:534` + schema
- **TB2a reviewed_by 盖章**：`normalize_tender_result` 调共享 normalize 后覆盖 `reviewed_by="tender-evaluator"`；
  **不改共享 `_DEFAULT_REVIEWED_BY`**（免波及 expense）。断言 tender 盖章正确 + expense 现有测试全绿（回归证明）。
- **TB2b enum 扩展**：编辑 `audit-result.schema.json` `manual_review_reason` enum，加法式向后兼容；
  值以 `.claude/CLAUDE.md` tender 节为准（先读 CLAUDE.md 现有枚举，缺项补齐，勿臆造）。补 tender 场景断言该 reason 过校验。
- **TB2c policy_refs_detail**：F5 已于 `d26d90d` 实现于共享 `enrich_audit_decision`（有测试）→ 仅补 1 个 tender 回归测试确认（近零工作）。

### TB3 / R6 · config 收口 — `server/platform/config.py`
- **INFRA-01**：定位 `TENDER_TIMEOUT` 与 OCR 云等待实际读取点；启动校验「OCR 等待 ≤ 0.5×TENDER 超时」
  否则日志 **warning（只警告不硬拒**，部署机自主）→ 单测断言警告触发/不触发边界。
- **INFRA-02**：cache v2 首跑重 OCR 部署提示（runbook/README 注记 + 启动日志一行）。

**Batch B 验收**：全量 pytest 基线（895）不回退 + 新增全绿；ruff 净；D1 golden 回归不回退（网关抖动重跑一次口径）。

---

## Batch A · R4 ocr-page 安全硬化 + 接线（codex, 独立安全轮, fail-closed）
前置：F2 Hotfix 已 landed（`agent_bridge.py:180-192` tools 白名单 6 项排除 Bash）→ 在收紧基线上接线。

- **TA0 探查（spike 先行）**：探 `ClaudeAgentOptions.hooks` PreToolUse 回调在现 `query(str)` 架构接法
  （`.claude/settings.json` PreToolUse 有先例）；探 ocr-page skill 实际命令形态。机制不可用 → 停并报告，不硬接。
- **TA1 白名单闸（PreToolUse hook）**：仅允许 ocr-page 规定形态；参数**服务端 Python 层**硬校验（不信任 agent 传参）：
  路径解析后须落本任务提交目录内；页码正整数；拒 shell 元字符 / `../` 穿越。
- **TA2 对抗验证（TDD 红先行）**：注入样本 `;rm`/反引号/`$()` / `../` 穿越 / 超长参数 / 伪造页锚 →
  断言**全部被拒且进程无副作用**。
- **TA3 接线**：tender-eval skill 文档补「读不清页→调 ocr-page→用重识别文本再判」；重识别文本进上下文保留【第N页】页锚。
- **验收（fail-closed）**：对抗测试全绿（**任一失败 = 不接线**，只交付 TA1/TA2 硬化本体，如实记录）；D1 golden 回归不回退。

---

## Batch C · 条件项（建 Task 标 `blocked` + 原因，铁律[Sisyphus] 允许 blocked 语义，critic F6）
- **TC1 / glm 技术参数**：**DESCOPED（用户 2026-07-19：内网隔离部署用 DeepSeek 或 qwen，不用 glm）**。
  技术参数判 manual 是 glm 自身保守（compound `2026-06-23-gate-rescues-not-creates`）；DeepSeek 已在 R8 e2e
  验证技术参数出真分 → glm 专属问题随选型消解，**不做 prompt 加压**（反过度工程：所选模型无此问题）。
  qwen 行为未验，若部署机出现技术参数 manual 届时按模型单独处理。
- **TC2 / R7 前端 null guard**：agent-front 红区，`status=blocked`（待用户显式授权）；授权后另立 codex worktree。

## Gate
每批次独立 commit 序列 → 主 agent review（reviewer + spec-compliance 并行 → evaluator VERDICT）→ PASS 才 merge。
条件项未完成必须显式 `status=blocked` + 原因。

---

## Round2 定稿 critic 结论（2026-07-19, critic subagent）+ 调整

**VERDICT**：批次 B = APPROVE-WITH-CHANGES（可立即 impl）；批次 A = NEEDS_REVISION（1 P0 + 2 P1，已在本 plan + codex-a-prompt.md 消解后 launch）。机制核验：PreToolUse hooks 在 `query(str)` 下确可 deny（SDK `client.py:168-176` 恒 streaming）；F04 派生隔离现有代码已保证（`evidence.py:253-264` 顶层分支只写 resolution，`:271-319` scoring 分支才 downgrade，两路不交）。

### 批次 A 修订（launch codex-A 前已并入 prompt）
- **F1（P0）case-root 无数据通道**：`directory_path` 仅进 prompt 文本，`build_options` cwd 恒 PROJECT_ROOT → 围栏无数据。**决议=option(a) 补数据通道**：加可选 `case_root` kwarg，`run_tender_evaluation→run_command_json→run_agent_json/run_agent→build_options→hook 闭包` 显式透传，默认 None（audit 零影响，回归护航）；围栏在 case_root 子树，防跨案/跨租户读。
- **F2（P1）Bash 死代码**：ocr-page 是 Bash 命令但 `_AGENT_TOOLS` 排除 Bash → 受控加回 Bash（仅 case_root 接线路径）+ 端到端可达性断言。
- **F3（P1）anchored**：PreToolUse 回调对整条 command `re.fullmatch`（非子串/黑名单），偏离即 deny。
- 新测试文件 `tests/test_ocr_page_security.py`（跨案路径必 deny / symlink / 绝对路径 / `../` / 元字符 / page 溢出 / 正向一例 / 端到端可达性）。

### 批次 B 调整
- **F4（P1，历史教训冲突）**：`evidence.py:354-356` verdict 翻转时二次调 `enrich_tender_result`（同 compound `2026-07-18-learning-lazy-import-behavioral-seam` 路径）。**TB1 加第 6 条断言**：走完整 `apply_schema_semantics`（unresolved→downgrade→二次 enrich）场景下派生只发生一次、无重复条目、无副作用。→ **codex-B 已在跑，此项 review 关口强制核验**。
- **TB2b 降级**：schema 7 枚举值已与 `tender-evaluate.md:106` 完全对齐（含 pre_approval_mismatch）→ 从「扩展 enum」降为「确认 + 补 1 测试」。
- 测试文件名点名 `tests/test_evidence_chain_derivation.py`，避免与 Unit A 撞。
