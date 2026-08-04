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
nssm set AI00Backend-V2 AppEnvironmentExtra "ENV_FILE=E:\projects\ai00-v2\backend\.env.v2.runtime" "PYTHONIOENCODING=utf-8"
if errorlevel 1 exit /b !ERRORLEVEL!
net stop AI00Backend-V2 >nul 2>&1
timeout /t 3 /nobreak >nul
net start AI00Backend-V2
if errorlevel 1 exit /b !ERRORLEVEL!

echo [6/6] health check
timeout /t 15 /nobreak >nul
curl -fsS http://127.0.0.1:8082/health
if errorlevel 1 exit /b !ERRORLEVEL!

echo ALL DONE
exit /b 0