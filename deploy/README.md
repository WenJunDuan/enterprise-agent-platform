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
| **跳板 mac mini** | `macs-mac-mini.tailbf6a2a.ts.net` | mac | config 别名 `macmini`（key `macs_mac_mini_ed25519`）| demo 的唯一入口 |
| **prod 内网** | `192.168.1.24`(构建) + 隔离目标机 | — | 物理隔离，离线 tar 搬运 | 内网 qwen3.6 vLLM @ `:8100`（Ascend NPU, 256K ctx, `enable_thinking=false`）|

- **litellm 网关**（dev）：容器 `ea-litellm`，配置 `/opt/application/litellm/litellm_config.yaml`，改后 `docker restart ea-litellm`。
- SSH 用密钥认证，**不要反复用密码**（会触发 OpenSSH PerSourcePenalties / fail2ban 封 IP）。

## 二、约定

- **部署根**：各机 `/opt/application/audit-agent/`
- **镜像标签**：`audit-agent:{月日}{版本}`，如 `0611b1` = 6/11 第 1 版。**更新代码必须 bump 版本号，禁止复用旧标签**（否则版本分不清）。
- **离线包**：`docker save` → `audit-agent-{tag}.tar` + `audit-agent-{tag}.tar.sha256`

## 三、什么烤进镜像 vs 挂载（决定改完要不要重建）

| 内容 | 方式 | 改完怎么生效 |
|---|---|---|
| `server/`、`.claude/`、`ui/dist` | **烤进镜像** | 必须 `docker compose build` 重建 |
| `knowledge/`、`data/`、`logs/` | **volume 挂载** | 同步到挂载目录即可，无需重建 |
| `audit-agent.env`（env_file）| 挂载 | 改后 `docker compose up -d --force-recreate` |

> `knowledge/` 与 `data/` 被 `.gitignore` 忽略（制度源不入库）→ 部署时**单独同步规则文件**，不在镜像/git 里。

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

## 五、审核能力开关（写在各机 `audit-agent.env`，默认全关/安全值）

| 开关 | 默认 | 作用 | 开启前提 |
|---|---|---|---|
| `AUDIT_CONTRACT_MAX_RETRY` | 1 | 契约/CLI 失败重试次数 | 安全，可调大（如 3）|
| `AUDIT_ENABLE_READ` | 0 | 文本模式也给 Read 工具（多模态读发票图）| 模型多模态 + 接受 Read 往返延迟 |
| `AUDIT_STRUCTURED_OUTPUT` | 0 | 强制 json_schema 结构化输出 | litellm+模型支持 json_schema |
| `AUDIT_LEAN_CONTEXT` | 1 | =1 不加载 .claude/settings(含 hooks) | hook 生效需设 0 |
| `AUDIT_WRITE_VALIDATION_ENABLED` | 关 | check-before-write 写入校验 hook | 见 hook 注释，需 lean=0 + 模型经 Write 写结果 |
| `SECOND_REVIEW_ENABLED` | 关 | 二次 SDK 复核 | 耗时翻倍，慎开 |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | CLI 默认 64000 | CLI 请求的最大输出 token | **本地 65536 上下文模型必须压低（如 16000）**，否则撞 400；大上下文云模型可留默认 |

## 六、验证（部署后必做）

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
