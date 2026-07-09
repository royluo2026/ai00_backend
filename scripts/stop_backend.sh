#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="$ROOT_DIR/logs/backend.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "[INFO] 未找到 PID 文件，无需停止"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if [[ -z "$PID" ]]; then
  echo "[WARN] PID 文件为空，已清理"
  rm -f "$PID_FILE"
  exit 0
fi

if kill -0 "$PID" >/dev/null 2>&1; then
  kill "$PID"
  echo "[OK] 已停止后端进程: PID=$PID"
else
  echo "[INFO] 进程不存在，清理 PID 文件: PID=$PID"
fi

rm -f "$PID_FILE"
