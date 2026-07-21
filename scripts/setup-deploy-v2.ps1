param(
    [switch]$Skip8081Stop
)

$ErrorActionPreference = "Stop"
$V2_DIR = "E:\projects\ai00-v2"
$SERVICE_NAME = "AI00Backend-V2"
$PORT = 8082
$OLD_SERVICE = "AI00Backend-Test"
$OLD_PORT = 8081

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "  V2 部署环境初始化脚本" -ForegroundColor Cyan
Write-Host "  目标目录: $V2_DIR" -ForegroundColor Cyan
Write-Host "  服务名称: $SERVICE_NAME" -ForegroundColor Cyan
Write-Host "  监听端口: $PORT" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. 停止旧服务（8081）────────────────────────────────────────────────────
if (-not $Skip8081Stop) {
    Write-Host "[1/6] 停止旧服务 ${OLD_SERVICE} (端口 ${OLD_PORT})..." -ForegroundColor Yellow
    $oldSvc = Get-Service -Name $OLD_SERVICE -ErrorAction SilentlyContinue
    if ($oldSvc) {
        if ($oldSvc.Status -eq 'Running') {
            net stop $OLD_SERVICE
            Write-Host "  旧服务已停止" -ForegroundColor Green
        }
        # 删除旧服务
        & "nssm" remove $OLD_SERVICE confirm
        Write-Host "  旧服务已删除" -ForegroundColor Green
    } else {
        Write-Host "  旧服务不存在，跳过" -ForegroundColor Gray
    }
} else {
    Write-Host "[1/6] 跳过旧服务停止（--Skip8081Stop）" -ForegroundColor Gray
}

# ── 2. 创建目标目录结构 ────────────────────────────────────────────────────
Write-Host "[2/6] 创建目录结构..." -ForegroundColor Yellow
@(
    "$V2_DIR",
    "$V2_DIR\backend",
    "$V2_DIR\backend\static\uploads",
    "$V2_DIR\dist",
    "$V2_DIR\logs",
    "$V2_DIR\scripts"
) | ForEach-Object {
    if (-not (Test-Path $_)) {
        New-Item -Path $_ -ItemType Directory -Force | Out-Null
        Write-Host "  创建: $_" -ForegroundColor Gray
    }
}

# ── 3. 生成运行时配置文件 ────────────────────────────────────────────────
Write-Host "[3/6] 生成运行时配置..." -ForegroundColor Yellow
$ENV_FILE = "$V2_DIR\backend\.env.v2.runtime"
if (-not (Test-Path $ENV_FILE)) {
    # 尝试从当前 repo 复制 .env.example 作为基础
    $SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
    $EXAMPLE_FILE = Join-Path $SCRIPT_DIR "..\backend\.env.example"
    if (Test-Path $EXAMPLE_FILE) {
        # 复制并修改端口
        $content = Get-Content $EXAMPLE_FILE -Raw
        $content = $content -replace 'PORT=8081', "PORT=$PORT"
        $content = $content -replace '# PORT=8080', "# PORT=$PORT"
        Set-Content -Path $ENV_FILE -Value $content
        Write-Host "  已从 .env.example 生成（端口已改为 $PORT）" -ForegroundColor Green
        Write-Host "  文件: $ENV_FILE" -ForegroundColor Gray
        Write-Host "  ⚠ 请检查并补充敏感字段（JWT_SECRET, USERS_DB_URL, OIS_* 等）" -ForegroundColor Yellow
    } else {
        # 创建最小模板
        @"
# AI00 V2 Test 运行时配置
# 生成时间: $(Get-Date)

FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_REDIRECT_URI=http://127.0.0.1:${PORT}/auth/feishu/callback

JWT_SECRET=
JWT_EXPIRE_HOURS=72

USERS_DB_URL=

HOST=0.0.0.0
PORT=${PORT}
DEBUG=true
LOG_LEVEL=INFO

PUBLIC_URL=http://127.0.0.1:${PORT}
CORS_ALLOW_ORIGINS=http://127.0.0.1:${PORT},http://127.0.0.1:5173,http://localhost:5173,app://root,null

FIRST_SUPER_ADMIN_EMAIL=luoyi8@lixiang.com

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
"@ | Set-Content -Path $ENV_FILE -Encoding ASCII
        Write-Host "  已创建最小运行时配置模板" -ForegroundColor Green
    }
} else {
    Write-Host "  配置文件已存在，跳过: $ENV_FILE" -ForegroundColor Gray
}

# ── 4. 创建 Python venv ──────────────────────────────────────────────────
Write-Host "[4/6] 创建 Python 虚拟环境..." -ForegroundColor Yellow
$VENV_DIR = "$V2_DIR\venv"
if (-not (Test-Path "$VENV_DIR\Scripts\python.exe")) {
    python -m venv $VENV_DIR
    Write-Host "  虚拟环境已创建" -ForegroundColor Green
} else {
    Write-Host "  虚拟环境已存在，跳过" -ForegroundColor Gray
}

# ── 5. 注册 Windows 服务（NSSM）──────────────────────────────────────────
Write-Host "[5/6] 注册 Windows 服务..." -ForegroundColor Yellow
# 定位 NSSM
$NSSM = Get-Command "nssm" -ErrorAction SilentlyContinue
if (-not $NSSM) {
    $nssmPaths = @(
        "$env:LOCALAPPDATA\Microsoft\WinGet\nssm.exe",
        "C:\ProgramData\chocolatey\bin\nssm.exe",
        "C:\nssm\win64\nssm.exe",
        "C:\tools\nssm\nssm.exe",
        "C:\Windows\nssm.exe"
    )
    foreach ($p in $nssmPaths) {
        if (Test-Path $p) { $NSSM = $p; break }
    }
}
if (-not $NSSM) {
    Write-Host "  [错误] 找不到 nssm.exe，请安装: winget install NSSM" -ForegroundColor Red
    exit 1
}
Write-Host "  NSSM 路径: $NSSM" -ForegroundColor Gray

# 如果服务已存在，先删除
$svc = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "  服务已存在，正在重新注册..." -ForegroundColor Yellow
    net stop $SERVICE_NAME 2>$null
    & $NSSM remove $SERVICE_NAME confirm
}

& $NSSM install $SERVICE_NAME "$VENV_DIR\Scripts\python.exe" `
    "-m" "uvicorn" "backend.main:app" "--host" "0.0.0.0" "--port" "$PORT"

& $NSSM set $SERVICE_NAME AppDirectory "$V2_DIR"
& $NSSM set $SERVICE_NAME AppEnvironmentExtra "PYTHONPATH=$V2_DIR"
& $NSSM set $SERVICE_NAME AppEnvironmentExtra "ENV_FILE=$ENV_FILE"
& $NSSM set $SERVICE_NAME AppStdout "$V2_DIR\logs\backend.log"
& $NSSM set $SERVICE_NAME AppStderr "$V2_DIR\logs\backend.log"
& $NSSM set $SERVICE_NAME AppRotateFiles 1
& $NSSM set $SERVICE_NAME AppRotateOnline 1
& $NSSM set $SERVICE_NAME AppRotateSeconds 86400
& $NSSM set $SERVICE_NAME Start SERVICE_AUTO_START
& $NSSM set $SERVICE_NAME DisplayName "AI00 柔性智能业务基座 Backend (V2)"
& $NSSM set $SERVICE_NAME Description "AI00 工艺系统云端后端 FastAPI 服务（V2 测试环境，端口 $PORT）"

Write-Host "  服务注册完成: $SERVICE_NAME" -ForegroundColor Green

# ── 6. 启动服务 ──────────────────────────────────────────────────────────
Write-Host "[6/6] 启动服务..." -ForegroundColor Yellow
net start $SERVICE_NAME
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [错误] 服务启动失败，请检查配置文件: $ENV_FILE" -ForegroundColor Red
    Write-Host "  日志: $V2_DIR\logs\backend.log" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "  初始化完成！" -ForegroundColor Cyan
Write-Host "  服务: $SERVICE_NAME" -ForegroundColor Cyan
Write-Host "  端口: $PORT" -ForegroundColor Cyan
Write-Host "  目录: $V2_DIR" -ForegroundColor Cyan
Write-Host "  健康检查: curl http://127.0.0.1:${PORT}/health" -ForegroundColor Cyan
Write-Host "  查看日志: type $V2_DIR\logs\backend.log" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "后续步骤:" -ForegroundColor White
Write-Host "  1. 编辑配置文件: notepad $ENV_FILE" -ForegroundColor White
Write-Host "  2. 填入敏感字段（JWT_SECRET, USERS_DB_URL, OIS_* 等）" -ForegroundColor White
Write-Host "  3. 重启服务: net stop $SERVICE_NAME && net start $SERVICE_NAME" -ForegroundColor White
Write-Host "  4. 创建 Gitea 仓库 deploy-v2 分支并推送" -ForegroundColor White
