#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_ENV="$ROOT_DIR/backend/.env.test.runtime"

if [[ -f "$TARGET_ENV" ]]; then
  echo "[INFO] 已存在运行时配置文件：$TARGET_ENV"
  echo "[INFO] 未做覆盖，请直接补齐敏感信息后使用。"
  exit 0
fi

cat > "$TARGET_ENV" <<'EOF'
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_REDIRECT_URI=https://workmanship-backend-test.chehejia.com/auth/feishu/callback

JWT_SECRET=
JWT_EXPIRE_HOURS=72

USERS_DB_URL=

HOST=0.0.0.0
PORT=8080
DEBUG=false
LOG_LEVEL=INFO

PUBLIC_URL=https://workmanship-backend-test.chehejia.com
CORS_ALLOW_ORIGINS=https://workmanship-web-test.chehejia.com,http://127.0.0.1:5173,http://localhost:5173,app://root,null

FIRST_SUPER_ADMIN_EMAIL=

OIS_IDENTIFY=
OIS_ENV=
OIS_OIS3_URL=
OIS_REGION=
OIS_LICLOUD_APPID=
OIS_IDAAS_URL=
OIS_IDAAS_CLIENT_ID=
OIS_IDAAS_CLIENT_SECRET=
OIS_IDAAS_SERVICE_ID=
OIS_PUBLIC_BASE_URL=
EOF

cat <<EOF
[OK] 已生成运行时配置模板：$TARGET_ENV
[INFO] 请补齐以下敏感字段后再启动：
  - FEISHU_APP_ID
  - FEISHU_APP_SECRET
  - JWT_SECRET
  - USERS_DB_URL
  - OIS_IDENTIFY
  - OIS_ENV
  - OIS_OIS3_URL
  - OIS_REGION
  - OIS_LICLOUD_APPID
  - OIS_IDAAS_URL
  - OIS_IDAAS_CLIENT_ID
  - OIS_IDAAS_CLIENT_SECRET
  - OIS_IDAAS_SERVICE_ID
  - OIS_PUBLIC_BASE_URL

[INFO] 示例补齐命令：
  sed -i "s|^JWT_SECRET=.*|JWT_SECRET=你的真实密钥|" "$TARGET_ENV"
  sed -i "s|^USERS_DB_URL=.*|USERS_DB_URL=mysql://user:password@host:3306/dbname|" "$TARGET_ENV"
  sed -i "s|^OIS_IDAAS_CLIENT_SECRET=.*|OIS_IDAAS_CLIENT_SECRET=你的真实secret|" "$TARGET_ENV"

[INFO] 启动示例：
  ENV_FILE=$TARGET_ENV gunicorn backend.main:app -c backend/gunicorn.conf.py
EOF
