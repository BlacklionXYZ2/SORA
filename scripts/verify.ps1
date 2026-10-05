[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

function Invoke-UvChecked {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & uv @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "uv $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required but was not found on PATH. Run scripts/bootstrap.ps1 prerequisites first."
}

Push-Location $projectRoot
try {
    Invoke-UvChecked @("sync", "--locked", "--group", "dev")
    Invoke-UvChecked @(
        "run",
        "--locked",
        "ruff",
        "check",
        "src",
        "tests",
        "scripts/export-contracts.py",
        "scripts/benchmark-voice.py",
        "scripts/capture-gui-baseline.py",
        "scripts/verify-gui-shell.py"
    )
    Invoke-UvChecked @("run", "--locked", "mypy", "src", "tests", "scripts/export-contracts.py",
        "scripts/capture-gui-baseline.py", "scripts/verify-gui-shell.py")
    Invoke-UvChecked @("run", "--locked", "python", "scripts/export-contracts.py", "--check")
    Invoke-UvChecked @("run", "--locked", "pytest")
    Invoke-UvChecked @("run", "--locked", "python", "-m", "compileall", "-q", "src", "tests")
    & "$PSScriptRoot/verify-pwa.ps1"
    if ($LASTEXITCODE -ne 0) {
        throw "scripts/verify-pwa.ps1 failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
