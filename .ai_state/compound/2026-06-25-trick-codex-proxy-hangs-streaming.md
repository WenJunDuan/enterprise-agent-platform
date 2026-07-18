# Trick — codex exec 被 HTTP(S)_PROXY 挂起 streaming responses API

> doc_type: trick · 2026-06-25 · 适用：本机/本仓库用 `codex exec` 派活

## 症状

`codex exec` 派发后**长时间零进展**：进程活着但 CPU 近 0（47min 仅 ~8s CPU），
只读了几个文件就卡住，日志反复刷
`ERROR codex_models_manager::manager: failed to refresh available models: timeout waiting for child process to exit`
（每 ~3min 一条），无任何 `apply_patch` / 测试执行。

## 误导项

`codex doctor` 全绿（17 ok · 0 fail），`reachability ... ChatGPT base URL https://chatgpt.com/backend-api/ reachable (HTTP 403)`。
**doctor 的可达性探测是普通 HTTP 请求，能过；但实际推理走的是 streaming `responses` wire API，会被代理掐住。**
所以"doctor 通过"≠"能跑"。

## 根因

环境里设了 `HTTP_PROXY` / `HTTPS_PROXY`（本机常因 litellm/科学上网常驻）。
代理放行普通 GET，却**挂起 streaming 长连接**（responses API）。与历史 litellm 同名路由 / NO_PROXY 问题同源。

## 定位手法（30s 内确诊）

```bash
# 带代理：卡死无输出
printf 'Reply with exactly one word: PONG' | codex exec -s read-only -c model_reasoning_effort="low" -
# 去代理：秒回 PONG → 确诊是代理
printf 'Reply with exactly one word: PONG' | env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  codex exec -s read-only -c model_reasoning_effort="low" -
```

## 修复 / 标准派发姿势

派 codex 干活一律 **bypass 代理**：

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
  codex exec --dangerously-bypass-approvals-and-sandbox -C <repo> - < task.md
```

## 2026-07-18 增补 · anthropic SDK 直连同坑(第三例, SOCKS 变体)

D10①直连 spike:`anthropic` python SDK 构造 client 时直接 ImportError 崩——本机代理是
**SOCKS**(`ALL_PROXY` 等),httpx 需 `socksio` 包才肯走 SOCKS,缺则拒绝启动(比挂起好:fail-fast)。
网关是国内 deepseek 端点本就不需代理。修法同款:

```bash
env -u ALL_PROXY -u HTTPS_PROXY -u HTTP_PROXY -u all_proxy -u https_proxy -u http_proxy \
  uv run --with anthropic python <script>
```

**产品化直连(D10 实施)必须代码内免疫**:构造 client 用 `http_client=DefaultHttpxClient(trust_env=False)`
之类显式关代理继承,不能依赖调用方 shell 环境;部署机网络形态需在 runbook 单独核对。

## 旁注

- `~/.codex/hooks.json` 有非致命 parse warning：`unknown field _comment_athena`（codex 只认 `hooks` 键）。不阻断，但该删掉那个注释字段。
- 排查 codex 卡死：先看进程 CPU 时间（近 0 = 阻塞在网络，不是在算）+ 日志有无 `apply_patch`/测试执行，别干等。
