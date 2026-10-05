[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$voiceEnvironment = Join-Path $projectRoot ".local/voice-runtime"
$previousEnvironment = $env:UV_PROJECT_ENVIRONMENT
Push-Location $projectRoot
try {
    $env:UV_PROJECT_ENVIRONMENT = $voiceEnvironment
    & uv sync --locked --extra voice
    if ($LASTEXITCODE -ne 0) { throw "Local speech dependencies could not be installed." }
    Write-Host "Local voice runtime ready. Existing speech weights are reused; no model is downloaded."
}
finally {
    $env:UV_PROJECT_ENVIRONMENT = $previousEnvironment
    Pop-Location
}
