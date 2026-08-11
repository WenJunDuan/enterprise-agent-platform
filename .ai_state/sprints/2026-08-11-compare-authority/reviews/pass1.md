# Review Pass 1 — 2026-08-11-compare-authority

审对象：worktree agent-a56af065140f2dc80，5 commits（6c766a5..5b5dc18），diff main..HEAD 31 文件 +2468/-529。
reviewer 与 spec-compliance 并行独立完成；evaluator 判定按主 agent 决策**推迟到 pass2**（本 pass 已有
实测复现的 P0，REWORK 结论无悬念，省一轮 evaluator 额度；如实记账，非绕过）。

## VERDICT 预判：REWORK（P0 待修）

## Findings（reviewer，按严重度）

- **F1 [P0] 自动触发在生产必然 RuntimeError + 幽灵任务永久锁死项目**：worker.py:270 经
  `asyncio.to_thread` 调 `maybe_schedule_compare` → compare_worker.py:199 `asyncio.create_task`
  在无 loop 的工作线程抛 `RuntimeError: no running event loop`（reviewer 在 worktree venv 实测复现）。
  且 :196 已先写入 accepted 行 → `has_active_compare` 恒 True → 自动/手动触发全被闸，GET 恒
  pending，前端 retryCompare 静默吞 409。异常从 finally 冲出还跳过 flusher.cancel。
  修法：判定（to_thread）与 create_task（loop 线程）拆开，或 call_soon_threadsafe；
  "建 accepted 行"与"起协程"必须同成败，失败回滚/置 failed。
- **F2 [P0] AC1 三条测试全 mock 掉被测边界**（test_tender_compare.py:291-296,309-314,339-350），
  生产唯一链路 worker→to_thread→maybe_schedule→schedule→create_task 零覆盖，掩盖 F1。
  修法：补真链路测试（仅 mock `_run_evaluation` 与 `run_command_json`），断言 compare 真进入
  running/completed、eval 不抛异常、flusher 已 cancel。
- **F3 [P1] 无权威 criteria 时封锁原因被价格项短路误报 `no_price_item`**（compare_input.py:152-153），
  复现本 sprint 要修的 F9 病症。修法：先池级可比性后价格项；补 `_new_project(None)` 用例。
- **F4 [P1] output.py:613-617 降级路径 pending_reason 贴错标签**：`insufficient_evidence` 场景打成
  `non_responsive`，与 evidence.py:187 的 `evidence_unresolved` 不一致。修法：改
  `evidence_unresolved` 并在 test_tender_pending_reason.py 锁定。
- **F5 [P1] 越线文件豁免缺账**：result_store 479→554 / output 664→708 / worker 369→420 /
  runner 328→354，design 基线节只记了 compare_worker 与 runner（且 runner 实增超"数行"表述）。
  处置：主 agent 已补记 design 基线节豁免（见 design.md 同日修订），拆分并入 OCR 服务迁移期。
- **F6 [P1] sanitize_error_detail 是透传+浅清洗而非白名单脱敏**（compare_guard.py:55-72）：
  只抹路径不抹凭证类（Bearer/sk-/token），首行取样可能取到空泛前缀。修法：白名单映射，
  仅已知业务异常原文透出，其余固定文案+详情进服务端日志；至少补凭证兜底抹除。
- **F7 [P2]** 排除告警把 16 位 hash 展示给业务用户（compare_input.py:213-216）→ 文案去 hash。
- **F8 [P2]** 列表推导 pop 副作用 + `_pool_blocked_reason` 改参职责混合（compare_input.py:154-158,
  239-242）→ polish 收敛。
- **F9 [P2]** scoring-detail-table 「处理」列 68px 装不下最长枚举文案 → truncate+title 或加宽。
- **F10 [INFO]** 反过度工程双向扫描：无过度抽象；信任边界防护到位，唯一缺口即 F6。

## Spec Compliance（spec-compliance）

- 覆盖矩阵 KD1-KD5 全"齐"，AC 硬指标复核通过（compare_worker 202 行；collect 1196 = 1162+34，
  旧判据测试 4 条随判据废除删除属合法替换）。scope creep = 0。
- **M1**：AC2"前端可手动重触发"无测试锚点（retryCompare 零测试）。
- **M2**：AC1"入队并产出结果"无落库端到端断言（与 reviewer F2 同源，真链路测试可一并覆盖）。
- EXTRA×3 均判合理（compare_guard.py / result_store 两方法 / 前端连带）。
- DEVIATED×3 无行为缺口：D1 ref 改服务端确定性打标（比 design 更强）；D2 criteria_ref 未进
  契约 schema（靠 additionalProperties 放行，唯一写入方是服务端，低风险，pass2 顺手声明）；
  D3 封锁原因两层枚举（reviewer 评估接受，但 F3 分支须修）。
- 附带发现：architecture/system-tender-data-model.md:39 仍描述旧判据，ship 前必须更新（门禁项）。
- 自评建议：REWORK（MISSING>0 判据）；若视 M1/M2 为证据补齐可下调 CONCERNS。

## 两处自报偏离评估（reviewer）

- 偏离①（compare_guard.py 二次拆分）：**接受**，非新增抽象层，合并回单文件反违 300 行 P0。
- 偏离②（两层封锁枚举）：**接受**，比 design 原文更贴 KD1 意图；前提是修掉 F3 的未闭合分支。

## Pass 2 返工清单（发给 generator）

必修：F1（含调度原子性）、F2/M2（真链路测试）、F3、F4、F6、M1。
顺手：F7、F9、D2（schema 声明 criteria_ref）。
留 polish：F8。
主 agent 自理：F5（design 豁免已补）、architecture 档更新（ship 前）。
