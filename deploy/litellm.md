# LiteLLM 网关配置

> litellm 是 audit-agent 与实际推理模型之间的网关：把 SDK/CLI 请求的 **`claude-*` 模型名**
> 翻译/路由到真正的上游（云 dashscope qwen / 本地 vLLM qwen / deepseek 等）。
> audit-agent 通过 `MODEL_BASE_URL=http://litellm:4000` 接它。
>
> ⚠️ 本文不写任何 api_key / token 明文 —— 凭据只在 `litellm_config.yaml` 里。

## 一、运维位置

- **dev**：容器 `ea-litellm`（镜像 `docker.litellm.ai/berriai/litellm`），配置挂载自
  `/opt/application/litellm/litellm_config.yaml`，compose 在 `/opt/application/litellm/`。
- **改配置后必须重启**：`docker restart ea-litellm`（配置在进程启动时读入）。
- litellm 独立运维，**不在 audit-agent 仓库**。

## 二、配置结构

```yaml
model_list:
  - model_name: claude-opus-4-8            # ← audit-agent 的 MODEL_NAME 请求的名字
    litellm_params:
      model: dashscope/qwen3.6-27b         # 上游真实模型 (provider/model)
      api_base: https://dashscope.aliyuncs.com/compatible-mode/v1
      api_key: <见配置文件, 勿外泄>
  - model_name: claude-opus-4-6
    litellm_params:
      model: openai/Qwen3.6-27B            # 本地 vLLM (served-model-name 必须对得上)
      api_base: http://qwen36-27b:8000/v1  # 容器名 + 容器内部端口
litellm_settings:
  drop_params: true                        # 丢弃上游不认的参数
  num_retries: 2
```

**命名约定**：audit-agent 的 `MODEL_NAME`（在 `audit-agent.env`）必须等于 litellm 里的某个
`model_name`，否则 `model not found`。本项目复用 `claude-*` 名让 SDK 以为在调 Claude。

## 三、关键规则（踩过的坑，务必遵守）

### 1. 一个 model_name 只能有一条 ⚠️最隐蔽
同名定义多条 → litellm 当**负载均衡组随机路由**到不同上游 → 审核**时好时坏**（跳到限制紧的上游就失败）。
排查：`curl http://<litellm>:4000/v1/models` 看有无重名 + 逐条核 api_base。

### 2. api_base 必须是「litellm 容器能到」的地址
- ❌ `http://127.0.0.1:xxxx` —— 容器内 127.0.0.1 = 容器自己，到不了宿主机/别的容器。
- ✅ 同 docker 网络：**容器名 + 容器内部端口**（如 `http://qwen36-27b:8000/v1`，注意不是宿主映射端口 8082）。需先 `docker network connect <net> <上游容器>`。
- ✅ 或宿主机 LAN IP + 宿主映射端口。
- scheme 用 **http**（vLLM/dashscope-compatible 是明文；写 https 会 SSL 握手失败）。

### 3. served-model-name 要对得上（本地 vLLM）
vLLM 启动 `--served-model-name X`，则 litellm 的 `model:` 必须是 `openai/X`，否则 vLLM 404。

### 4. 关 thinking（治"输出无 JSON / 空 explanation"）
推理模型在文本模式下爱长篇 reasoning、不收尾成 JSON（见 TROUBLESHOOTING E1）。**关掉 thinking 让它直出答案**：
- **本地 vLLM**：启动参数 `--default-chat-template-kwargs '{"enable_thinking": false}'`（内网 prod 已这么配）。
- **云 dashscope**：在该 model 的 `litellm_params` 里传 `enable_thinking:false`（dashscope qwen3 支持该请求参数；litellm 经 `extra_body` 透传，具体写法以实测为准）。
- 关 thinking 后再配合 `AUDIT_CONTRACT_MAX_RETRY` 兜偶发。

## 四、测试 / 排查命令

```bash
LH=http://<litellm-host>:4000
# 暴露的模型 (看有无重名)
curl -s $LH/v1/models
# 直连上游测 (OpenAI 格式)，确认某 model_name 通
curl -s $LH/v1/chat/completions -H 'Authorization: Bearer <litellm-key>' \
  -H 'Content-Type: application/json' \
  -d '{"model":"claude-opus-4-8","messages":[{"role":"user","content":"ping"}],"max_tokens":32}'
# SDK 同款 (Anthropic 格式, audit-agent 实际走这条)
curl -s "$LH/v1/messages?beta=true" -H 'Authorization: Bearer <litellm-key>' \
  -H 'anthropic-version: 2023-06-01' -H 'Content-Type: application/json' \
  -d '{"model":"claude-opus-4-8","max_tokens":256,"messages":[{"role":"user","content":"ping"}]}'
# 从 litellm 容器内测能否到上游 (验 api_base 可达)
docker exec ea-litellm python -c "import urllib.request as u;print(u.urlopen('http://qwen36-27b:8000/v1/models',timeout=5).read()[:80])"
```

## 五、改配置标准流程

1. 备份：`cp -a litellm_config.yaml litellm_config.yaml.bak.$(date +%Y%m%d-%H%M%S)`
2. 改 `litellm_config.yaml`（注意上面 4 条规则）
3. `docker restart ea-litellm`，等 ~20s（healthcheck start_period）
4. `curl $LH/v1/models` 确认 + 跑一次端到端审核验证
