#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_ENV="$ROOT_DIR/backend/.env.test.runtime"

usage() {
  cat <<'EOF'
用法：
  bash scripts/patch_test_runtime_env.sh [选项]

选项：
  --env-file PATH
  --feishu-app-id VALUE
  --feishu-app-secret VALUE
  --jwt-secret VALUE
  --users-db-url VALUE
  --ois-identify VALUE
  --ois-env VALUE
  --ois-ois3-url VALUE
  --ois-region VALUE
  --ois-licloud-appid VALUE
  --ois-idaas-url VALUE
  --ois-idaas-client-id VALUE
  --ois-idaas-client-secret VALUE
  --ois-idaas-service-id VALUE
  --ois-public-base-url VALUE
  --help

示例：
  bash scripts/patch_test_runtime_env.sh \
    --jwt-secret 'your-jwt-secret' \
    --users-db-url 'mysql://user:password@host:3306/dbname' \
    --ois-idaas-client-secret 'your-ois-secret'
EOF
}

if [[ $# -eq 0 ]]; then
  usage
  exit 1
fi

if [[ ! -f "$TARGET_ENV" ]]; then
  echo "[ERROR] 未找到运行时配置文件：$TARGET_ENV"
  echo "[INFO] 请先执行：bash scripts/prepare_test_runtime_env.sh"
  exit 1
fi

escape_replacement() {
  printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'
}

patch_key() {
  local key="$1"
  local value="$2"
  local escaped
  escaped="$(escape_replacement "$value")"
  if grep -q "^${key}=" "$TARGET_ENV"; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" "$TARGET_ENV"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$TARGET_ENV"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      TARGET_ENV="$2"
      shift 2
      ;;
    --feishu-app-id)
      patch_key FEISHU_APP_ID "$2"
      shift 2
      ;;
    --feishu-app-secret)
      patch_key FEISHU_APP_SECRET "$2"
      shift 2
      ;;
    --jwt-secret)
      patch_key JWT_SECRET "$2"
      shift 2
      ;;
    --users-db-url)
      patch_key USERS_DB_URL "$2"
      shift 2
      ;;
    --ois-identify)
      patch_key OIS_IDENTIFY "$2"
      shift 2
      ;;
    --ois-env)
      patch_key OIS_ENV "$2"
      shift 2
      ;;
    --ois-ois3-url)
      patch_key OIS_OIS3_URL "$2"
      shift 2
      ;;
    --ois-region)
      patch_key OIS_REGION "$2"
      shift 2
      ;;
    --ois-licloud-appid)
      patch_key OIS_LICLOUD_APPID "$2"
      shift 2
      ;;
    --ois-idaas-url)
      patch_key OIS_IDAAS_URL "$2"
      shift 2
      ;;
    --ois-idaas-client-id)
      patch_key OIS_IDAAS_CLIENT_ID "$2"
      shift 2
      ;;
    --ois-idaas-client-secret)
      patch_key OIS_IDAAS_CLIENT_SECRET "$2"
      shift 2
      ;;
    --ois-idaas-service-id)
      patch_key OIS_IDAAS_SERVICE_ID "$2"
      shift 2
      ;;
    --ois-public-base-url)
      patch_key OIS_PUBLIC_BASE_URL "$2"
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] 未知参数：$1"
      usage
      exit 1
      ;;
  esac
done

echo "[OK] 已更新运行时配置文件：$TARGET_ENV"
