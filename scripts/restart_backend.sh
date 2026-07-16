#!/usr/bin/env bash
# 一键重启后端：强制杀旧进程 → 启动新进程
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT_DIR/logs/backend.pid"

cd "$ROOT_DIR"

# 1. 杀旧进程
if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE")"
  if [[ -n "${OLD_PID}" ]] && kill -0 "$OLD_PID" >/dev/null 2>&1; then
    echo "[INFO] 停止旧进程: PID=$OLD_PID"
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
    kill -9 "$OLD_PID" 2>/dev/null || true
  fi
  rm -f "$PID_FILE"
fi
# 备用：按端口杀
PORT="${PORT:-8081}"
PID_BY_PORT=$(powershell.exe -Command "Get-NetTCPConnection -LocalPort $PORT -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess" 2>/dev/null || echo "")
if [[ -n "$PID_BY_PORT" && "$PID_BY_PORT" =~ ^[0-9]+$ ]]; then
  echo "[INFO] 停止端口 $PORT 上的进程: PID=$PID_BY_PORT"
  powershell.exe -Command "Stop-Process -Id $PID_BY_PORT -Force" 2>/dev/null || true
fi

# 2. 启动
exec bash "$ROOT_DIR/scripts/start_backend.sh"
