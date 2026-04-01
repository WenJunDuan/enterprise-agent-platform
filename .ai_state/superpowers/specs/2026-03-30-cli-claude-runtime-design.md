# CLI Claude Runtime Design

## Goal

让 Python CLI 进程稳定读取项目根 `.env`，将本地 `MODEL_*` 配置映射为 Claude SDK/CLI 可识别的 `ANTHROPIC_*` 环境变量，并通过 `server.cli ask` 进入真实模型调用链。

## Scope

本轮只收口 CLI 运行面，不处理 HTTP serve、`/audit`、extractor、rules 或 hook 阻塞行为。

涉及文件：

- `server/platform/config.py`
- `server/core.py`
- `server/cli.py`
- `.env.example`
- `README.md`
- 视需要小改 `server/platform/diagnostics.py`

不涉及：

- `server/api.py`
- `.claude/hooks/review-output.py`
- `.claude/commands/audit.md`
- `expense-audit` 相关 skill 和规则文件

## Current Problems

1. 映射逻辑存在，但调用前没有强校验。
2. `build_options()` 直接读环境变量，缺少一层“已解析 runtime config”。
3. CLI 没有轻量级的运行时可见性入口，用户无法直接确认当前生效的是哪个网关地址和模型。
4. `.env.example` 与 README 解释了映射机制，但没有以 CLI 为中心说明最小必填项和排错顺序。

## Design

### 1. 配置层收口

在 `server/platform/config.py` 中收敛成三类函数：

- 加载与映射：
  - 负责 `.env` 加载
  - 负责 `MODEL_* -> ANTHROPIC_*`
- 解析与快照：
  - 生成脱敏后的 runtime snapshot
  - 暴露当前主模型、默认 sonnet/opus/haiku 映射和 review model
- 校验：
  - 对 CLI 调模型所需的最小字段做校验
  - 输出结构化错误，而不是延迟到 SDK 深层失败

### 2. 运行时优先级

优先级规则定为：

1. 显式 `ANTHROPIC_*`
2. 由 `MODEL_*` 映射出的 `ANTHROPIC_*`
3. 默认值

细项：

- `ANTHROPIC_BASE_URL` 优先于 `MODEL_BASE_URL`
- `ANTHROPIC_API_KEY` 优先于 `MODEL_API_KEY`
- `ANTHROPIC_AUTH_TOKEN` 优先于 `MODEL_AUTH_TOKEN`，若两者都缺则回退 `MODEL_API_KEY`
- `ANTHROPIC_MODEL` 优先于 `MODEL_NAME` 推导
- `MODEL_NAME` 为非原生 Claude 模型时：
  - `ANTHROPIC_MODEL=sonnet`
  - `ANTHROPIC_DEFAULT_SONNET_MODEL / OPUS / HAIKU = MODEL_NAME`

### 3. Core 层收口

`server/core.py` 不再直接散读 `os.getenv("ANTHROPIC_MODEL", "sonnet")` 作为主路径，而是依赖配置层返回的已解析 runtime config。

目标：

- CLI 调用前拿到一致的 `model/base_url/headers` 视图
- 错误在 CLI 层就可解释
- 后续接回 HTTP 时无需重复逻辑

### 4. CLI 可见性

在 `server/cli.py` 增加一个轻量命令，例如 `runtime` 或 `doctor`，输出：

- `.env` 是否已加载
- 当前生效的 `anthropic_base_url`
- 当前生效的 `anthropic_model`
- 当前默认映射的 sonnet / opus / haiku 模型
- 当前 `second_review_model`
- 缺失项列表

`ask` 在执行前走同一套 runtime 校验。若配置缺失，应直接报可读错误：

- 缺网关地址
- 缺 API key / auth token
- 缺模型名
- `TENANT_KEYS` JSON 非法

### 5. 用户使用口径

用户侧最小使用组合为：

```env
MODEL_BASE_URL=...
MODEL_API_KEY=...
MODEL_NAME=...
```

可选：

```env
MODEL_AUTH_TOKEN=...
MODEL_CUSTOM_HEADERS=...
SECOND_REVIEW_MODEL=...
```

## Acceptance

本轮验收只看 CLI：

1. Python 进程能吃到 `.env`
2. `server.cli ask` 调用前能正确完成 runtime 映射
3. 配置错误时 CLI 能明确给出缺失项或非法项
4. 用户可通过 CLI runtime/doctor 输出确认当前实际模型配置

## Risks

1. 当前 HTTP 与 hook 还没一并收口，后续接回时仍需复用同一配置层。
2. 如果实际网关要求特殊 header 组合，`MODEL_CUSTOM_HEADERS` 的归一化逻辑必须保守，不能破坏原格式。
3. 如果用户同时设置 `ANTHROPIC_*` 与 `MODEL_*`，必须在输出里清楚体现最终生效来源，避免误判。
