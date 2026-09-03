param(
    [Parameter(Mandatory)] [string] $CasePath,
    [Parameter(Mandatory)] [string] $AccessToken
)
$ErrorActionPreference = 'Stop'
$pilot = Get-Content -LiteralPath $CasePath -Raw | ConvertFrom-Json
if (-not $pilot.ai00_base.StartsWith('https://')) { throw 'pilot_https_required' }
$headers = @{ Authorization = "Bearer $AccessToken"; 'Content-Type' = 'application/json' }
$body = @{
    environment_id = $pilot.environment_id
    environment_version = $pilot.environment_version
    device_id = $pilot.device_id
} | ConvertTo-Json
$start = Invoke-RestMethod -Method Post -Headers $headers -Uri "$($pilot.ai00_base)/api/simulation/capture-runs" -Body $body
$captureRunId = $start.data.capture_run_id
if (-not $captureRunId) { throw 'capture_run_missing' }
do {
    Start-Sleep -Seconds 2
    $result = Invoke-RestMethod -Headers $headers -Uri "$($pilot.ai00_base)/api/simulation/capture-runs/$captureRunId"
    if ($result.data.status -eq 'failed') { throw "capture_failed:$captureRunId" }
} while ($result.data.status -notin @('completed', 'cancelled'))
$actualOrder = @($result.data.steps.operation_id) -join ','
$expectedOrder = @($pilot.expected_operation_ids) -join ','
if ($actualOrder -ne $expectedOrder) { throw "capture_order_mismatch:$actualOrder" }
if (@($result.data.steps | Where-Object { $_.status -ne 'completed' -or -not $_.artifact_attached }).Count -ne 0) { throw 'capture_attach_incomplete' }
if (@($result.data.steps | Where-Object { -not $_.artifact_ref.sha256 -or $_.artifact_ref.media_type -ne 'image/png' }).Count -ne 0) { throw 'capture_artifact_invalid' }
[pscustomobject]@{ capture_run_id = $captureRunId; status = $result.data.status; operation_ids = @($result.data.steps.operation_id) }
