# API-only 启动文档

本文档用于本地启动 `workmanship-backend` API 服务。该仓库不再承担 `workmanship-web` 前端运行时托管职责。

## 1. 环境要求

- macOS / Linux / Windows（WSL 或 Git Bash）
- Python 3.10+
- 可访问的网络（用于安装 Python 依赖）

## 2. 安装依赖

在项目根目录执行：

```bash
bash scripts/bootstrap.sh
```

## 3. 启动服务

```bash
bash scripts/start_backend.sh
```

脚本行为：
- 自动创建 `.venv`
- 自动安装 `backend/requirements.txt`
- 自动创建 `logs/` 与 `backend/static/uploads`
- 若 `backend/.env.dev` 不存在则生成占位配置
- 按 `backend/.env.dev` 中的 `HOST` / `PORT` 启动 FastAPI
- 写入 PID 到 `logs/backend.pid`
- 写入运行日志到 `logs/backend.out.log`

默认本地端口：`8080`

## 4. 验证启动

```bash
curl -sS http://127.0.0.1:8080/health
```

查看日志：

```bash
tail -n 200 logs/backend.out.log
```

## 5. 停止服务

```bash
bash scripts/stop_backend.sh
```

## 5.1 前端改动随 backend 提交时的 dist 同步

当 `workmanship-web` 的前端改动需要一起发布到当前 backend 仓库时，不要等到 `git commit` 再生成产物。

推荐流程：

```bash
bash scripts/sync_frontend_dist.sh
git add -A dist
```

如果你在 PowerShell 里操作，优先使用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync_frontend_dist.ps1
git add -A dist
```

说明：
- `scripts/sync_frontend_dist.sh` 会进入默认的 `../workmanship-web` 前端目录执行 `npm run build:web --silent`
- `scripts/sync_frontend_dist.ps1` 提供给 PowerShell 使用，避免通过 bash/WSL 路径运行前端构建
- 然后把前端 `dist/` 覆盖同步到当前 backend 仓库的 `dist/`
- 若前端目录不在默认位置，可用环境变量覆盖：

```bash
FRONTEND_DIR=/path/to/workmanship-web bash scripts/sync_frontend_dist.sh
```

纯后端改动无需执行该脚本。

## 6. 配置说明

主要配置文件：`backend/.env.dev`

关键变量：
- `HOST`
- `PORT`
- `PUBLIC_URL`
- `CORS_ALLOW_ORIGINS`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_REDIRECT_URI`
- `JWT_SECRET`
- `USERS_DB_URL`

## 6.1 容器 / Pipeline 部署约定

容器运行时不要依赖仓库内的 `.env.example` 或 `.env.test.example`。

必须由 pipeline 或部署平台生成真实配置文件，并通过 `ENV_FILE` 显式注入，例如：

```bash
ENV_FILE=/chj/app/backend/.env.test.runtime \
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

或：

```bash
ENV_FILE=/chj/app/backend/.env.test.runtime \
gunicorn backend.main:app -c backend/gunicorn.conf.py
```

推荐把以下值放进运行时配置文件，而不是提交到 git：
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_REDIRECT_URI`
- `JWT_SECRET`
- `USERS_DB_URL`
- `PUBLIC_URL`
- `CORS_ALLOW_ORIGINS`
- `OIS_IDENTIFY`
- `OIS_ENV`
- `OIS_OIS3_URL`
- `OIS_REGION`
- `OIS_LICLOUD_APPID`
- `OIS_IDAAS_URL`
- `OIS_IDAAS_CLIENT_ID`
- `OIS_IDAAS_CLIENT_SECRET`
- `OIS_IDAAS_SERVICE_ID`
- `OIS_PUBLIC_BASE_URL`

### 6.2 先自动生成半成品运行时配置

可以先执行：

```bash
bash scripts/prepare_test_runtime_env.sh
```

脚本会：
- 若 `backend/.env.test.runtime` 不存在，则自动生成
- 预填测试环境固定的非敏感值
- 对数据库、JWT、OIS 密钥等敏感项留空
- 若文件已存在则不覆盖

### 6.3 用脚本补齐敏感字段

可以直接用参数补值：

```bash
bash scripts/patch_test_runtime_env.sh \
  --jwt-secret 'your-jwt-secret' \
  --users-db-url 'mysql://user:password@host:3306/dbname' \
  --ois-idaas-client-secret 'your-ois-secret'
```

支持的参数包括：
- `--feishu-app-id`
- `--feishu-app-secret`
- `--jwt-secret`
- `--users-db-url`
- `--ois-identify`
- `--ois-env`
- `--ois-ois3-url`
- `--ois-region`
- `--ois-licloud-appid`
- `--ois-idaas-url`
- `--ois-idaas-client-id`
- `--ois-idaas-client-secret`
- `--ois-idaas-service-id`
- `--ois-public-base-url`

### 6.4 `backend/.env.test.runtime` 示例

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_REDIRECT_URI=https://workmanship-backend-test.chehejia.com/auth/feishu/callback

JWT_SECRET=replace-with-real-secret
JWT_EXPIRE_HOURS=72

USERS_DB_URL=mysql://user:password@db-host:3306/database

HOST=0.0.0.0
PORT=8080
DEBUG=false
LOG_LEVEL=INFO

PUBLIC_URL=https://workmanship-backend-test.chehejia.com
CORS_ALLOW_ORIGINS=https://workmanship-web-test.chehejia.com,http://127.0.0.1:5173,http://localhost:5173,app://root,null

OIS_IDENTIFY=replace-with-real-identify
OIS_ENV=replace-with-real-env
OIS_OIS3_URL=https://replace-with-real-ois-endpoint
OIS_REGION=replace-with-real-region
OIS_LICLOUD_APPID=replace-with-real-appid
OIS_IDAAS_URL=https://replace-with-real-idaas
OIS_IDAAS_CLIENT_ID=replace-with-real-client-id
OIS_IDAAS_CLIENT_SECRET=replace-with-real-client-secret
OIS_IDAAS_SERVICE_ID=replace-with-real-service-id
OIS_PUBLIC_BASE_URL=https://replace-with-real-public-base-url
```

### 6.5 Pipeline 生成示例

如果 pipeline 支持 shell 步骤，可以在部署机上生成运行时配置文件：

```bash
cat > /chj/app/backend/.env.test.runtime <<'EOF'
FEISHU_APP_ID=${FEISHU_APP_ID}
FEISHU_APP_SECRET=${FEISHU_APP_SECRET}
FEISHU_REDIRECT_URI=https://workmanship-backend-test.chehejia.com/auth/feishu/callback

JWT_SECRET=${JWT_SECRET}
JWT_EXPIRE_HOURS=72

USERS_DB_URL=${USERS_DB_URL}

HOST=0.0.0.0
PORT=8080
DEBUG=false
LOG_LEVEL=INFO

PUBLIC_URL=https://workmanship-backend-test.chehejia.com
CORS_ALLOW_ORIGINS=https://workmanship-web-test.chehejia.com,http://127.0.0.1:5173,http://localhost:5173,app://root,null

OIS_IDENTIFY=${OIS_IDENTIFY}
OIS_ENV=${OIS_ENV}
OIS_OIS3_URL=${OIS_OIS3_URL}
OIS_REGION=${OIS_REGION}
OIS_LICLOUD_APPID=${OIS_LICLOUD_APPID}
OIS_IDAAS_URL=${OIS_IDAAS_URL}
OIS_IDAAS_CLIENT_ID=${OIS_IDAAS_CLIENT_ID}
OIS_IDAAS_CLIENT_SECRET=${OIS_IDAAS_CLIENT_SECRET}
OIS_IDAAS_SERVICE_ID=${OIS_IDAAS_SERVICE_ID}
OIS_PUBLIC_BASE_URL=${OIS_PUBLIC_BASE_URL}
EOF
```

然后用这份文件启动：

```bash
ENV_FILE=/chj/app/backend/.env.test.runtime \
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

或：

```bash
ENV_FILE=/chj/app/backend/.env.test.runtime \
gunicorn backend.main:app -c backend/gunicorn.conf.py
```

## 7. 与前端联调

独立启动 `workmanship-web`：

```bash
cd ../workmanship-web
npm run dev
```

默认联调组合：
- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8080`

## 8. 本地开发 / 测试部署命令对照

### 本地开发

后端（在 `workmanship-backend` 根目录）：

```bash
bash scripts/bootstrap.sh
bash scripts/start_backend.sh
```

前端（在 `workmanship-web` 根目录）：

```bash
npm run dev
```

停止后端：

```bash
bash scripts/stop_backend.sh
```

### 测试部署（半自动）

1. 先生成半成品运行时配置：

```bash
bash scripts/prepare_test_runtime_env.sh
```

2. 再补齐敏感字段：

```bash
bash scripts/patch_test_runtime_env.sh \
  --feishu-app-id 'your-feishu-app-id' \
  --feishu-app-secret 'your-feishu-app-secret' \
  --jwt-secret 'your-jwt-secret' \
  --users-db-url 'mysql://user:password@host:3306/dbname' \
  --ois-identify 'your-ois-identify' \
  --ois-env 'your-ois-env' \
  --ois-ois3-url 'https://your-ois-endpoint' \
  --ois-region 'your-ois-region' \
  --ois-licloud-appid 'your-ois-appid' \
  --ois-idaas-url 'https://your-idaas-endpoint' \
  --ois-idaas-client-id 'your-ois-client-id' \
  --ois-idaas-client-secret 'your-ois-client-secret' \
  --ois-idaas-service-id 'your-ois-service-id' \
  --ois-public-base-url 'https://your-ois-public-base-url'
```

3. 启动测试环境服务：

```bash
ENV_FILE=backend/.env.test.runtime \
gunicorn backend.main:app -c backend/gunicorn.conf.py
```

如需直接用 uvicorn：

```bash
ENV_FILE=backend/.env.test.runtime \
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8080
```
