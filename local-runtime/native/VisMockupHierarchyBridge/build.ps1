$ErrorActionPreference = 'Stop'
$compiler = (Get-Command g++.exe -ErrorAction Stop).Source
$source = Join-Path $PSScriptRoot 'bridge.cpp'
$output = Join-Path $PSScriptRoot 'Ai00.VisMockup.HierarchyBridge.dll'
& $compiler -std=c++20 -O2 -shared -static -static-libgcc -static-libstdc++ -municode '-Wl,--no-insert-timestamp' $source -lole32 -loleaut32 -o $output
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Get-FileHash -Algorithm SHA256 $output | Select-Object Path,Hash
