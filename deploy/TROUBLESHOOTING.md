# 部署 / 运行踩坑记录

> 按"症状 → 真因 → 解法"组织。新坑往这里追加，方便下次秒定位。
> 凭据/IP 等敏感值不在此文写明文。

---

## A. 网关与模型路由

### A1. 审核"时好时坏" / 偶发 400 或 exit 1（最隐蔽）
- **症状**：同样的请求，有时成功有时失败，无规律。
- **真因**：**litellm 配置里同一个 `model_name` 定义了两次**（指向不同上游，如一条云 dashscope、一条本地 vLLM），litellm 当负载均衡组**随机路由**。跳到限制紧的那个上游就失败。
- **解法**：`curl litellm:4000/v1/models` 看有无重名；`litellm_config.yaml` 里**一个 model_name 只留一条**，重名的改名。改后 `docker restart ea-litellm`。

### A2. `400 ... requested 64000 output tokens ... context length only 65536`
- **真因**：Claude CLI **默认请求 64000 output token**（写死在 CLI，项目代码/配置里没有），本地 vLLM `--max-model-len 65536` 装不下 `输入+64000`。
- **解法**：`audit-agent.env` 设 `CLAUDE_CODE_MAX_OUTPUT_TOKENS=16000`（本地 65536 模型必设）。大上下文云模型（256K）不受影响。改后 `up -d --force-recreate`。

### A3. litellm 连不上上游 `Cannot connect to host 127.0.0.1:xxxx`
- **真因**：litellm 在容器里，`127.0.0.1` 指**容器自身**，不是宿主机/别的容器。
- **解法**：上游用**宿主机 LAN IP**（如 `http://<宿主IP>:8082/v1`）或把上游容器接到同一 docker 网络后用**容器名 + 容器内部端口**（注意不是宿主映射端口）。`docker network connect <net> <container>`。

### A4. litellm `AnthropicResponse ValidationError` / 上游用 https 失败
- **真因**：上游 `api_base` 写了 `https://` 但 vLLM 是明文 http；或上游返回的 reasoning/tool_calls 字段 litellm 翻译成 Anthropic 格式时崩。
- **解法**：`api_base` 用 `http://`；上游开了 `--reasoning-parser`/`--enable-auto-tool-choice` 时，文本模式审核易出畸形响应 → 见 E 区。

---

## B. 容器 / 网络 / 镜像

### B1. 改了代码但容器行为没变
- **真因**：`server/` `.claude/` `agent-front/dist` **烤进镜像**，不重建不生效（`knowledge/`/`data/`/`logs/` 才是挂载）。
- **解法**：`docker compose build` 重建（必 bump 镜像标签）。规则文件改动则同步到挂载的 `knowledge/`。

### B2. `MODEL_BASE_URL` 没进容器 → CLI 退回 `api.anthropic.com`（内网 ConnectionRefused）
- **诊断**：`docker exec audit-agent python -m server.cli runtime` 看 `anthropic_base_url`（空或指向 anthropic = 在拨公网）。
- **真因**：env 没真正进容器（env_file 没生效 / 没 recreate）。
- **解法**：`audit-agent.env` 设 `MODEL_BASE_URL=http://litellm:4000`，`up -d --force-recreate`。代码已硬约束：base_url 空/指向 anthropic 时直接报错（`ALLOW_ANTHROPIC_API=1` 解除）。

### B3. `env_file ... Additional property format is not allowed`（compose 版本）
- **真因**：compose **< v2.30** 不认 `env_file` 的 `format: raw`（demo 是 v2.27.1）。`path:`/`required:` 需 v2.24+。
- **解法**：该机 `docker-compose.yml` 里**删掉 `format: raw` 一行**（保留 `path:`/`required:`，或退回短格式 `- ./audit-agent.env`）。删后跑 `docker exec audit-agent printenv TENANT_KEYS` 确认 JSON 没被弄坏（应是完整 `{"default":"..."}`）。

### B4. mac mini 大文件招投标上传失败，但小文件正常
- **症状**：前端提示"请求失败，请稍后重试"；nginx/access 看到
  `POST /tender/projects/<id>/evaluate` 返回 400；后端没有生成 `tender_tasks`，
  `data/submissions/default/tender/` 也没有落文件。
- **后端特征**：异常发生在 `request.form()` 解析 multipart 阶段，日志含
  `starlette.requests.ClientDisconnect`。这表示上传流在识别/评标前断开，不是模型识别逻辑失败。
- **cloudflared 特征**：同一时间有 `Incoming request ended abruptly: context canceled`，目标为
  `https://agent.guoker.org/tender/projects/<id>/evaluate`。
- **真因**：公网 `cloudflared-mesh` 链路对大 body 上传不稳定或触发 Cloudflare 请求体限制。Cloudflare 官方
  `413 Payload Too Large` 文档列出 Free/Pro 100MB、Business 200MB、Enterprise 500MB+ 的上传上限：
  https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-413/
  前端 nginx / 后端路由可用，小文件同路径成功时尤其能确认问题在上传链路。
- **解法**：
  1. mac mini 前端 nginx 保持 `client_max_body_size 512m`、`client_body_timeout 600s`、
     `proxy_send_timeout 600s`、`proxy_read_timeout 1200s`、`proxy_request_buffering off`。
  2. 后端 env 保持 `MAX_UPLOAD_FILE_BYTES=536870912`（512MiB），与 nginx 对齐；改后重建/重启
     `agent-backend`。
  3. 用户无法拆文件时，优先绕过 Cloudflare：本机开
     `ssh -fN -o ExitOnForwardFailure=yes -L 15173:127.0.0.1:5173 macmini`，然后访问
     `http://127.0.0.1:15173/contracts/tender-review` 上传。
  4. 验证是否真正进入评标：`tender_tasks` 应出现 `accepted/running/completed`，上传目录应有 PDF 文件；
     如果只有 `tender_projects` 没有 task，就是还没进入识别。

### B5. Apple `container run --network ... hostname=...` 报错
- **症状**：重建 mac mini 容器时报 `unknown network property 'hostname'. Available properties: mac, mtu`。
- **真因**：Apple `container` 的 `--network` 参数不是 Docker run 语义，目前不接受 `hostname` 属性。
- **解法**：使用 `--network default,mtu=1280`，容器名用 `--name agent-backend` / `--name agent-front` 固定即可。

---

## C. SSH / 跳板

### C1. SSH `Permission denied`，之前还好好的
- **真因**：短时间反复**密码**登录触发 OpenSSH `PerSourcePenalties` / fail2ban，按源 IP 临时封禁（连密钥认证也一起封）。
- **解法**：① 装公钥走密钥认证（不再触发密码惩罚）；② 等冷却；③ 用 SSH ControlMaster 连接复用减少新建连接。

### C2. 连 demo（10.200.52.4）
- demo 只能经 **mac mini 跳板**：`ssh -J macmini -i ~/.ssh/njsr-app01_ed25519 root@10.200.52.4`。
- 用户是 **root**（不是 key 注释里的 codex）。`macmini` 在 `~/.ssh/config` 里定义。

### C3. zsh 下 `$SSHOPT` 变量被当成单个参数
- **真因**：zsh 默认不对未加引号的变量做分词。
- **解法**：ssh 选项**直接 inline 写**，别塞进变量；或用 `${=VAR}` 强制分词。

---

## D. 规则 / 资产校验

### D1. `asset_validation` 报 degraded：`category does not match filename` / `rule_id does not match prefix`
- **真因**：规则文件的 **文件名、`category` 字段、`rule_id` 前缀必须三者一致**。`server/platform/asset_validation.py` 强校验：`category == 文件名(去.rules.json)`，`rule_id` 以 `{domain}_{category}_` 开头。
- **解法**：三者对齐。例：接待规则文件名 `entertainment.rules.json` → `category: entertainment` → `rule_id: expense_entertainment_NNN`（不要文件名叫 reception 而 category 叫 entertainment）。

### D2. 规则文件改了但审核没用上
- **真因**：`knowledge/` 是**挂载目录**，要同步到目标机 `/opt/application/audit-agent/knowledge/`；它被 gitignore，不在镜像/仓库里。
- **说明**：内联 `/audit` 直接 glob `knowledge/expense/*.json` 注入 prompt，**不调用任何 skill**（skill 是旧编排流的废弃脚手架，删了不影响审核）。

---

## E. 模型输出质量（文本模式）

### E1. `audit result field explanation must be non-empty` / `未能从模型输出中解析出 JSON 对象`
- **真因**：文本模式（`AUDIT_STRUCTURED_OUTPUT=0`）下模型输出**有波动**：复杂案子模型长篇 reasoning、**始终没吐出最终 JSON 对象**（或漏填 explanation）。开了 thinking 的模型尤甚。模型分析往往是对的，只是不收尾成 JSON。
- **解法（按推荐）**：
  1. **关模型 thinking**（最对症）：内网 vLLM 用 `--default-chat-template-kwargs '{"enable_thinking": false}'`；云模型在 litellm 侧传等价参数。
  2. 调大 `AUDIT_CONTRACT_MAX_RETRY`（如 3）兜随机波动。
  3. 试 `AUDIT_STRUCTURED_OUTPUT=1`（需 litellm+模型支持 json_schema）。

### E2. CLI 崩 `Command failed with exit code 1 / Check stderr output for details`（黑盒）
- **解法**：代码已加 `_log_cli_stderr`（`server/core.py`）把 CLI stderr 落日志。查 `docker logs audit-agent | grep claude_cli_stderr` 看真因。

### E3. 手动复现审核时 CLI 报 `--dangerously-skip-permissions cannot be used with root`
- **真因**：`docker exec` 默认以 **root** 进容器，Claude CLI 拒绝 root 下跳过权限。真实服务以 `app` 用户（gosu 降权）跑，不受影响。
- **解法**：手动跑加 `-u app`：`docker exec -u app -i audit-agent python - <<'PY' ... PY`。

---

## F. 前端

### F1. 详情页白屏 `Minified React error #31 (object with keys {code,description,severity})`
- **真因**：旧归档结果里 `reasons`/`risk_dimensions` 是对象，前端按字符串/数组渲染对象 → 崩。
- **解法**：① 后端 `enrich_audit_decision` 写入+读取端都归一化（reasons 拍平字符串、risk_dimensions 对象→数组、0-100→0-10）；② 前端 `TaskDetail` 加 `toText`/`normalizeRiskDimensions` 兜底。旧结果免重跑即可渲染。

---

## G. 日志噪音排除特征

这些可以在日志侧先降噪；排除前保留 ERROR、failed、traceback、`status=failed`、`ClientDisconnect`
等异常关键词。

### G1. 后端 `agent-backend`
- 前端轮询任务状态：`INFO: .* "GET /tender/tasks/[0-9a-f-]+ HTTP/1.1" 200 OK`
- 前端轮询项目/结果列表：`INFO: .* "GET /tender/projects.* HTTP/1.1" 200 OK`
- 健康检查：`INFO: .* "GET /health HTTP/1.1" 200 OK`
- 正常启动噪音：`Started server process`、`Waiting for application startup`、
  `Application startup complete`、`Uvicorn running on`
- SDK 正常启动：`Using bundled Claude Code CLI:`
- PyMuPDF 建议提示：`Consider using the pymupdf_layout package`

### G2. 前端 `agent-front` nginx
- 任务状态轮询：`"GET /tender/tasks/[0-9a-f-]+ HTTP/1.1" 200`
- 项目/结果轮询：`"GET /tender/projects.* HTTP/1.1" 200`
- 健康检查：`"GET /health HTTP/1.1" 200`
- 静态资源加载：`"GET /assets/.* HTTP/1.1" 200`、`"GET /images/.* HTTP/1.1" 200`
- SPA 页面缓存命中：`"GET /contracts/tender-review HTTP/1.1" 304`

### G3. `cloudflared-mesh`
- 正常启动/连边缘：`Starting tunnel`、`Registered tunnel connection`、
  `Tunnel connection curve preferences`
- ICMP 能力不足但不影响 HTTP tunnel：`ICMP proxy feature is disabled`、
  `ping_group_range`
- QUIC 不稳但自动降级 HTTP/2：`QUIC connection failed`、
  `Allow outbound QUIC traffic on port 7844 or use HTTP2`、
  `Environment ready with degraded transport`
- 旧 origin 不通的重复噪音：`Unable to reach the origin service.*dial tcp .*:5173: i/o timeout`

不要排除这类上传失败信号，除非已明确改用本地隧道：`Incoming request ended abruptly: context canceled`
且 `dest=https://agent.guoker.org/tender/projects/.*/evaluate`。
