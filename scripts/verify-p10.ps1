[CmdletBinding()]
param([switch]$Full)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$bridge = Join-Path $projectRoot 'clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe'
$oldElevated = $env:SORA_TEST_ELEVATED_PID
$oldInaccessible = $env:SORA_TEST_INACCESSIBLE_PID
$oldUia = $env:SORA_TEST_UIA
$oldCsharp = $env:SORA_TEST_CSHARP

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

Push-Location $projectRoot
try {
    Invoke-Checked dotnet build clients/windows_bridge --verbosity quiet
    Invoke-Checked dotnet build clients/uia_fixture --verbosity quiet

    $integrity = (whoami /groups) -join "`n"
    if ($integrity -notmatch 'Medium Mandatory Level') {
        throw 'P10 live privilege matrix requires a non-elevated medium-integrity caller.'
    }

    $elevated = $null
    $inaccessible = $null
    foreach ($process in (Get-Process | Sort-Object Id)) {
        if ($process.Id -lt 1) { continue }
        $request = @{
            schema_version = '1.0'
            operation = 'windows'
            process_id = $process.Id
            window_handle = $null
            max_nodes = 1
            max_depth = 0
        } | ConvertTo-Json -Compress
        try {
            $response = (($request | & $bridge) | ConvertFrom-Json)
        }
        catch {
            continue
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Windows bridge probe failed with exit code $LASTEXITCODE"
        }
        if ($response.status -eq 'elevated_target' -and $null -eq $elevated) {
            $elevated = [pscustomobject]@{ pid = $process.Id; process = $process.ProcessName }
        }
        if ($response.status -eq 'access_denied' -and $null -eq $inaccessible) {
            $inaccessible = [pscustomobject]@{ pid = $process.Id; process = $process.ProcessName }
        }
        if ($null -ne $elevated -and $null -ne $inaccessible) { break }
    }
    if ($null -eq $elevated) {
        throw 'No live elevated process was available for P10 acceptance.'
    }
    if ($null -eq $inaccessible) {
        throw 'No live inaccessible process was available for P10 acceptance.'
    }

    $env:SORA_TEST_ELEVATED_PID = [string]$elevated.pid
    $env:SORA_TEST_INACCESSIBLE_PID = [string]$inaccessible.pid
    Invoke-Checked uv run --locked pytest tests/desktop/test_observation.py::test_live_elevated_and_inaccessible_process_matrix -q
    & (Join-Path $PSScriptRoot 'verify-desktop.ps1') -Native
    if ($LASTEXITCODE -ne 0) { throw 'Native P10 desktop gate failed' }
    if ($Full) {
        $env:SORA_TEST_UIA = '1'
        $env:SORA_TEST_CSHARP = '1'
        Invoke-Checked uv run --locked pytest -q
    }

    $evidenceRoot = Join-Path $projectRoot 'docs/verification/p10-windows-bridge'
    New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null
    [pscustomobject]@{
        recorded_at = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ssK')
        caller_integrity = 'medium'
        caller_elevated = $false
        elevated_target = $elevated
        inaccessible_target = $inaccessible
        elevated_status = 'elevated_target'
        inaccessible_status = 'access_denied'
        helper_requested_elevation = $false
        window_titles_recorded = $false
        full_native_suite = [bool]$Full
    } | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $evidenceRoot 'live-privilege-matrix.json')
}
finally {
    $env:SORA_TEST_ELEVATED_PID = $oldElevated
    $env:SORA_TEST_INACCESSIBLE_PID = $oldInaccessible
    $env:SORA_TEST_UIA = $oldUia
    $env:SORA_TEST_CSHARP = $oldCsharp
    Pop-Location
}
