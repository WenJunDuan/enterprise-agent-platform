#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="ui/.env.local"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "错误：找不到 $ENV_FILE，请先创建并配置 VITE_API_BASE 和 VITE_API_KEY"
  exit 1
fi

# 从 .env.local 读取配置
VITE_API_BASE=$(grep -E '^VITE_API_BASE=' "$ENV_FILE" | cut -d'=' -f2- | tr -d '[:space:]')
VITE_API_KEY=$(grep -E '^VITE_API_KEY=' "$ENV_FILE" | cut -d'=' -f2- | tr -d '[:space:]')

if [[ -z "$VITE_API_KEY" ]]; then
  echo "错误：$ENV_FILE 中未配置 VITE_API_KEY"
  exit 1
fi

# 从 VITE_API_BASE 解析端口，默认 8000
PORT=$(echo "$VITE_API_BASE" | grep -oE ':[0-9]+$' | tr -d ':')
PORT="${PORT:-8000}"

echo "后端端口: $PORT"
echo "启动后端..."
TENANT_KEYS="{\"default\":\"$VITE_API_KEY\"}" \
  uvicorn server.api:app --host 127.0.0.1 --port "$PORT" &
BACKEND_PID=$!

echo "启动前端..."
cd ui && npm run dev &
FRONTEND_PID=$!

cleanup() {
  echo ""
  echo "关闭中..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo ""
echo "前后端已启动，按 Ctrl+C 退出"
wait
