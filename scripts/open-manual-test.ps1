[CmdletBinding()]
param(
    [ValidateSet("Desktop", "Widget", "Browser")]
    [string]$Client = "Desktop",
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765,
    [string]$StateRoot
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$testRoot = if ($StateRoot) { [IO.Path]::GetFullPath($StateRoot) } else { Join-Path $projectRoot ".local/manual-test" }
$tokenFile = Join-Path $testRoot "private/sora-api-token"
$coreUrl = "http://127.0.0.1:$Port"
if (-not (Test-Path -LiteralPath $tokenFile -PathType Leaf)) {
    throw "No manual-test token file exists. Start .\scripts\start-manual-test.ps1 first."
}
try {
    $token = (Get-Content -Raw -LiteralPath $tokenFile).Trim()
    $null = Invoke-RestMethod -Uri "$coreUrl/api/v1/status" -Headers @{
        Authorization = "Bearer $token"
    } -TimeoutSec 4
}
catch {
    throw "SORA Core is not reachable with this test token at $coreUrl. Check the Core terminal and -Port."
}

switch ($Client) {
    "Desktop" {
        $executable = Join-Path $projectRoot "clients/desktop_app/bin/Debug/net10.0-windows/SoraDesktop.exe"
        $settings = Join-Path $testRoot "desktop/settings.json"
    }
    "Widget" {
        $executable = Join-Path $projectRoot "clients/desktop_widget/bin/Debug/net10.0-windows/SoraWidget.exe"
        $settings = Join-Path $testRoot "widget/settings.json"
    }
    "Browser" {
        Write-Host "Opening $coreUrl/app"
        Write-Host "When prompted, paste the owner token from: $tokenFile"
        Write-Host "To display it locally: Get-Content -Raw -LiteralPath '$tokenFile'"
        Start-Process -FilePath "$coreUrl/app"
        return
    }
}

if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "The $Client client has not been built. Run .\scripts\start-manual-test.ps1 first."
}
Write-Host "Opening SORA $Client against $coreUrl. Close it from the window or tray when done."
& $executable --token-file $tokenFile --core-url $coreUrl --settings-file $settings
