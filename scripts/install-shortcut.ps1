[CmdletBinding()]
param(
    # Where to put the shortcut. Default: the owner's Desktop.
    [string]$Folder = [Environment]::GetFolderPath("Desktop"),
    [string]$Name = "SORA"
)

# Creates the "SORA" shortcut that starts SORA in full (scripts/launch-sora.ps1): no console
# window, her avatar on the desktop, the tray icon and the local model. Opening it again while
# SORA runs shows her command menu. Run it once; it never replaces a shortcut it did not make.
# Windows PowerShell 5.1 compatible.

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $projectRoot "scripts/launch-sora.ps1"
$icon = Join-Path $projectRoot "assets/sora.ico"
$path = Join-Path $Folder "$Name.lnk"
$powershell = Join-Path $env:SystemRoot "System32/WindowsPowerShell/v1.0/powershell.exe"
$arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`""

$shell = New-Object -ComObject WScript.Shell
if (Test-Path -LiteralPath $path) {
    $existing = $shell.CreateShortcut($path)
    if ($existing.Arguments -notlike "*launch-sora.ps1*") {
        throw "$path already exists and is not SORA's shortcut. Move it, or choose -Name."
    }
}
$shortcut = $shell.CreateShortcut($path)
$shortcut.TargetPath = $powershell
$shortcut.Arguments = $arguments
$shortcut.WorkingDirectory = $projectRoot
$shortcut.WindowStyle = 7  # minimised: no console flashes up while PowerShell hides itself
$shortcut.Description = "Start SORA"
if (Test-Path -LiteralPath $icon) { $shortcut.IconLocation = "$icon,0" }
$shortcut.Save()
Write-Host "Created $path"
