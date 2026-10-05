[CmdletBinding()]
param([switch]$Native)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$previous = $env:SORA_TEST_UIA
Push-Location $root
try {
    dotnet build clients/windows_bridge --verbosity quiet
    if ($LASTEXITCODE -ne 0) { throw 'Windows bridge build failed' }
    dotnet build clients/windows_action --verbosity quiet
    if ($LASTEXITCODE -ne 0) { throw 'Windows action bridge build failed' }
    dotnet build clients/windows_type --verbosity quiet
    if ($LASTEXITCODE -ne 0) { throw 'Windows TYPE bridge build failed' }
    dotnet build clients/windows_capture --verbosity quiet
    if ($LASTEXITCODE -ne 0) { throw 'Windows capture bridge build failed' }
    if ($Native) {
        dotnet build clients/uia_fixture --verbosity quiet
        if ($LASTEXITCODE -ne 0) { throw 'UIA fixture build failed' }
        dotnet build clients/media_fixture --verbosity quiet
        if ($LASTEXITCODE -ne 0) { throw 'Media fixture build failed' }
        $env:SORA_TEST_UIA = '1'
    }
    uv run --locked pytest tests/desktop tests/vision -q
    if ($LASTEXITCODE -ne 0) { throw 'Desktop verification failed' }
}
finally {
    $env:SORA_TEST_UIA = $previous
    Pop-Location
}
