[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js is required to verify the P15.1 browser client."
}

Push-Location $projectRoot
try {
    & node "scripts/generate-pwa-icons.mjs" "--check"
    if ($LASTEXITCODE -ne 0) {
        throw "PWA icon verification failed with exit code $LASTEXITCODE"
    }
    foreach ($source in @(
        "src/sora/pwa/api-client.js",
        "src/sora/pwa/sync.js",
        "src/sora/pwa/device-vault.js",
        "src/sora/pwa/app.js",
        "src/sora/pwa/service-worker.js"
    )) {
        & node --check $source
        if ($LASTEXITCODE -ne 0) {
            throw "PWA syntax verification failed for $source with exit code $LASTEXITCODE"
        }
    }
    $tests = @(Get-ChildItem -LiteralPath "clients/pwa/tests" -Filter "*.test.mjs" |
        Sort-Object FullName |
        ForEach-Object FullName)
    & node --test $tests
    if ($LASTEXITCODE -ne 0) {
        throw "PWA browser tests failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
