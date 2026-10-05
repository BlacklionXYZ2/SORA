[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$oldProbeSetting = $env:SORA_TEST_CSHARP
Push-Location $projectRoot
try {
    dotnet build clients/protocol_probe --verbosity quiet
    if ($LASTEXITCODE -ne 0) { throw 'Portable transport/probe build failed' }
    dotnet test clients/csharp_tests --verbosity quiet
    if ($LASTEXITCODE -ne 0) { throw 'C# embodiment tests failed' }
    $env:SORA_TEST_CSHARP = '1'
    uv run --locked pytest tests/embodiment -q
    if ($LASTEXITCODE -ne 0) { throw 'Python/real C# transport tests failed' }
    uv run --locked python scripts/export-contracts.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Published contracts are stale' }
    Write-Output 'Headless P09 checks passed. Unity packaging, VRM and desktop hardware acceptance remain separate.'
}
finally {
    $env:SORA_TEST_CSHARP = $oldProbeSetting
    Pop-Location
}
