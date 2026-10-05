[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Bundle,
    [string]$WorkRoot,
    [switch]$RequireWidget,
    [switch]$RequireDesktop
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$bundleRoot = [System.IO.Path]::GetFullPath($Bundle)
$widgetIncluded = Test-Path -LiteralPath (Join-Path $bundleRoot "payload/clients/widget/SoraWidget.exe") -PathType Leaf
if ($RequireWidget -and -not $widgetIncluded) { throw "The release bundle lacks SoraWidget.exe." }
$desktopIncluded = Test-Path -LiteralPath (Join-Path $bundleRoot "payload/clients/desktop/SoraDesktop.exe") -PathType Leaf
if ($RequireDesktop -and -not $desktopIncluded) { throw "The release bundle lacks SoraDesktop.exe." }
if (-not $WorkRoot) {
    $WorkRoot = Join-Path $projectRoot (".local/p15.3-release-acceptance-" + [guid]::NewGuid())
}
$work = [System.IO.Path]::GetFullPath($WorkRoot)
if (Test-Path -LiteralPath $work) { throw "Release acceptance work root must not already exist: $work" }
$profile = Join-Path $work "profile"
$install = Join-Path $profile "AppData/Local/SORA/app"
$state = Join-Path $profile "AppData/Local/SORA/state"
$startup = Join-Path $profile "AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/SORA.cmd"
$upgradeBundle = Join-Path $work "upgrade-bundle"
New-Item -ItemType Directory -Force $profile | Out-Null

$portablePython = Join-Path $bundleRoot "payload/core/python/python.exe"
& $portablePython -B -m sora.operations.cli verify-manifest --bundle $bundleRoot | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Initial bundle integrity verification failed." }

& (Join-Path $bundleRoot "install.ps1") -InstallRoot $install -StateRoot $state `
    -StartupEntry $startup -EnableStartup
if ($LASTEXITCODE -ne 0) { throw "Clean-profile installation failed." }
if (-not (Test-Path -LiteralPath $startup -PathType Leaf)) { throw "Optional startup entry was not created." }
if ($widgetIncluded) {
    $widgetLauncher = Join-Path $install "bin/sora-widget.ps1"
    $installedPointer = Get-Content -Raw -LiteralPath (Join-Path $install "current.json") | ConvertFrom-Json
    $widgetExecutable = Join-Path (Join-Path (Join-Path $install "versions") $installedPointer.release_id) "clients/widget/SoraWidget.exe"
    if (-not (Test-Path -LiteralPath $widgetLauncher -PathType Leaf) -or
        -not (Test-Path -LiteralPath $widgetExecutable -PathType Leaf)) {
        throw "The installed release lacks its widget executable or stable launcher."
    }
    $widgetSettings = Join-Path $state "widget/settings.json"
    New-Item -ItemType Directory -Force (Split-Path -Parent $widgetSettings) | Out-Null
    $settingsSentinel = '{"Anchor":0,"Quiet":true,"acceptance":"widget-preferences-retained"}'
    [System.IO.File]::WriteAllText($widgetSettings, $settingsSentinel, [System.Text.UTF8Encoding]::new($false))
}
if ($desktopIncluded) {
    $desktopLauncher = Join-Path $install "bin/sora-desktop.ps1"
    $installedPointer = Get-Content -Raw -LiteralPath (Join-Path $install "current.json") | ConvertFrom-Json
    $desktopExecutable = Join-Path (Join-Path (Join-Path $install "versions") $installedPointer.release_id) "clients/desktop/SoraDesktop.exe"
    if (-not (Test-Path -LiteralPath $desktopLauncher -PathType Leaf) -or
        -not (Test-Path -LiteralPath $desktopExecutable -PathType Leaf)) {
        throw "The installed release lacks its full-app executable or stable launcher."
    }
    $desktopSettings = Join-Path $state "desktop/settings.json"
    New-Item -ItemType Directory -Force (Split-Path -Parent $desktopSettings) | Out-Null
    $desktopSentinel = '{"ShowTechnicalDetail":false,"acceptance":"desktop-preferences-retained"}'
    [System.IO.File]::WriteAllText($desktopSettings, $desktopSentinel, [System.Text.UTF8Encoding]::new($false))
}

$launcher = Join-Path $install "bin/sora.ps1"
& $launcher --once "P15.3 state-preserving upgrade sentinel" --wait
if ($LASTEXITCODE -ne 0) { throw "Installed portable Core could not create the upgrade sentinel." }
$before = & $launcher --messages
if ($LASTEXITCODE -ne 0 -or ($before -join "`n") -notmatch "P15.3 state-preserving upgrade sentinel") {
    throw "Installed state does not contain the upgrade sentinel."
}

Copy-Item -LiteralPath $bundleRoot -Destination $upgradeBundle -Recurse
$upgradeManifest = Join-Path $upgradeBundle "release-manifest.json"
Remove-Item -LiteralPath $upgradeManifest
$upgradePython = Join-Path $upgradeBundle "payload/core/python/python.exe"
$metadata = Join-Path $upgradeBundle "release-metadata.json"
$upgradeId = "p15.3-upgrade-" + [guid]::NewGuid().ToString("N")
& $upgradePython -B -m sora.operations.cli build-manifest `
    --bundle $upgradeBundle --release-id $upgradeId --metadata $metadata | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Upgrade fixture manifest generation failed." }
& (Join-Path $upgradeBundle "update.ps1") -InstallRoot $install -StateRoot $state `
    -StartupEntry $startup
if ($LASTEXITCODE -ne 0) { throw "State-preserving update failed." }
$after = & $launcher --messages
if ($LASTEXITCODE -ne 0 -or ($after -join "`n") -notmatch "P15.3 state-preserving upgrade sentinel") {
    throw "Upgrade did not preserve the sentinel."
}
if ($widgetIncluded -and (Get-Content -Raw -LiteralPath $widgetSettings) -ne $settingsSentinel) {
    throw "Update did not preserve widget preferences."
}
if ($desktopIncluded -and (Get-Content -Raw -LiteralPath $desktopSettings) -ne $desktopSentinel) {
    throw "Update did not preserve full-app preferences."
}

& (Join-Path $upgradeBundle "rollback.ps1") -InstallRoot $install -StateRoot $state `
    -StartupEntry $startup
if ($LASTEXITCODE -ne 0) { throw "Rollback failed." }
$rolledBack = & $launcher --messages
if ($LASTEXITCODE -ne 0 -or ($rolledBack -join "`n") -notmatch "P15.3 state-preserving upgrade sentinel") {
    throw "Rollback did not restore the prior release/state pair."
}
if ($widgetIncluded -and (Get-Content -Raw -LiteralPath $widgetSettings) -ne $settingsSentinel) {
    throw "Rollback did not preserve widget preferences."
}
if ($desktopIncluded -and (Get-Content -Raw -LiteralPath $desktopSettings) -ne $desktopSentinel) {
    throw "Rollback did not preserve full-app preferences."
}

& (Join-Path $bundleRoot "uninstall.ps1") -InstallRoot $install -StateRoot $state `
    -StartupEntry $startup
if ($LASTEXITCODE -ne 0) { throw "Data-preserving uninstall failed." }
if (Test-Path -LiteralPath $install) { throw "Uninstall left the application root behind." }
if (-not (Test-Path -LiteralPath $state)) { throw "Default uninstall removed personal state." }
if (Test-Path -LiteralPath $startup) { throw "Uninstall left the startup entry behind." }
if ($widgetIncluded -and (Get-Content -Raw -LiteralPath $widgetSettings) -ne $settingsSentinel) {
    throw "Data-retaining uninstall removed widget preferences."
}
if ($desktopIncluded -and (Get-Content -Raw -LiteralPath $desktopSettings) -ne $desktopSentinel) {
    throw "Data-retaining uninstall removed full-app preferences."
}

& (Join-Path $bundleRoot "install.ps1") -InstallRoot $install -StateRoot $state `
    -StartupEntry $startup
if ($LASTEXITCODE -ne 0) { throw "Reinstall against retained state failed." }
$reinstalled = & $launcher --messages
if ($LASTEXITCODE -ne 0 -or ($reinstalled -join "`n") -notmatch "P15.3 state-preserving upgrade sentinel") {
    throw "Reinstall did not recover retained personal state."
}
if ($widgetIncluded -and (Get-Content -Raw -LiteralPath $widgetSettings) -ne $settingsSentinel) {
    throw "Reinstall did not recover widget preferences."
}
if ($desktopIncluded -and (Get-Content -Raw -LiteralPath $desktopSettings) -ne $desktopSentinel) {
    throw "Reinstall did not recover full-app preferences."
}

$evidence = [ordered]@{
    status = "passed"
    bundle = $bundleRoot
    isolated_profile = $profile
    clean_install = "passed"
    portable_core = "passed"
    optional_startup = "passed"
    state_preserving_upgrade = "passed"
    rollback = "passed"
    uninstall_retains_data = "passed"
    reinstall_recovers_data = "passed"
    packaged_widget_and_launcher = $(if ($widgetIncluded) { "passed" } else { "not_applicable" })
    widget_preferences_survive_lifecycle = $(if ($widgetIncluded) { "passed" } else { "not_applicable" })
    packaged_full_app_and_launcher = $(if ($desktopIncluded) { "passed" } else { "not_applicable" })
    full_app_preferences_survive_lifecycle = $(if ($desktopIncluded) { "passed" } else { "not_applicable" })
}
$evidencePath = Join-Path $work "acceptance.json"
$evidence | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $evidencePath -Encoding utf8
Write-Host "Release acceptance passed: $evidencePath"
