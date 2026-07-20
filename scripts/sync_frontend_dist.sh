#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_FRONTEND_DIR="$(cd "$BACKEND_DIR/.." && pwd)/workmanship-web"
FRONTEND_DIR="${FRONTEND_DIR:-$DEFAULT_FRONTEND_DIR}"

if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
  echo "[sync_frontend_dist] 未找到前端 package.json: $FRONTEND_DIR"
  echo "[sync_frontend_dist] 可通过 FRONTEND_DIR=/path/to/workmanship-web bash scripts/sync_frontend_dist.sh 指定前端目录"
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "[sync_frontend_dist] 前端 node_modules 不存在，请先在前端目录执行 npm ci"
  exit 1
fi

echo "[sync_frontend_dist] 前端目录: $FRONTEND_DIR"
echo "[sync_frontend_dist] 构建前端 dist..."
(
  cd "$FRONTEND_DIR"
  npm run build:web --silent
)

if [[ ! -d "$FRONTEND_DIR/dist" ]]; then
  echo "[sync_frontend_dist] 前端 dist 不存在，构建可能失败"
  exit 1
fi

echo "[sync_frontend_dist] 同步 dist → backend"
rm -rf "$BACKEND_DIR/dist"
cp -r "$FRONTEND_DIR/dist" "$BACKEND_DIR/dist"

echo "[sync_frontend_dist] 完成"
echo "[sync_frontend_dist] 下一步请执行: git add -A dist"
