# learning · 返工引入的 P0 只有下一轮 review 能抓住（tender-eval-hardening 实测）

## 事实

2026-08-11/12 的三 slice program（H1 横比/H2 页锚/H3 并发）共跑 7 轮 review，抓到 4 个 P0：

1. H1 pass1：自动横比调度在 `asyncio.to_thread` 工作线程里 `create_task` → 生产必崩 +
   幽灵 accepted 行永久锁项目。**测试全绿**——因为 AC1 三条测试把被测边界 mock 掉了。
2. H2 pass1：回查闸跨文件误纠（quote 在文件 B 却把文件 A 的页号改成 B 的页号），产出底稿中
   不存在的出处且标 page_corrected 正面状态。
3. H2 pass1：tdd-evidence 自报 5 条实测 1 条（证据落盘缺失，非伪造绿——测试真实存在）。
4. **H3 pass2：修复自己引入的**——pass1 要求的"补跑"状态机，其失败路径把手上可用的降级底稿
   覆写成 NULL（比不修更糟）；pass3 又抓到修复的修复漏了取消路径（CancelledError 不被
   except Exception 捕获，行永久卡 running）。

## 教训

- **"修复引入的新 P0"是常态不是意外**：4 个 P0 里 2 个出自返工轮。新增状态机（快照/回滚/
  结算）的失败路径与取消路径，必须与主路径同等对待地 review——pass2/pass3 不是走过场。
- **mock 边界 = review 必查项**：H1 的 P0 能存活到 review，全因测试 mock 了唯一的生产链路。
  "只 mock 模型/网络边界，链路本身真跑"应成为 generator 派工模板的固定句（本次第二轮起已加）。
- **NO_NEW_FAILURES 基线必须在完整环境测**：worktree venv 缺 ocr extra 时"33 条基线"是残缺
  环境放大出的数字（真基线 16+7），拿它当基线会掩盖真实回归。H3 reviewer 用主 venv 重跑才定音。
- **主 agent 绿区直修（≤3 文件小修）省一次 40 万 token 的 generator 续跑**，但必须同样走
  红→绿并把 evidence 落对位置（e30d32b 的记录挂错 YAML 节点被 evaluator 抓住，E1）。
- **合并序纪律有效**：三 worktree 并行开发 + H1→H2→H3 串行合并 + rebase 后共享契约复核，
  三次合并只有 runner.py 一处需要手工合一（H1 criteria_ref × H3 doc_layer 正交并存）。

## 出处

roadmap/2026-08-11-tender-eval-hardening + 各 sprint reviews/pass1-3；关联 [[2026-07-30-learning-document-ingestion-deployment-evidence]]（契约链漏末端消费者同族教训）。
