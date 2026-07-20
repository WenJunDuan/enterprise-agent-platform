# Session Log · 2026-07-20（D9 页级流式 OCR 全流程 + .ai_state 整理）

> 本会话增量记录。权威盘面见 _index.md next_action；本文档为可读时间线。

## 会话开场：.ai_state 瘦身整理
- `_index.md` 62.7KB/409 行 → 12KB/141 行（治 hook 每会话注入超限）：next_action 只留当前+上一轮存档，2026-06 逐会话叙事区裁剪（git 历史可回溯），pointers 刷新指 D11。清 `.snapshots` 6 月旧快照 + `.DS_Store`。commit 1da3cb5 push。

## 主线：D9 页级流式 OCR（sprint 2026-07-20-streaming-ocr，System 路径）

### 立项 + design（两轮 critic）
- 用户拍板 D9 先行（部署机窗口交 codex）+ 授权 agent-front 红区。
- route-note：Feature 路径；`depends_on D4` 判为执行序软依赖并解除（代码核验 streaming 接缝与 engine 选型正交）；**关键前提修正=平台无 SSE**（grep 零命中，真实先例=TaskStore submit→poll）。
- design 方案 A=OCR 任务化（`POST/GET /ocr/jobs` + 部分结果轮询），SSE 否决留流式二期；粒度自适应 native/VLM 页级、cloud 文件级。
- critic round1 NEEDS_REVISION（F1 P0 TaskStore 无增量落点 / F2 FITZ_LOCK 临界区 / F3 缓存绕过 + 3P2）→ Round2 应答 **units.jsonl 边车**（job case_dir 内 per-job lock append，TaskStore("ocr_jobs") 独立表 + progress_message 存 {done,total} JSON，不改共享 schema）+ buffer-then-fire 锁外回调 + 缓存补事件 + 0 单元 completed / 未知 404 / recover_stale 保留 partial → round2 APPROVE-WITH-CHANGES（F1-F6 全 RESOLVED；G1 units.jsonl 入 `_OCR_EXCLUDED_FILENAMES` 防重扫；G2 progress 格式钉死 + 路径服务端派生）。

### impl T1-T5（逐任务 worktree + 主 agent 独立验）
- T1 pipeline 回调接缝（buffer-then-fire 锁外 / F3 缓存补事件 / G1 排除）— merge ebf9113。
- T2+T3 `/ocr/jobs` 端点 + job worker（units.jsonl per-job lock append / progress 锁内单调 / G2 路径派生+404 / F4-F5 边界）— merge f36f537。
- T4 前端：第一版把工作台回填替换成流式 → **用户拍板保留回填**→ 改为 Tabs 双模式（A 识别+回填 / B 流式识别，mode-state.ts reducer 跨模式隔离）— merge 3539392。
- T5 全量回归：后端 952 + 前端 121 绿。

### review（pass1 REWORK → 修 → pass2 PASS）
- **pass1**：独立 reviewer 对抗审查发现 **P0 F1**——流式回调在 native→OCR 回退路径（font-only 扫描 PDF / 混合 PDF 子集增强/整份回退）产生重复或过期页级单元，直接打击内容保真承诺，且无测试覆盖。spec-compliance 侧 PASS（1 minor D1）。主 agent 读码独立确认 F1 真实。
- **F1 修复**（merge 176e91c）：`_dispatch_native_pdf_text` 抽出；native 改 `_call_native_read(path, None)` 不即时流；`_emit_pages_from_blocks` 从最终/augmented blocks 发一次（页锚 enumerate start=1 与 _render_body 一致）。+ F2 三回归用例（RED 证据 [1,2,1,2]/空白/[1,2,3,1,2,3]）。955 passed。
- **pass2 PASS**：独立子 agent 因用户断网中断不可恢复 → 主 agent 亲自复审（透明记录），逐路径确认 F1 解决、无新 P0/P1，2 个 P2 留 polish。

### polish
- P2-a：`_extract_one_raw` docstring 过时描述更正。
- P2-b：`read_pdf_text.on_page` F1 修复后被生产路径旁路 → 保留 + 文档化 defer（critic-F2 安全实现，native streaming 二期再定；移除级联触及多函数+测试，收益不抵）。
- security/doc 扫描净；ARCHITECTURE.md 新增「OCR 流式任务层（D9）」。commit 3d80836。

### 交接（唯一剩 runtime-verify）
- 用户 GO=先 ship 跳本机实跑 → 细化为**用户 mac mini 亲自部署实跑 + codex 规整日志回传**作 runtime-verify 证据。
- 交接单 `runtime-verify-handoff.md`（实跑 5 点 + 需回传的 units.jsonl/日志）。回传后主 agent 写 runtime-verify.md → 达标完成 ship 契约 + roadmap D9→done + **fable5 全局扫描代码+.ai_state**（用户约定收尾）。
- 全部 merge+push origin（至 932437e），worktree/分支全清仅 main。

## 关键决策（本会话产出）
- `compound/2026-07-20-decision-ocr-as-standalone-service.md`：**OCR 路由拆独立服务倾向**（直读+路由+模型池内聚，本项目只调一个 API；重定义 D4，待 D4 窗口确认）。

## 过程教训（本会话）
- **cwd 污染**：`cd` 进 agent-front（有独立嵌套 .ai_state，stage=ship 老状态）后未切回 → delivery-gate 顺 cwd 读到错误 _index 误跑 ship 校验。修复=切回主项目根；后续 worktree 内跑命令改用 `(cd … && …)` 子 shell 不留持久 cwd。
- **红区 worktree 强制**：System 路径写文件的 subagent 缺 `isolation: worktree` 被 PreToolUse hook BLOCK；补 isolation 即过。
