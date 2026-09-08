[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required but was not found on PATH. Install uv, then rerun this script."
}

Push-Location $projectRoot
try {
    uv sync --locked --group dev
}
finally {
    Pop-Location
}

