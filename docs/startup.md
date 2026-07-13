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

## 7. 与前端联调

独立启动 `workmanship-web`：

```bash
cd ../workmanship-web
npm run dev
```

默认联调组合：
- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8080`
