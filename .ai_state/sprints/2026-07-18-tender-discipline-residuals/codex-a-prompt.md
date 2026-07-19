你在隔离 git worktree（分支 `d11-batch-a`）里工作。任务：实现 D11 **Batch A · R4 ocr-page 安全硬化 + 接线**，严格 TDD、fail-closed。**只改本 worktree，绝不 push/碰 main。安全敏感轮（RCE + 跨案读取面），宁可只交硬化本体也不接假接线。**（上一轮你在 TA0 正确 fail-closed 停下——本 prompt v2 已修正命令形态与锚点，采用真实语法。）

## 环境准备（第一步）
- 先 `uv sync --extra ocr` populate 本 worktree 的 `.venv`（**别**跑纯 `uv sync`，会卸 pypdf/openpyxl/docx）。之后可读 worktree `.venv` 里的 SDK 源码、跑 pytest。
- SDK 源码位置：`.venv/lib/python3.14/site-packages/claude_agent_sdk/`（types.py / _internal/）。

## 真实事实（已核，直接用；与旧 design.md 冲突以此为准）
- **ocr-page 真实命令形态**（`.claude/skills/ocr-page/SKILL.md:18` + `ocr.py:46-51`）：
  `uv run python .claude/skills/ocr-page/ocr.py <文件路径> [--pages N-M] [--seal]`
  - `<文件路径>`=**评标目录里真实文件的绝对路径**（是绝对路径，合法；围栏靠"realpath 落在 case_root 子树内"，**不是**拒绝绝对路径）。
  - `--pages`=可选，`N` 或 `N-M`（正整数，见 `ocr.py:_slice_pages` 正则 `(\d+)(?:-(\d+))?`）；缺省=整份。
  - `--seal`=可选布尔 flag。
  - ocr.py 只读、失败非 0 退出。
- **SDK hook API**（claude_agent_sdk v0.2.88，`types.py`）：
  - `ClaudeAgentOptions.hooks: dict[HookEvent, list[HookMatcher]] | None`（:1760）。
  - `HookMatcher`（:585）：`matcher: str`（PreToolUse 下匹配工具名，如 `"Bash"`）+ `hooks: list[HookCallback]` + `timeout`。
  - `HookCallback`（:573）：`async def cb(input: dict, tool_use_id: str | None, context) -> dict`。
  - 返回形状（:412 `PreToolUseHookSpecificOutput`）：`{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny"|"allow", "permissionDecisionReason": "..."}}`。
  - 从 `claude_agent_sdk` import `HookMatcher`（确认确切 import 名，可能在顶层或 types）。
  - PreToolUse hook 回调是**本进程内 Python**（CLI 发 `SDKHookCallbackRequest`→SDK 本地调用，`types.py:1972`）。
- **run_agent_json 实际在 `server/common/json_bridge.py:125`**（不在 agent_bridge）。threading 路径 = `run_tender_evaluation`(runner.py) → `run_command_json`(command_adapter.py) → `run_agent_json`(json_bridge.py) → `run_agent`/`build_options`(agent_bridge.py) → hook 闭包。
- F2 Hotfix：`agent_bridge.py:180-192` `_AGENT_TOOLS` 6 项不含 Bash；build_options 现设 `permission_mode="bypassPermissions"`。

## 任务

### TA0 · 探查 + **bypassPermissions↔hook 经验闸（关键，先做）**
1. 读 `agent_bridge.py`(build_options/run_agent)、`json_bridge.py`(run_agent_json :125)、`command_adapter.py`(run_command_json/build_command_prompt)、`runner.py`(run_tender_evaluation 调用链)、`.claude/skills/ocr-page/{SKILL.md,ocr.py}`、SDK `types.py`（确认 HookMatcher/回调/返回形状 import 与签名）。
2. **经验闸**：写一个最小 async 测试——构造 `ClaudeAgentOptions(permission_mode="bypassPermissions", hooks={"PreToolUse":[HookMatcher(matcher="Bash", hooks=[deny_cb])]})`，用 SDK 跑一个平凡 Bash 工具调用，**断言该 Bash 被 deny 拦下**（deny_cb 恒返回 deny）。
   - **若 deny 在 bypassPermissions 下生效** → hook 是真闸，继续 TA1-TA4。
   - **若 hook 在 bypassPermissions 下不触发** → **停下如实报告**（这决定 Batch A 可行性；不要硬写一个永不触发的闸）。我会据此改 gated 路径的 permission_mode。
3. 若命令形态/SDK 签名与上述不符 → 停下报告，不硬接。

### TA1 · case-root 数据通道（critic F1, P0）
`directory_path` 当前只拼进 prompt 文本，build_options cwd 恒 PROJECT_ROOT → 围栏无数据。
- 加**可选** kwarg `case_root: Path | None = None`，从 `run_tender_evaluation → run_command_json → run_agent_json → run_agent/build_options → hook 闭包` 显式透传，默认 None。
- **audit/expense 零影响**：kwarg 可选默认 None，不传即行为不变——必须有 audit/expense 现有测试全绿作回归证明。
- build_options 收到非 None case_root 才注册 PreToolUse hook 闭包（闭包捕获 case_root）。

### TA2 · PreToolUse 白名单闸（critic F3, anchored；用真实语法）
- hook 回调对完整 Bash `command` 串做 **`re.fullmatch`**（整条锚定，非子串/黑名单），匹配 ocr-page 真实形态：固定前缀 `uv run python .claude/skills/ocr-page/ocr.py` + 一个文件参数（可带引号，token 内禁 shell 元字符）+ 可选 `--pages <N 或 N-M>` + 可选 `--seal`（flag 顺序两种都接）。任何偏离 → `deny`。
- 从匹配组取 `file`/`pages`，**服务端 Python 硬校验**（不信任 agent 传参）：
  - `file`：`os.path.realpath` 解析后**必须落 `case_root` 子树内**（`Path.is_relative_to` 或 realpath 前缀比对；防 `../` 穿越 / symlink 逃逸 / 跨案路径 / case_root 外的绝对路径）。**绝对路径若在 case_root 内=合法**。
  - `pages`（若有）：`\d+(-\d+)?` 且 lo≤hi、正整数、拒溢出。
  - 显式二次拒 shell 元字符（`; & | $ ` ( ) { } < >` 换行）。
  - 通过 → `allow`；否则 `deny`（附原因）。
- **"Bash" 受控加回**工具面（`tools`）使模型能发起 ocr-page 调用，但只有过闸形态放行。加回**仅限 case_root 接线路径**，不放宽 audit/其它路径既有白名单。

### TA3 · 对抗验证（TDD 红先行，fail-closed 核心）— `tests/test_ocr_page_security.py`
全部断言 **deny 且无副作用**：元字符注入（`;rm -rf /`/反引号/`$()`/`|`/`&&`/换行）；**合法前缀+追加恶意**（测 anchored，如 `...ocr.py /case/x.pdf --pages 3; rm -rf /`）；`../` 穿越；**case_root 外绝对路径**（`/etc/passwd`）；**symlink 逃逸**（case_root 内软链指向外部）；**跨案路径**（另一 case dir 文件——必 deny）；pages 负/0/非数字/`3 4`/溢出。**正向 allow 一例**：case_root 内真实文件 + `--pages 7`（+可选 `--seal`）。**端到端可达性断言**（critic F2）：带非 None case_root 的 build_options 里 Bash 确在 tools 面、过闸形态 allow、其余 deny——不要只测纯函数。

### TA4 · 接线（仅当 TA0 经验闸通过 + TA3 全绿）
`.claude/skills/tender-eval` 文档补「底稿页读不清 → 调 ocr-page 重识别 → 用重识别文本再判分」；重识别文本进上下文保留【第N页】页锚。**fail-closed**：TA0 经验闸未过或 TA3 任一失败 = **不接线**，只交 TA1/TA2 硬化本体，如实记录原因。

## 规范 + 产出
- DRY/SRP，函数 ≤40 行；hook 闭包/校验加 type hints + docstring；信任边界 fail-fast。
- 测试 `uv run pytest -q tests/test_ocr_page_security.py`（+ agent_bridge/tender 回归）。lint `uv run ruff check .`。
- **只改**：`server/common/agent_bridge.py`、`server/common/json_bridge.py`、`server/common/command_adapter.py`、`server/tender/runner.py`、`.claude/skills/tender-eval/*`、`tests/test_ocr_page_security.py`（+必要 tender 测试回归）。**不改** output.py/config.py/schema（Batch B 并行在改）。
- 每任务单独 commit（`feat(security):`/`fix(security):`），不 push。
- 结论写明：TA0 探查发现 + **bypassPermissions 经验闸结果**、每 commit SHA+message、对抗测试逐条结果、是否接线（TA4）或只交硬化本体+原因、任何 blocked。
- **遇不符/无法诚实过对抗测试：停下报告，绝不编造测试/放宽断言。**
