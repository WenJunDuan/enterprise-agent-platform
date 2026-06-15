#!/usr/bin/env bash
# audit-agent 部署 / 恢复脚本。详见 deploy/README.md。
#
# 用法:
#   ./deploy/deploy.sh dev    <tag>   # 本机源码 → 同步+构建镜像<tag>+重启+导出 tar (在 dev 上)
#   ./deploy/deploy.sh pull   <tag>   # 把 dev 上的 <tag> 离线包拉到 ~/Desktop/audit-agent-<tag>/
#   ./deploy/deploy.sh demo   <tag>   # 把本地 <tag> 离线包经 mac mini 跳板 load 到 demo + 重启
#   ./deploy/deploy.sh verify dev|demo
#
# 标签约定: {月日}{版本}, 如 0611b1。更新代码必 bump, 勿复用旧标签。
# 前提: ~/.ssh/spark-3d55 (dev), ~/.ssh/njsr-app01_ed25519 + ~/.ssh/config 里的 macmini (demo)。
# ⚠️ 本脚本不含任何密钥/token; 凭据只在各机 audit-agent.env / litellm_config.yaml。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST=/opt/application/audit-agent

# --- 环境 (仅主机+密钥路径, 无明文凭据) ---
DEV_KEY="$HOME/.ssh/spark-3d55";          DEV_HOST="admin@100.107.62.19"
DEMO_KEY="$HOME/.ssh/njsr-app01_ed25519"; DEMO_HOST="root@10.200.52.4"
DESKTOP="$HOME/Desktop"

SSH_BASE=(-o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=20)

dev_ssh()  { ssh -i "$DEV_KEY"  "${SSH_BASE[@]}" "$DEV_HOST"  "$@"; }
demo_ssh() { ssh -J macmini -i "$DEMO_KEY" "${SSH_BASE[@]}" "$DEMO_HOST" "$@"; }
dev_rsh()  { echo "ssh -i $DEV_KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"; }

die() { echo "❌ $*" >&2; exit 1; }
need_tag() { [ -n "${1:-}" ] || die "缺少 <tag>，如 0611b1"; }

deploy_dev() {
  local tag="$1"; need_tag "$tag"
  echo "==> [dev] 同步源码 + 配置 + 规则到 $DEV_HOST:$DEST"
  rsync -rtz --delete --exclude=__pycache__ --exclude='*.pyc' --exclude=.venv \
    -e "$(dev_rsh)" "$REPO_ROOT/server/"  "$DEV_HOST:$DEST/server/"
  rsync -rtz --delete --exclude=settings.local.json \
    -e "$(dev_rsh)" "$REPO_ROOT/.claude/" "$DEV_HOST:$DEST/.claude/"
  # knowledge 是挂载目录且被 gitignore; 只同步 expense 规则
  rsync -rtz --delete \
    -e "$(dev_rsh)" "$REPO_ROOT/knowledge/expense/" "$DEV_HOST:$DEST/knowledge/expense/"

  echo "==> [dev] bump compose 镜像标签 → $tag"
  dev_ssh "sed -i -E 's#image: audit-agent:[^[:space:]]+#image: audit-agent:$tag#' $DEST/docker-compose.yml && grep image: $DEST/docker-compose.yml"

  echo "==> [dev] 构建 + 重启 (pip 依赖层有缓存; 慢则几分钟)"
  dev_ssh "cd $DEST && docker compose build && docker compose up -d --force-recreate audit-agent"

  echo "==> [dev] 导出离线包 audit-agent-$tag.tar"
  dev_ssh "cd $DEST && docker save audit-agent:$tag -o audit-agent-$tag.tar && sha256sum audit-agent-$tag.tar > audit-agent-$tag.tar.sha256 && ls -la audit-agent-$tag.tar*"

  verify_env dev
  echo "✅ [dev] 完成。清理旧镜像(确认无误后手动): dev_ssh 'docker rmi audit-agent:<旧tag>'"
}

pull_tag() {
  local tag="$1"; need_tag "$tag"
  local out="$DESKTOP/audit-agent-$tag"; mkdir -p "$out"
  echo "==> 拉取 dev 的离线包 → $out"
  for f in "audit-agent-$tag.tar" "audit-agent-$tag.tar.sha256" docker-compose.yml; do
    scp -i "$DEV_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new "$DEV_HOST:$DEST/$f" "$out/"
  done
  cp "$REPO_ROOT/enterprise-agent.env.example" "$out/" 2>/dev/null || true
  ( cd "$out" && shasum -a 256 -c "audit-agent-$tag.tar.sha256" )
  echo "✅ 拉取完成: $out"
}

deploy_demo() {
  local tag="$1"; need_tag "$tag"
  local tar="$DESKTOP/audit-agent-$tag/audit-agent-$tag.tar"
  [ -f "$tar" ] || die "本地找不到 $tar，先跑 ./deploy.sh pull $tag"
  echo "==> [demo] 经 mac mini 跳板传镜像 + 校验和"
  scp -J macmini -i "$DEMO_KEY" "${SSH_BASE[@]}" "$tar" "$tar.sha256" "$DEMO_HOST:$DEST/"
  echo "==> [demo] 校验 + load + 改 compose(image+去 format:raw) + 重启"
  demo_ssh "cd $DEST \
    && sha256sum -c audit-agent-$tag.tar.sha256 \
    && docker load -i audit-agent-$tag.tar \
    && cp -a docker-compose.yml docker-compose.yml.bak.\$(date +%Y%m%d-%H%M%S) \
    && sed -i -E 's#image: audit-agent:[^[:space:]]+#image: audit-agent:$tag#' docker-compose.yml \
    && sed -i '/^[[:space:]]*format: raw\$/d' docker-compose.yml \
    && docker compose up -d --force-recreate"
  verify_env demo
  echo "✅ [demo] 完成。"
}

verify_env() {
  local env="$1"; local run
  case "$env" in dev) run=dev_ssh;; demo) run=demo_ssh;; *) die "verify 需 dev|demo";; esac
  echo "==> [$env] 验证"
  $run "docker ps --filter name=audit-agent --format '  容器: {{.Image}} | {{.Status}}'"
  $run "docker exec audit-agent python -c \"import urllib.request as u;print('  health:',u.urlopen('http://127.0.0.1:9999/health',timeout=5).read().decode()[:80])\"" || echo "  ⚠️ health 未就绪(可能还在启动)"
  $run "docker exec audit-agent python -c \"from server.platform.asset_validation import validate_knowledge_assets as v;r=v();print('  assets:',r['status'],'rules:',r['rules']['checked_files'],'errors:',len(r['rules']['errors']))\""
  $run "docker exec audit-agent sh -c 'printf \"  TENANT_KEYS 完整? \"; printenv TENANT_KEYS | grep -q \"^{.*}\$\" && echo yes || echo NO(检查 env_file 解析)'"
}

cmd="${1:-}"; shift || true
case "$cmd" in
  dev)    deploy_dev "${1:-}";;
  pull)   pull_tag   "${1:-}";;
  demo)   deploy_demo "${1:-}";;
  verify) verify_env "${1:-}";;
  *) sed -n '2,14p' "$0"; exit 1;;
esac
