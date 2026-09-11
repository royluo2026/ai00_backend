param(
    [Parameter(Mandatory)] [string] $PrimaryPath,
    [Parameter(Mandatory)] [string] $InsertPath,
    [string] $VisMockupExe = 'D:\Siemens\Visualization14\Products\Mockup\VisView.exe'
)
$ErrorActionPreference = 'Stop'
foreach ($path in @($PrimaryPath, $InsertPath, $VisMockupExe)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "pilot_file_missing:$path" }
}
$project = Join-Path $PSScriptRoot 'VisMockupInsertProbe\VisMockupInsertProbe.csproj'
dotnet run --project $project -- `
    (Resolve-Path -LiteralPath $PrimaryPath).Path `
    (Resolve-Path -LiteralPath $InsertPath).Path `
    (Resolve-Path -LiteralPath $VisMockupExe).Path
if ($LASTEXITCODE -ne 0) { throw "vismockup_insert_pilot_failed:$LASTEXITCODE" }
