# LiteLLM 协议翻译层

让审核平台经一层 LiteLLM 代理跑 Qwen（或其他非 Anthropic 模型），同时保持 Claude Code/SDK 看到的是 Claude 模型名。解决两件事：

1. **工具调用透传**：LiteLLM 在 Anthropic ↔ OpenAI 协议间双向翻译 `tool_use`，补上裸网关（如 yunwu）不透传工具调用导致的“0 工具调用 → 编造结果 → max_turns 失败”。
2. **模型名映射**：对外保持 `claude-opus-4-8` 等 Claude 名（让 CLI 的子串能力判定走完整 opus 档），实际打到 Qwen。

## 快速开始

```bash
# 1. 安装（⚠️ 见下方安全警告，务必避开被投毒的版本）
pip install "litellm[proxy]==<安全版本>"

# 2. 准备环境变量
cp deploy/litellm/.env.example deploy/litellm/.env
#   编辑 .env，填 QWEN_API_BASE / QWEN_API_KEY / LITELLM_MASTER_KEY

# 3. 起代理（默认 4000 端口）
set -a && . deploy/litellm/.env && set +a
litellm --config deploy/litellm/litellm_config.yaml --port 4000
```

## 接入审核平台（改主项目根目录的 .env）

```dotenv
MODEL_BASE_URL=http://127.0.0.1:4000
MODEL_AUTH_TOKEN=<与 LITELLM_MASTER_KEY 相同>
MODEL_NAME=claude-opus-4-8
# 关键：Claude Code 每个请求都带 Anthropic beta 头，非 Anthropic 后端常 400 拒掉，置 1 剥掉。
CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1
```

改完重启后端：`uv run python -m server.cli serve`。

## 验证工具调用是否真的通了

切到 LiteLLM 后第一件事就是验证 `tool_use` 透传（这是整套方案能不能成立的前提）：

```bash
uv run python -m server.cli ask "用 Read 工具读取 README.md，并只回答它的第一行"
# 看最新 session 日志里 tool_call 事件数，≥1 说明工具调用透传成功：
ls -t logs/sessions/events/*/*/*/*.jsonl | head -1 | xargs grep -c '"event": "tool_call"'
```

若仍为 0，说明后端/配置没把工具调用传通，先排查 LiteLLM 与 Qwen 的 function calling 再继续。

## 配置说明

`litellm_config.yaml` 的 `model_list` 中：

- `model_name`：Claude Code/SDK 请求的名字（保持 Claude 名）。
- `litellm_params.model`：实际转发的真实模型（`openai/qwen-*` 走 Qwen 的 OpenAI 兼容端点）。
- `"*"` 兜底条目：CLI 内部偶尔请求未显式列出的 Claude 名，避免 `model not found`。

按账号可用的 Qwen 模型调整三档映射即可。

## ⚠️ 安全警告

- **LiteLLM 的 PyPI `1.82.7` / `1.82.8` 被植入窃取凭证的恶意代码（Claude Code 官方文档点名）。务必避开这两个版本**；安装前去 PyPI 核对当前安全版本号。
- `LITELLM_MASTER_KEY` 与 `QWEN_API_KEY` 只放 `.env`，不要提交（本目录 `.env` 已被根 `.gitignore` 忽略）。

## 已知风险

LiteLLM 解决的是“协议透传”，工具调用的**质量**仍取决于后端模型。社区反馈 Qwen 在复杂工具链上不如 Claude 稳，而审核要连续 `Read + Glob + StructuredOutput`——尤其 StructuredOutput 那步是最大变量，务必先用上面的探针验证。
