# 部署指南 (deploy/)

> 企业智能审核平台（audit-agent）部署 / 故障恢复手册。
>
> ⚠️ 本目录只放**文档**；实际 `Dockerfile` / `docker-compose.yml` 在仓库根。
> ⚠️ **不在本目录写任何密钥 / 令牌 / 密码明文** —— 凭据只存各机的 `audit-agent.env` 与
>    `litellm_config.yaml`；SSH 私钥只在本机 `~/.ssh/`，不入库。

## 一、环境一览

| 环境 | 主机 | 用户 | 接入方式 | 备注 |
|---|---|---|---|---|
| **dev 测试** | `100.107.62.19` | admin | `ssh -i ~/.ssh/spark-3d55 admin@100.107.62.19`（tailscale 直连；config 别名 `spark`）| NVIDIA aarch64 |
| **demo 演示** | `10.200.52.4`（njsr-app01）| root | `ssh -J macmini -i ~/.ssh/njsr-app01_ed25519 root@10.200.52.4`（经 mac mini 跳板）| compose **v2.27.1** |
| **mac mini 容器演示** | `macs-mac-mini.tailbf6a2a.ts.net` | mac | config 别名 `macmini`（key `macs_mac_mini_ed25519`）| Apple `container`；同时是 demo 跳板 |
| **prod 内网** | `192.168.1.24`(构建) + 隔离目标机 | — | 物理隔离，离线 tar 搬运 | 内网 qwen3.6 vLLM @ `:8100`（Ascend NPU, 256K ctx, `enable_thinking=false`）|

- **litellm 网关**（dev）：容器 `ea-litellm`，配置 `/opt/application/litellm/litellm_config.yaml`，改后 `docker restart ea-litellm`。
- SSH 用密钥认证，**不要反复用密码**（会触发 OpenSSH PerSourcePenalties / fail2ban 封 IP）。

## 二、约定

- **部署根**：各机 `/opt/application/audit-agent/`
- **镜像标签**：`audit-agent:{月日}{版本}`，如 `0611b1` = 6/11 第 1 版。**更新代码必须 bump 版本号，禁止复用旧标签**（否则版本分不清）。
- **mac mini Apple container 标签**：`agent-backend:{月日}{版本}` / `agent-front:{月日}{版本}`，如 `0621b3`；容器名固定
  `agent-backend` / `agent-front` / `cloudflared-mesh`，不要把长时间戳写进容器名。
- **离线包**：`docker save` → `audit-agent-{tag}.tar` + `audit-agent-{tag}.tar.sha256`

## 三、什么烤进镜像 vs 挂载（决定改完要不要重建）

| 内容 | 方式 | 改完怎么生效 |
|---|---|---|
| `server/`、`.claude/`、`agent-front/dist` | **烤进镜像** | 必须 `docker compose build` 重建 |
| `knowledge/`、`data/`、`logs/` | **volume 挂载** | 同步到挂载目录即可，无需重建 |
| `audit-agent.env`（env_file）| 挂载 | 改后 `docker compose up -d --force-recreate` |

> `knowledge/` 与 `data/` 被 `.gitignore` 忽略（制度源不入库）→ 部署时**单独同步规则文件**，不在镜像/git 里。
> mac mini Apple container 路线使用 `/Users/mac/workspace/enterprise-agent-platform/{knowledge,data,logs}`
> 作为宿主机持久化目录，分别挂到后端容器 `/app/knowledge`、`/app/data`、`/app/logs`。

## 四、部署流程

### A) dev（有源码，本地构建）

```bash
KEY=~/.ssh/spark-3d55; H=admin@100.107.62.19; D=/opt/application/audit-agent
RSH="ssh -i $KEY -o IdentitiesOnly=yes"

# 1) 同步代码 + 配置 + 规则（规则是挂载目录，也要同步）
rsync -rtz --exclude=__pycache__ --exclude=.venv -e "$RSH" server/   $H:$D/server/
rsync -rtz --exclude=settings.local.json          -e "$RSH" .claude/ $H:$D/.claude/
rsync -rtz                                         -e "$RSH" knowledge/expense/ $H:$D/knowledge/expense/
# 删除的文件 rsync 不带 --delete 不会清，手动删（如废弃的 skill 目录）

# 2) bump 镜像标签（compose image: 改成新版本，如 0611b1）
ssh -i $KEY $H "sed -i 's#audit-agent:<旧tag>#audit-agent:<新tag>#' $D/docker-compose.yml"

# 3) 构建 + 重启（依赖层有缓存；pip 下载慢可能要几分钟）
ssh -i $KEY $H "cd $D && docker compose build && docker compose up -d --force-recreate audit-agent"

# 4) 导出离线包 + 删旧镜像（不留备份时）
ssh -i $KEY $H "cd $D && docker save audit-agent:<新tag> -o audit-agent-<新tag>.tar \
  && sha256sum audit-agent-<新tag>.tar > audit-agent-<新tag>.tar.sha256 \
  && docker rmi audit-agent:<旧tag>"
```

### B) demo（物理上只能经跳板，离线 load 镜像）

```bash
KEY=~/.ssh/njsr-app01_ed25519; H=root@10.200.52.4; D=/opt/application/audit-agent
J="-J macmini"   # macmini 在 ~/.ssh/config 里定义

# 1) 传镜像 tar（本机 → demo，经 mac mini 跳板）
scp $J -i $KEY audit-agent-<tag>.tar audit-agent-<tag>.tar.sha256 $H:$D/

# 2) demo 上校验 + load + 起
ssh $J -i $KEY $H "cd $D \
  && sha256sum -c audit-agent-<tag>.tar.sha256 \
  && docker load -i audit-agent-<tag>.tar \
  && sed -i 's#image: audit-agent:.*#image: audit-agent:<tag>#' docker-compose.yml \
  && docker compose up -d --force-recreate"
```

> ⚠️ demo 的 compose 是 **v2.27.1**，不支持 `env_file` 的 `format: raw`（v2.30+ 才有）。
> 仓库 compose 带 `format: raw` → 在 demo 上 **删掉那一行**（保留 `path:` / `required:` 即可）。
> 详见 `TROUBLESHOOTING.md`。

### C) mac mini（Apple `container`，前后端分容器）

当前 mac mini 演示使用 Apple `container`，不是 Docker daemon。固定路径与容器名：

- 代码与持久化根：`/Users/mac/workspace/enterprise-agent-platform`
- env：`/Users/mac/workspace/enterprise-agent-platform/.env`
- 后端容器：`agent-backend`，端口 `9999`
- 前端容器：`agent-front`，端口 `5173`
- tunnel 容器：`cloudflared-mesh`
- 持久化挂载：`knowledge/`、`data/`、`logs/` 对应 `/app/knowledge`、`/app/data`、`/app/logs`

```bash
# 在本机同步到 mac mini（按需加 --delete；knowledge/data/logs 不走 git，确认后单独同步）
R=macmini
D=/Users/mac/workspace/enterprise-agent-platform
rsync -az --exclude .git --exclude .venv --exclude node_modules ./ "$R:$D/"

# 在 mac mini 构建，tag 用月日版本号，如 0621b3
TAG=0621b3
ssh "$R" "cd $D \
  && npm --prefix agent-front install \
  && npm --prefix agent-front run build \
  && /usr/local/bin/container build -f agent-front/deploy/Containerfile.agent-backend -t agent-backend:$TAG . \
  && /usr/local/bin/container build -f agent-front/deploy/Containerfile.agent-front -t agent-front:$TAG ."

# 后端：env_file 读 .env；大文件上传上限当前与 nginx 对齐为 512MiB
ssh "$R" "cd $D \
  && /usr/local/bin/container stop agent-backend 2>/dev/null || true \
  && /usr/local/bin/container rm agent-backend 2>/dev/null || true \
  && /usr/local/bin/container run --detach \
    --name agent-backend \
    --cpus 4 \
    --memory 2048M \
    --network default,mtu=1280 \
    --publish 0.0.0.0:9999:9999 \
    --env-file $D/.env \
    --env MAX_UPLOAD_FILE_BYTES=536870912 \
    --mount type=bind,source=$D/knowledge,target=/app/knowledge \
    --mount type=bind,source=$D/data,target=/app/data \
    --mount type=bind,source=$D/logs,target=/app/logs \
    agent-backend:$TAG"

# 前端 nginx：代理到 Apple container 宿主网关 192.168.64.1:9999
ssh "$R" "cd $D \
  && /usr/local/bin/container stop agent-front 2>/dev/null || true \
  && /usr/local/bin/container rm agent-front 2>/dev/null || true \
  && /usr/local/bin/container run --detach \
    --name agent-front \
    --cpus 2 \
    --memory 512M \
    --network default,mtu=1280 \
    --publish 0.0.0.0:5173:80 \
    --env API_PROXY_TARGET=http://192.168.64.1:9999 \
    agent-front:$TAG"

# 验证
ssh "$R" "/usr/local/bin/container ls --all"
curl -sS http://127.0.0.1:15173/health  # 如本机开了 15173 SSH tunnel，见下方
ssh "$R" "curl -sS http://127.0.0.1:5173/health"
```

Apple `container run --network` 目前只接受 `mac`、`mtu` 等属性；不要写
`--network default,hostname=agent-backend,mtu=1280`，会报 `unknown network property 'hostname'`。

公网 `https://agent.guoker.org` 经 `cloudflared-mesh`，适合普通页面和小请求；大文件评标上传建议开本地 SSH 隧道绕过
Cloudflare request body / 连接中断风险：

```bash
ssh -fN -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -L 15173:127.0.0.1:5173 macmini

open http://127.0.0.1:15173/contracts/tender-review
```

## 五、审核能力开关（写在各机 `audit-agent.env`，默认全关/安全值）

| 开关 | 默认 | 作用 | 开启前提 |
|---|---|---|---|
| `AUDIT_CONTRACT_MAX_RETRY` | 1 | 契约/CLI 失败重试次数 | 安全，可调大（如 3）|
| `AUDIT_ENABLE_READ` | 0 | 文本模式也给 Read 工具（多模态读发票图）| 模型多模态 + 接受 Read 往返延迟 |
| `AUDIT_STRUCTURED_OUTPUT` | 0 | 强制 json_schema 结构化输出 | litellm+模型支持 json_schema |
| `AUDIT_LEAN_CONTEXT` | 1 | =1 不加载 .claude/settings(含 hooks) | hook 生效需设 0 |
| `AUDIT_WRITE_VALIDATION_ENABLED` | 关 | check-before-write 写入校验 hook | 见 hook 注释，需 lean=0 + 模型经 Write 写结果 |
| `SECOND_REVIEW_ENABLED` | 关 | 二次 SDK 复核 | 耗时翻倍，慎开 |
| `MODEL_PROFILES_JSON` | 未设置 | 按模型名配置 `context_window` / `max_output_tokens` | 切换 `MODEL_NAME` 或 `TENDER_EVAL_MODEL` 时同步选择对应条目 |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | 由 CLI/网关决定 | 单模型兼容配置：CLI 请求的最大输出 token | 仅在未配置模型条目时使用；本地小窗口模型按网关实际限制填写 |

## 六、OCR 文档识别（可选能力）

OCR（`/ocr/extract` 纯识别 + `/ocr/fill` 识别+回填）默认**不装**，需显式开启。Excel /
文本层 PDF / Word 等**原生直读不依赖引擎**；只有**扫描件**才需 PaddleOCR-VL serving。

### 构建（装 OCR 依赖）

```bash
# 镜像默认精简（不含 paddleocr）；加 WITH_OCR=1 才装 paddleocr[doc-parser]
docker compose build --build-arg WITH_OCR=1
```

镜像内已装 PaddleOCR 运行时系统库（`libgl1` / `libglib2.0-0` / `libgomp1`）。

### env（写各机 `audit-agent.env`）

| 开关 | 示例 / 默认 | 作用 |
|---|---|---|
| `OCR_VL_SERVER_URL` | `http://10.200.52.4:4000/v1` | PaddleOCR-VL 的 VLM 识别走的 litellm OpenAI 兼容端点；**未设则扫描件不可识别** |
| `OCR_VL_MODEL_NAME` | litellm 注册的 model_name | 须与 litellm 配置**一字不差**，否则上游 `model does not exist`（`/v1/models` 查 id）|
| `OCR_VL_USE_PADDLE_PIPELINE` | `0` | =0 直接走网关识别；=1 才启用本地 PP-DocLayoutV2 layout pipeline（部分 arm64 容器会崩，慎开）|
| `MAX_CONCURRENT_OCR` | 2 | 并发识别上限（识别在信号量内跑到完成，无请求级超时）|
| `OCR_FILL_TIMEOUT_SEC` | 180 | `/ocr/fill` 字段映射（调模型）超时 |
| `OCR_MAX_FILE_BLOCK_CHARS` | 40000 | 单文件识别底稿截断上限（超长截断并显式标记）|

> `/ocr/fill` 的字段映射调一次模型，走审核同一套 `MODEL_BASE_URL` 网关。

### compose（缓存卷）

PaddleX 模型缓存挂 volume 避免每次重下：

```yaml
    volumes:
      - paddlex-cache:/home/app/.paddlex
# 顶层
volumes:
  paddlex-cache:
```

> 仅 `OCR_VL_USE_PADDLE_PIPELINE=1` 时，PP-DocLayoutV2 版面权重首次运行联网下载（baidu
> bcebos）；离线环境需预热（联网机跑一次填充 `paddlex-cache` 再搬运）。默认 `=0` 不需要。

### 验证

```bash
# litellm 是否注册了 PaddleOCR-VL（/v1/models 应含 OCR_VL_MODEL_NAME）
curl -s $OCR_VL_SERVER_URL/models -H "Authorization: Bearer <key>" | grep <model_name>
# 上传扫描件试 /ocr/extract（kind 应为 ocr，非 error）
curl -X POST http://127.0.0.1:9999/ocr/extract -H "Authorization: Bearer <token>" -F 'files=@scan.pdf'
```

> 未部署 serving 时：扫描件返回 `kind=error`，但 Excel / 文本层 PDF / Word 等原生直读
> **不受影响**，OCR API 本身仍可用。

## 七、验证（部署后必做）

```bash
# 容器健康
ssh ... "docker ps --filter name=audit-agent --format '{{.Image}} {{.Status}}'"
# 健康端点
ssh ... "docker exec audit-agent python -c \"import urllib.request as u;print(u.urlopen('http://127.0.0.1:9999/health',timeout=4).read().decode())\""
# 知识资产校验（规则文件 schema + category/文件名/rule_id 前缀一致）
ssh ... "docker exec audit-agent python -c \"from server.platform.asset_validation import validate_knowledge_assets as v;print(v())\""
# 关键 env（TENANT_KEYS 必须是完整 JSON，否则 401）
ssh ... "docker exec audit-agent printenv TENANT_KEYS MODEL_NAME"
# 跑一笔真实审核（用 app 用户，不能用 root，见 TROUBLESHOOTING）
```
