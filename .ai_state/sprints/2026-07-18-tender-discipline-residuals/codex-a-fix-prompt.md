你在 git worktree（分支 `d11-batch-a` @ 9dee52a）继续。D11 Batch A 的**围栏逻辑已通过两轮独立对抗 review（~20+ payload 无绕过，CLEAN）——不要改它**。仅剩 1 P0 + 1 P1，本轮**只做这两件**：

## 背景
Batch A 给评标 agent 受控加回 Bash（仅放行 ocr-page 命令），靠 `build_options` 注册的 PreToolUse deny-hook 把关；`runner.py` 让 `case_root` 对每次评标恒非 None → Bash 对所有评标恒开（受 hook 约束）。
- **P0（F1）**：围栏基石假设——`permission_mode="bypassPermissions"` 下 PreToolUse `deny` 是否真的拦住 Bash——**本 diff 零测试证据**，两 reviewer + 静态读 SDK 都无法确证（判定在打包 Node CLI 二进制里）。若假设错，Bash = 每次评标全开的 RCE 面。spec 的 TA0 明确要求一条真 `query()` 集成测试证实，未做即接线=违约。

## 任务 1（F1, P0）· 真 query() 集成测试锁死 linchpin — 新文件 `tests/test_ocr_page_hook_integration.py`
- **Test A（linchpin，必须）**：构造 `ClaudeAgentOptions(permission_mode="bypassPermissions", ...)`，tools 含 Bash，注册 PreToolUse hook（matcher="Bash"）——该 hook **记录被调用次数**并**恒返回 deny**。用 `claude_agent_sdk.query()` 发**强诱导单次 Bash 调用**的 prompt（严格要求"调用 Bash 工具一次，command 恰为 `touch <tmp_marker>`，然后停止"）。断言：
  - hook 被调用次数 ≥ 1（证明工具调用确实发生 + hook 确实被咨询——**若为 0**=模型没调 Bash，测试**不可判定**，应加强 prompt 或 `pytest.skip("model did not emit Bash tool call")`，**绝不能**让"模型没调=marker 没建"伪装成通过）；
  - `tmp_marker` **未被创建**（deny 真拦住执行）。
  - 两条同时成立 = bypassPermissions 下 deny 真生效。
- **Test B（生产路径，尽量做）**：`build_options(case_root=<tmp case dir>)`（真实 ocr-page hook）+ `query()` 诱导**非 ocr-page** Bash（`touch <marker>`），断言 marker 未创建（真实 hook 生产形态 deny）。
- **网关不可达优雅 skip**：捕获连接错误/缺 env/CLI 不可用 → `pytest.skip`（标 integration，别让无网关机器/CI 挂）。**别 mock CLI**（要测真 CLI 行为）。
- **本轮务必真跑一次**（你有网关），结论写进最终报告：hook 调用次数、marker 是否创建、bypassPermissions 下 deny 是否生效——**要真实运行结果，不要只声称**。

## 任务 2（F2, P1）· 显式记录"Bash 对全部评标恒开"是有意决策
`server/tender/runner.py` 的 `evaluation_case_root = case_root if case_root is not None else Path(directory_path)` 处加注释：case_root 恒为本案目录 → 受 ocr-page hook 约束的 Bash 对**每次**评标可用（TA4：任一评标都可能需低清页 ocr-page 重识别），hook 是唯一闸；有意设计，非默认参数副作用。

## 约束 + 产出
- **只改**：新增 `tests/test_ocr_page_hook_integration.py` + `runner.py` 注释。**不动**围栏校验逻辑（`agent_bridge` 的 `_validate_*`/正则/hook——已 CLEAN）。
- 单独 commit（`test(security):` / `docs(security):`），不 push，不碰 main。缺依赖 `uv sync --extra ocr`。lint `uv run ruff check .`。
- 最终报告：**Test A/B 真实运行结果（linchpin 结论）** + commit SHA + 无网关时是否正确 skip。
- **若真跑发现 bypassPermissions 下 deny 不生效（marker 被创建）→ 立即停下如实报告，这是 P0 安全事故（围栏形同虚设），不要掩盖。**
