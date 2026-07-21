param(
    [switch]$Skip8081Stop
)

$ErrorActionPreference = "Stop"
$V2_DIR = "E:\projects\ai00-v2"
$SERVICE_NAME = "AI00Backend-V2"
$PORT = 8082
$OLD_SERVICE = "AI00Backend-Test"
$OLD_PORT = 8081

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  V2 Deploy Environment Setup" -ForegroundColor Cyan
Write-Host "  Target: $V2_DIR" -ForegroundColor Cyan
Write-Host "  Service: $SERVICE_NAME" -ForegroundColor Cyan
Write-Host "  Port: $PORT" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Stop old service
if (-not $Skip8081Stop) {
    Write-Host "[1/6] Stopping old service ${OLD_SERVICE} (port ${OLD_PORT})..." -ForegroundColor Yellow
    $oldSvc = Get-Service -Name $OLD_SERVICE -ErrorAction SilentlyContinue
    if ($oldSvc) {
        if ($oldSvc.Status -eq 'Running') {
            net stop $OLD_SERVICE
            Write-Host "  Old service stopped" -ForegroundColor Green
        }
        & nssm remove $OLD_SERVICE confirm
        Write-Host "  Old service removed" -ForegroundColor Green
    } else {
        Write-Host "  Old service not found, skip" -ForegroundColor Gray
    }
} else {
    Write-Host "[1/6] Skip old service stop (--Skip8081Stop)" -ForegroundColor Gray
}

# Step 2: Create directories
Write-Host "[2/6] Creating directories..." -ForegroundColor Yellow
$dirs = @(
    "$V2_DIR",
    "$V2_DIR\backend",
    "$V2_DIR\backend\static\uploads",
    "$V2_DIR\dist",
    "$V2_DIR\logs",
    "$V2_DIR\scripts"
)
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -Path $d -ItemType Directory -Force | Out-Null
        Write-Host "  Created: $d" -ForegroundColor Gray
    }
}

# Step 3: Generate runtime config
Write-Host "[3/6] Generating runtime config..." -ForegroundColor Yellow
$ENV_FILE = "$V2_DIR\backend\.env.v2.runtime"
if (-not (Test-Path $ENV_FILE)) {
    @"
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
    Write-Host "  Config template created: $ENV_FILE" -ForegroundColor Green
    Write-Host "  !!! Please fill in: JWT_SECRET, USERS_DB_URL, OIS_* etc." -ForegroundColor Yellow
} else {
    Write-Host "  Config already exists, skip: $ENV_FILE" -ForegroundColor Gray
}

# Step 4: Create Python venv
Write-Host "[4/6] Creating Python venv..." -ForegroundColor Yellow
$VENV_DIR = "$V2_DIR\venv"
if (-not (Test-Path "$VENV_DIR\Scripts\python.exe")) {
    python -m venv $VENV_DIR
    Write-Host "  venv created" -ForegroundColor Green
} else {
    Write-Host "  venv already exists, skip" -ForegroundColor Gray
}

# Step 5: Register Windows service with NSSM
Write-Host "[5/6] Registering Windows service..." -ForegroundColor Yellow
$NSSM = Get-Command nssm -ErrorAction SilentlyContinue
if (-not $NSSM) {
    $nssmPaths = @(
        "$env:LOCALAPPDATA\Microsoft\WinGet\links\nssm.exe",
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
    Write-Host "  [ERROR] nssm.exe not found. Install: winget install NSSM" -ForegroundColor Red
    exit 1
}
Write-Host "  NSSM: $NSSM" -ForegroundColor Gray

$svc = Get-Service -Name $SERVICE_NAME -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "  Service exists, re-registering..." -ForegroundColor Yellow
    net stop $SERVICE_NAME 2>$null
    & $NSSM remove $SERVICE_NAME confirm
}

& $NSSM install $SERVICE_NAME "$VENV_DIR\Scripts\python.exe" "-m" "uvicorn" "backend.main:app" "--host" "0.0.0.0" "--port" "$PORT"
& $NSSM set $SERVICE_NAME AppDirectory "$V2_DIR"
& $NSSM set $SERVICE_NAME AppEnvironmentExtra "PYTHONPATH=$V2_DIR"
& $NSSM set $SERVICE_NAME AppEnvironmentExtra "ENV_FILE=$ENV_FILE"
& $NSSM set $SERVICE_NAME AppStdout "$V2_DIR\logs\backend.log"
& $NSSM set $SERVICE_NAME AppStderr "$V2_DIR\logs\backend.log"
& $NSSM set $SERVICE_NAME AppRotateFiles 1
& $NSSM set $SERVICE_NAME AppRotateOnline 1
& $NSSM set $SERVICE_NAME AppRotateSeconds 86400
& $NSSM set $SERVICE_NAME Start SERVICE_AUTO_START
& $NSSM set $SERVICE_NAME DisplayName "AI00 Backend V2 (Test $PORT)"

Write-Host "  Service registered: $SERVICE_NAME" -ForegroundColor Green

# Step 6: Start service
Write-Host "[6/6] Starting service..." -ForegroundColor Yellow
net start $SERVICE_NAME
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] Service start failed. Check config: $ENV_FILE" -ForegroundColor Red
    Write-Host "  Log: $V2_DIR\logs\backend.log" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Setup complete!" -ForegroundColor Cyan
Write-Host "  Service: $SERVICE_NAME" -ForegroundColor Cyan
Write-Host "  Port: $PORT" -ForegroundColor Cyan
Write-Host "  Dir: $V2_DIR" -ForegroundColor Cyan
Write-Host "  Health check: curl http://127.0.0.1:${PORT}/health" -ForegroundColor Cyan
Write-Host "  Log: type $V2_DIR\logs\backend.log" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. Edit config: notepad $ENV_FILE" -ForegroundColor White
Write-Host "  2. Fill in: JWT_SECRET, USERS_DB_URL, OIS_* etc." -ForegroundColor White
Write-Host "  3. Restart service: net stop $SERVICE_NAME; net start $SERVICE_NAME" -ForegroundColor White
