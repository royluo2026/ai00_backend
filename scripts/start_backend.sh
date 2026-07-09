#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/backend.pid"
OUT_LOG="$LOG_DIR/backend.out.log"
ENV_FILE="$ROOT_DIR/backend/.env.dev"

cd "$ROOT_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$ROOT_DIR/backend/static/uploads"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE")"
  if [[ -n "${OLD_PID}" ]] && kill -0 "$OLD_PID" >/dev/null 2>&1; then
    echo "[INFO] 后端已在运行，PID=$OLD_PID"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

if [[ ! -d "$ROOT_DIR/.venv" ]]; then
  echo "[INFO] 未检测到 .venv，先执行依赖安装"
  "$ROOT_DIR/scripts/bootstrap.sh"
fi

if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<'EOF'
FEISHU_APP_ID=local_dummy_app_id
FEISHU_APP_SECRET=local_dummy_app_secret
FEISHU_REDIRECT_URI=http://127.0.0.1:8080/auth/feishu/callback
JWT_SECRET=local_dummy_jwt_secret_replace_me
JWT_EXPIRE_HOURS=72
USERS_DB_URL=mysql://root:root@127.0.0.1:3306/workmanship
HOST=0.0.0.0
PORT=8080
DEBUG=true
EOF
  echo "[INFO] 已生成 backend/.env.dev（占位配置，请按需修改）"
fi

source "$ROOT_DIR/.venv/bin/activate"
export PYTHONUNBUFFERED=1

nohup python -m uvicorn backend.main:app --host 0.0.0.0 --port 8080 > "$OUT_LOG" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

for _ in $(seq 1 15); do
  if curl -fsS "http://127.0.0.1:8080/health" >/dev/null 2>&1; then
    echo "[OK] 后端已启动: PID=$NEW_PID"
    echo "[OK] 日志文件: $OUT_LOG"
    echo "[OK] 健康检查: http://127.0.0.1:8080/health"
    exit 0
  fi
  if ! kill -0 "$NEW_PID" >/dev/null 2>&1; then
    echo "[ERROR] 后端进程已退出，请查看日志: $OUT_LOG"
    rm -f "$PID_FILE"
    exit 1
  fi
  sleep 1
done

echo "[ERROR] 健康检查超时，请查看日志: $OUT_LOG"
rm -f "$PID_FILE"
exit 1
