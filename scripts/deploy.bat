@echo off
setlocal enabledelayedexpansion
echo [%date% %time%] AI00 V2 Deploy Script

set DEPLOY=E:\projects\ai00-v2
set WS=%1
if "%WS%"=="" set WS=%CD%

echo [1/6] robocopy backend
robocopy "%WS%\workmanship-backend\backend" "%DEPLOY%\backend" /MIR /XD __pycache__ /XF *.pyc .env* /NFL /NDL /NJH /NJS
if errorlevel 8 exit /b !ERRORLEVEL!

echo [2/6] robocopy plugins
robocopy "%WS%\workmanship-backend\plugins" "%DEPLOY%\plugins" /MIR /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS
if errorlevel 8 exit /b !ERRORLEVEL!

echo [3/6] robocopy dist
robocopy "%WS%\workmanship-web\dist" "%DEPLOY%\dist" /MIR /NFL /NDL /NJH /NJS
if errorlevel 8 exit /b !ERRORLEVEL!

echo [4/6] robocopy scripts
robocopy "%WS%\workmanship-backend\scripts" "%DEPLOY%\scripts" /MIR /NFL /NDL /NJH /NJS
if errorlevel 8 exit /b !ERRORLEVEL!

echo [5/6] configure and restart service
set RUNTIME_ENV_FILE=E:\projects\ai00-v2\backend\.env.v2.runtime
set MIGRATION_ENV_FILE=E:\projects\ai00-v2\backend\.env.v2.migration
E:\projects\ai00-v2\venv\Scripts\python.exe "%DEPLOY%\backend\scripts\runtime_preflight.py" --env-file "%RUNTIME_ENV_FILE%"
if errorlevel 1 exit /b !ERRORLEVEL!
set ENV_FILE=%MIGRATION_ENV_FILE%
E:\projects\ai00-v2\venv\Scripts\python.exe "%DEPLOY%\backend\scripts\run_migrations.py"
if errorlevel 1 exit /b !ERRORLEVEL!
set ENV_FILE=%RUNTIME_ENV_FILE%
nssm set AI00Backend-V2 AppEnvironmentExtra "ENV_FILE=E:\projects\ai00-v2\backend\.env.v2.runtime" "PYTHONIOENCODING=utf-8"
if errorlevel 1 exit /b !ERRORLEVEL!
powershell -NoProfile -Command "$p=Start-Process nssm -ArgumentList 'restart','AI00Backend-V2' -PassThru -WindowStyle Hidden; if (-not $p.WaitForExit(15000)) { $p.Kill(); exit 124 }; exit $p.ExitCode"
if errorlevel 1 (
  echo Normal restart failed or timed out; recovering only AI00Backend-V2.
  set SERVICE_PID=
  for /f "tokens=3" %%P in ('sc queryex AI00Backend-V2 ^| findstr /R /C:"PID *:"') do set SERVICE_PID=%%P
  if defined SERVICE_PID if not "!SERVICE_PID!"=="0" (
    taskkill /PID !SERVICE_PID! /F
    if errorlevel 1 exit /b !ERRORLEVEL!
    timeout /t 2 /nobreak >nul
  )
  nssm start AI00Backend-V2
  if errorlevel 1 exit /b !ERRORLEVEL!
)

echo [6/6] readiness check
set HEALTH_OK=
for /L %%I in (1,1,12) do (
  curl -fsS --max-time 5 http://127.0.0.1:8082/ready >nul 2>&1 && set HEALTH_OK=1 && goto health_ready
  timeout /t 5 /nobreak >nul
)
exit /b 1

:health_ready
curl -fsS --max-time 5 http://127.0.0.1:8082/ready
if errorlevel 1 exit /b !ERRORLEVEL!

echo ALL DONE
exit /b 0