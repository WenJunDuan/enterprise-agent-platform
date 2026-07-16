# D1 · eval-tender-scaffold — Review Pass 1（2026-07-15）

> 审查对象：worktree 分支 `worktree-agent-a0d447ab04c842bd5` diff main..HEAD（17 文件，+1626/-274）
> 5 commit：9ddbce5(T1) / 3bee6e6(T2) / 1520260(T3) / c0f0336(T4) / 38bbdb3(T5)
> 主 agent 前置实证：全量 pytest 806 绿 / 5 失败（test_ocr_engine+test_ocr_pipeline 缺 fitz，
> main 基线原样复现=环境既有非 sprint 引入）；ruff 全净。

## Reviewer findings（独立只读审查）

**无 P0 / P1。2 条 P2，均不阻塞 merge：**

### RF1 [P2] score_consistency 浮点显示噪音
- `server/tender/eval.py:200-208`（`_scored_summary`）、`:306-307`：total 以 `float` 累加，
  整数分在 format_report 打成 `60.0`；测试靠 `60.0 == 60` 通过。纯观感，建议 polish 时
  format_report 格式化整数。
- 处置：**defer → polish stage**。

### RF2 [P2/INFO] golden manifest `case_dir` 无 `../` 穿越校验
- `server/tender/eval.py:156-159` → `:380-391`。manifest 的 case_dir 原样传入评估管道。
- 判定依据：部署机手跑 CLI、manifest 由操作员自著（README 明确离线 harness 定位），
  操作员本就拥有等同文件系统权限，非网络面/多租户信任边界；audit/eval.py 先例同样无守卫。
  符合 security-checklist "内网工具/CLI 安全要求可适当放宽"例外。
- 处置：**记录不整改**（若日后 eval 暴露为服务接口，此项升 P0 必须加守卫）。

### 已核无发现（摘要）
- correctness：null 语义 1:1 复用 `is_real_number`（无语义漂移）；全 null run count=0/total=0
  照常进极差；repeat<2 返回 skipped 不算假极差；警告模式不置 fail 均有直接断言。
- 迁移保真：runner.py 与原 tender_worker.py 逐行比对字节等价（仅两处声明接缝：
  TENDER_OCR_PURPOSE 挪家 re-export + model 参数纯增量默认 no-op）；调度壳 kwargs 原样；
  monkeypatch 别名机制实证不受影响。
- security：无硬编码密钥；CLI 纯 argparse 无 shell/subprocess；env 读取均有安全默认。
- layering：server/tender/ 零 `server.routes.*` import（round1 F1 闭环）；4 条守卫为真实
  regex 扫描非空壳，可执行且能抓真实违规。
- test risk：retarget 测试仅改 import/patch 目标，断言零删除零削弱。
- 反过度工程：无多余抽象；harness 边界单 case 容错 catch 为 design 明确要求且不吞
  （ERROR 进报告），非 blanket。

## Spec-compliance findings

**T1-T5 全部 covered · EXTRA=0 · DEVIATED=0 · MISSING=1（M1）**

| 项 | 状态 | 证据要点 |
|---|---|---|
| T1 纯评分核 | covered | eval.py GoldenTenderCase(:58-73)/score_case(:211-279)/score_consistency(:282-332)/format_report(:335-359)；test_tender_eval.py 34 测试全绿 |
| T2 核心迁包+接缝 | covered | runner.py:129 run_tender_evaluation；调度壳 tender_worker.py:22 别名 import；接缝①ocr_preprocess_block 随迁(runner.py:24) ②TENDER_OCR_PURPOSE 挪家(runner.py:34-38)+re-export(tender_doc_pipeline.py:28)+identity 测试；CLI --manifest/--repeat/--model(eval.py:411-419) |
| T3 TENDER_EVAL_MODEL | covered | config.py:426-441；per-call 覆盖仿 _TENDER_EFFORT，空值零行为；7 个测试锁映射与优先级 |
| T4 fixture+runbook | covered | golden_manifest.json+placeholder-bid/；README 含 env -u 坑(:29-39)/MODEL_CONTEXT_WINDOW(:41-47)/基线收紧 checklist(:103-119, F4) |
| T5 边界用例+layering | covered | 全 null run(F2)+repeat<2(F7) 用例在；4 条守卫按方案 i 落位（含既有 audit↔ocr 改单向, test_layering.py:80,96-107,110-127,132,150） |
| 阈值可配+警告模式 | covered | max_item_spread/max_total_spread 进 manifest(eval.py:70-71)；*_exceeded 只入 warnings，CaseReport.passed 显式排除 spread |
| 运维指标（重试/时延） | **partial → M1** | run_tender_evaluation 返回 (payload, meta)，eval.py:391 只取 payload 丢弃 meta，重试/时延未进 CaseOutcome/format_report |
| 越界检查 | covered | diff 17 文件全落 design 影响范围+4 个必要 retarget；.ai_state/、deploy/、agent-front/ 零改动 |

### M1 [MISSING] 运维指标维度未结构化进报告
- design.md 评分维度表明文："运维指标 | 每次重试数/时延，只记录进报告不判 pass | S7 配套问题②"。
- 处置轮 1（commit 9972808）：latency_sec 实测落地（time.monotonic 包裹）；但 retry_count 用
  `getattr(meta, "retry_count", None)` 兜底——**主 agent 复核判定为空壳**：AgentRunMeta 是
  `@dataclass(slots=True)`（agent_bridge.py:136-149），slots 类不可能被附加属性，该值永久 None，
  "契约重试次数"基线维度实际未落地（正是 D8 要闸的回归信号）。
- 处置轮 2（2026-07-16 完成，commit 9972808 latency + 2f7baac retry 直读）：影响范围小幅修订——
  AgentRunMeta 追加尾部默认字段 `retry_count: int = 0`；runner.py 重试循环成功路径捕获 meta 后
  赋 `attempt`；eval.py:417 直读 `meta.retry_count`（getattr 已删）。
- **主 agent 实证**：load-bearing 测试 `test_run_tender_evaluation_retry_count_after_two_failures`
  （monkeypatch flaky_run 前 2 次抛契约异常、第 3 次成功 → 断言 retry_count==2）真实生效、非空壳；
  全量 `uv run pytest -q` = 813 passed / 5 failed（fitz 环境既有，main 基线同 failure）；ruff 净；
  AgentRunMeta 唯一构造点 json_bridge.py:302 全关键字传参 → audit/expense 零影响（已核验）。
  M1 闭环。

## Evaluator VERDICT

**VERDICT: PASS**（评分 4.6/5.0：Functionality 4.7 / Spec 4.8 / Craft 4.5 / Robustness 4.3）
— 2026-07-16，evaluator 独立复核 T1-T5+M1。

- Sisyphus 完整性：T1-T5 + M1 全 covered，独立复跑测试确认；`done_without_evidence=0`、
  `unresolved_over_engineering=0`。
- M1 真实性核验：`retry_count` 由 AgentRunMeta 真 slots 字段承载、runner 循环真赋值、
  load-bearing 测试真断言（flaky 2 失败→==2），非空壳。
- 5 个 fitz 失败：evaluator 独立确认 `git diff <merge-base>..HEAD -- test_ocr_*` 为空
  （测试文件与 main 分支点字节相同，未被本 sprint 触碰）=worktree venv 环境缺口，非回归。
- 2 条 P2 不阻塞：RF1 float 显示→defer；RF2 case_dir 穿越→CLI 内网例外记录不整改
  （触发升级条件：eval 若暴露服务接口须升 P0）。
- 路径：Feature(infra) 不强制 polish → **直接 ship**，ship 时顺补 ARCHITECTURE.md 正式分层图
  （已于 ship 收口完成）。
- worktree 遗留（不阻塞 merge）：该 worktree `.venv` 缺 fitz，可 `uv sync --extra ocr` 补齐。
