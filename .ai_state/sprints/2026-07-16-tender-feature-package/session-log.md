# Session Log — 2026-07-16-tender-feature-package

## 2026-07-16 (checkpoint)

- **做了**：
  - **D1 收官**：M1 轮2返工完成（eval.py 直读 `meta.retry_count`，commit `2f7baac`）→ evaluator
    VERDICT=**PASS**（4.6/5，reviews/pass1.md）→ ship：merge `77d9ffe` 回 main（D1 共 7 commit
    T1-T5+M1×2）、清 worktree、ARCHITECTURE 分层图重绘（ocr 服务层）、items D1=done。main 全量 818 绿。
  - **D1 快速复验**：发现 `--repeat 0` 空跑边界 + 三处 quick fix（commit `299c223`：repeat 守卫 /
    float 显示 RF1 / case_dir 穿越 RF2），各补测试、821 绿、pass1 P2 清零（`ab56d5f`）。
  - **D2 立项设计**：F6=A schema 分家拍板（compound/2026-07-16-decision-schema-split-tender.md）→
    critic round1=**NEEDS_REVISION**（2P0+3P1，落 design.md Round1 Critic Findings）→ F1/F5 用户拍板
    + F2/F3/F4 定 → 5 项应答落 design.md「Round1 修订应答」（`38659db`）。
- **状态**：stage=design · path=System · sprint=2026-07-16-tender-feature-package(D2)。
  D1 DONE（**未 push 远程**，被 stage 门禁挡，待用户 `! git push origin main`；本地领先 origin 17 commit）。
  D2 design 定稿应答就绪。
- **决策**：F6=A schema 分家 / F1=schema_path 别名 / F5=evidence 拆分（通用留 common，建议
  `server/common/corpus.py` 为 D7 预留）/ F4=#8 worker harness 移出 D2 独立 sprint。
  **范围校准**：D2 = 纯移动 + F6 schema 分家（含 contract 机制向后兼容小改）+ evidence 拆分。
- **下次接续**：D2 三选一——(1) 二轮 critic 确认 5 项应答无漏（推荐，因碰共享 contract 机制）/
  (2) 直接 ready 进 impl（红区 worktree 强制，按 design.md「Round1 修订应答」F1-F5 落地）/ (3) 已歇。
  **impl 入口** = design.md「Round1 修订应答」+ 迁移清单。另：D1 push 待用户手动执行。
- **blocker**：无（D2 待用户选下一步方向，非技术阻塞）。
