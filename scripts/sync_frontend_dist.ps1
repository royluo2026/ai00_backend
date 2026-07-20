param(
  [string]$FrontendDir = ""
)

$ErrorActionPreference = 'Stop'

$BackendDir = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($FrontendDir)) {
  if ($env:FRONTEND_DIR) {
    $FrontendDir = $env:FRONTEND_DIR
  } else {
    $FrontendDir = Join-Path (Split-Path -Parent $BackendDir) 'workmanship-web'
  }
}

$FrontendDir = [System.IO.Path]::GetFullPath($FrontendDir)
$FrontendPkg = Join-Path $FrontendDir 'package.json'
$FrontendNodeModules = Join-Path $FrontendDir 'node_modules'
$FrontendDist = Join-Path $FrontendDir 'dist'
$BackendDist = Join-Path $BackendDir 'dist'

if (-not (Test-Path $FrontendPkg)) {
  Write-Error "[sync_frontend_dist] 未找到前端 package.json: $FrontendDir`n[sync_frontend_dist] 可通过 `-FrontendDir` 或环境变量 FRONTEND_DIR 指定前端目录"
}

if (-not (Test-Path $FrontendNodeModules)) {
  Write-Error "[sync_frontend_dist] 前端 node_modules 不存在，请先在前端目录执行 npm ci"
}

Write-Host "[sync_frontend_dist] 前端目录: $FrontendDir"
Write-Host "[sync_frontend_dist] 构建前端 dist..."
Push-Location $FrontendDir
try {
  npm run build:web --silent
} finally {
  Pop-Location
}

if (-not (Test-Path $FrontendDist)) {
  Write-Error "[sync_frontend_dist] 前端 dist 不存在，构建可能失败"
}

Write-Host "[sync_frontend_dist] 同步 dist → backend"
if (Test-Path $BackendDist) {
  Remove-Item -Recurse -Force $BackendDist
}
Copy-Item -Recurse -Force $FrontendDist $BackendDist

Write-Host "[sync_frontend_dist] 完成"
Write-Host "[sync_frontend_dist] 下一步请执行: git add -A dist"
