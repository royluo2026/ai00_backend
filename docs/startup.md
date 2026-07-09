# 项目启动文档

本文档用于本地启动 workmanship-backend 后端服务。

## 1. 环境要求

- macOS/Linux
- Python 3.10+
- 可访问的网络（用于安装 Python 依赖）

## 2. 一键安装依赖

在项目根目录执行：

```bash
bash scripts/bootstrap.sh
```

说明：
- 自动选择 Python 3.10+（优先 `python3.12` / `python3.11` / `python3.10`）
- 自动创建 `.venv` 虚拟环境（若不存在）
- 自动安装 `backend/requirements.txt` 依赖

## 3. 启动服务

```bash
bash scripts/start_backend.sh
```

脚本行为：
- 自动创建 `logs/` 目录
- 自动创建 `backend/static/uploads` 目录
- 自动生成 `backend/.env.dev`（若不存在，内容为本地占位配置）
- 后台启动 FastAPI 服务，默认端口 `8080`
- 写入 PID 到 `logs/backend.pid`
- 写入运行日志到 `logs/backend.out.log`
- 启动后最多等待 15 秒健康检查，确认服务可访问才返回成功

## 4. 验证启动

健康检查：

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
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_REDIRECT_URI`
- `JWT_SECRET`
- `USERS_DB_URL`

注意：
- 当前后端在数据库不可用时可启动，但涉及数据库读写的接口会失败。
- 当前将 `cel-python` 作为可选依赖；未安装时，规则引擎中的 CEL 表达式会返回 `SKIP`。
- 上线前请替换所有占位配置，尤其是 `JWT_SECRET` 与飞书凭证。
