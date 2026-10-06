[CmdletBinding()]
param()

# Web panels (clients/panels): syntax check every module, then the node:test suite.
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js is required to verify the web panels."
}

Push-Location $projectRoot
try {
    $modules = @(Get-ChildItem -LiteralPath "clients/panels" -Recurse -Filter "*.js" |
        Where-Object { $_.FullName -notmatch '[\\/]node_modules[\\/]' } |
        Sort-Object FullName | ForEach-Object FullName)
    foreach ($module in $modules) {
        & node --check $module
        if ($LASTEXITCODE -ne 0) { throw "Panel syntax check failed for $module" }
    }
    $tests = @(Get-ChildItem -LiteralPath "clients/panels/tests" -Filter "*.test.mjs" |
        Sort-Object FullName | ForEach-Object FullName)
    & node --test $tests
    if ($LASTEXITCODE -ne 0) { throw "Panel tests failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}
