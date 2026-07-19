# trick · codex 0.144.6 headless launch 崩在 multi_agent_v2 配置冲突

**症状**：`codex exec ...` 启动即 exit 1，stdout 只有一行：
```
Error: thread/start: thread/start failed: agents.max_threads cannot be set when features.multi_agent_v2 is enabled (code -32600)
```
（codex-cli 0.144.6；旧版无此校验，故是升级后新暴露的冲突。）

**根因**：`~/.codex/config.toml` 同时有 `[agents] max_threads = 6` 与 `[features.multi_agent_v2]`（table 即 enabled）。0.144.6 拒绝这个组合。config 不能靠 `-c` 单独 unset 一个 key。

**修法**：launch 加 `--disable multi_agent_v2`（= `-c features.multi_agent_v2=false`，覆盖那张 table）。已验证：加后 codex 正常返回（`Reply READY` sanity test 通过）。

**完整 headless 落地形态**（本会话 D11 两 batch 用此并行跑 worktree impl）：
```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  codex exec --disable multi_agent_v2 --skip-git-repo-check \
  -C <worktree_abs_path> \
  --output-last-message <result.md 绝对路径> \
  - < <prompt.md 绝对路径>
```
- `env -u ...PROXY`：剥代理，防 streaming 挂起（同 [[2026-06-25-trick-codex-proxy-hangs-streaming]]）。
- `-C <dir>`：设工作根 = worktree（不用 cd，省 permission 提示）。
- `--output-last-message`：把 codex 最终结论落到指定文件，主 agent 只读它、不碰 JSONL 全 transcript（防 context 溢出）。
- `- < prompt.md`：prompt 从 stdin 读（长中文 prompt 免 shell 转义）。
- config 已是 `approval_policy = "never"` + `sandbox_mode = "danger-full-access"`，故无需再传审批/沙箱 flag；danger-full-access 下务必 worktree 隔离。

**要点**：worktree 从 committed HEAD 拉出，看不到主 repo 里未提交的 `.ai_state` 文件 → 给 codex 的 spec 要么 inline 自包含、要么只引 worktree 里已提交的文件（如 design.md）。worktree 首跑无 `.venv`，需 `uv sync --extra ocr`（**不是**纯 `uv sync`，会卸 pypdf/openpyxl/docx）后才能跑 pytest / 读 SDK 源码。

关联：[[2026-06-25-trick-codex-proxy-hangs-streaming]]
