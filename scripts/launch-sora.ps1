[CmdletBinding()]
param(
    # Only for testing the shortcut on an isolated profile; the owner's shortcut passes nothing.
    [string]$StateRoot,
    [int]$Port
)

# What the Desktop "SORA" shortcut runs (scripts/install-shortcut.ps1 creates it).
#
# It starts SORA the way the owner uses her: the native host with no window, her avatar on the
# desktop, the managed local model, and the tray icon. Opening it again while SORA runs shows her
# command menu (Start-SORA.ps1 forwards it to the running host).
#
# The shortcut runs PowerShell hidden, so nothing here may wait for input, and every failure is
# shown in a message box and written to .local/launch/ rather than lost with a closed console.
# Windows PowerShell 5.1 compatible.

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$logRoot = Join-Path $projectRoot ".local/launch"
New-Item -ItemType Directory -Force $logRoot | Out-Null
$log = Join-Path $logRoot ("launch-" + (Get-Date -Format "yyyy-MM-dd") + ".log")
Add-Type -AssemblyName System.Windows.Forms

function Write-LaunchLog([string]$Text) {
    Add-Content -LiteralPath $log -Encoding UTF8 -Value ("[" + (Get-Date -Format "HH:mm:ss") + "] " + $Text)
}

function Show-Problem([string]$Text) {
    Write-LaunchLog ("Stopped: " + $Text)
    [void][System.Windows.Forms.MessageBox]::Show(
        $Text + "`n`nDetails: " + $log, "SORA could not start",
        [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
}

# Problems the owner can fix, found before anything starts. Each names the fix in HOW_TO_USE.md.
function Find-SetupProblems {
    $problems = @()
    foreach ($command in @("uv", "dotnet")) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
            $problems += "$command is not installed or not on PATH. Run .\scripts\bootstrap.ps1."
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "clients/unity/Builds/Windows/SORA.exe"))) {
        $problems += "Her avatar is not built. Run .\scripts\build-embodiment.ps1 once."
    }
    return $problems
}

Write-LaunchLog ("Launch requested" + $(if ($StateRoot) { " for $StateRoot" } else { "" }))
try {
    $problems = @(Find-SetupProblems)
    if ($problems.Count) { Show-Problem ($problems -join "`n"); exit 1 }
    $arguments = @{}
    if ($StateRoot) { $arguments.StateRoot = $StateRoot }
    if ($Port) { $arguments.Port = $Port }
    # Start-SORA builds the host if needed, starts it and returns; the host owns Core, the model
    # and the avatar from then on. Its own output goes to the log.
    & (Join-Path $projectRoot "Start-SORA.ps1") @arguments 6>&1 | ForEach-Object { Write-LaunchLog "$_" }
    Write-LaunchLog "Host started."
}
catch {
    Show-Problem ("SORA did not start: " + $_.Exception.Message)
    exit 1
}
