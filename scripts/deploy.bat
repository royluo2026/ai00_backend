@echo off
setlocal enabledelayedexpansion
echo [%date% %time%] AI00 V2 Deploy Script

set DEPLOY=E:\projects\ai00-v2
set WS=%1
if "%WS%"=="" set WS=%CD%

echo [1/6] robocopy backend
robocopy "%WS%\workmanship-backend\backend" "%DEPLOY%\backend" /MIR /XD __pycache__ /XF *.pyc .env* /NFL /NDL /NJH /NJS
echo exit=%ERRORLEVEL%

echo [2/6] robocopy plugins
robocopy "%WS%\workmanship-backend\plugins" "%DEPLOY%\plugins" /MIR /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS
echo exit=%ERRORLEVEL%

echo [3/6] robocopy dist
robocopy "%WS%\workmanship-web\dist" "%DEPLOY%\dist" /MIR /NFL /NDL /NJH /NJS
echo exit=%ERRORLEVEL%

echo [4/6] robocopy scripts
robocopy "%WS%\workmanship-backend\scripts" "%DEPLOY%\scripts" /MIR /NFL /NDL /NJH /NJS
echo exit=%ERRORLEVEL%

echo [5/6] nssm env
nssm set AI00Backend-V2 AppEnvironmentExtra "ENV_FILE=E:\projects\ai00-v2\backend\.env.v2.runtime" "PYTHONIOENCODING=utf-8"

echo [6/6] restart service
taskkill /F /FI "SERVICES eq AI00Backend-V2" 2>nul
timeout /t 3 /nobreak >nul
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul
net start AI00Backend-V2
timeout /t 8 /nobreak >nul
curl -f http://127.0.0.1:8082/health
echo ALL DONE
