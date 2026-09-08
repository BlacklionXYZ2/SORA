[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required but was not found on PATH. Run scripts/bootstrap.ps1 prerequisites first."
}

Push-Location $projectRoot
try {
    uv sync --locked --group dev
    uv run --locked ruff check src tests scripts/export-contracts.py
    uv run --locked mypy src tests scripts/export-contracts.py
    uv run --locked python scripts/export-contracts.py --check
    uv run --locked pytest
    uv run --locked python -m compileall -q src tests
}
finally {
    Pop-Location
}
