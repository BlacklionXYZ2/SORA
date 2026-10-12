# Full SORA launcher: Core with every current Windows helper wired.
#
# Both this script and Start-SORA.ps1 wire the press/type action
# helpers, so desktop observation, capture, vision, targets, press and type are all
# reachable on a normal start (they answer "not_configured" without these flags).
#
# Chat features reachable from this launch: pose keywords (sit/lean/climb/stand),
# walking the companion to your pointer ("come here", "walk to me"), and looking at
# the current screen when asked ("what can you see?"), which captures the display
# under the cursor for the selected vision-capable dialogue model.
#
# Compatibility clients run Core in its own PowerShell window. Press Ctrl+C
# there to stop Core (its avatar closes with it). Opt-in Shell instead owns a
# hidden fixed-script launch and exposes graceful owned Quit in its command menu.
#
#   .\scripts\start-full-sora.ps1                  # Core + helpers + avatar + desktop app
#   .\scripts\start-full-sora.ps1 -NoClient        # ...without opening the GUI
#   .\scripts\start-full-sora.ps1 -NoAvatar        # no 3D companion
#   .\scripts\start-full-sora.ps1 -Client Widget   # open the compact widget instead
#   .\scripts\start-full-sora.ps1 -Client Shell    # windowless managed profile host
#   .\scripts\start-full-sora.ps1 -CodexModel gpt-6-luna -AntigravityEffort medium
#
# The desktop app (Chat, Activity, Content, Integrations, Settings, Companion tabs)
# opens against the Core API once the Core window reports ready.

[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765,
    [string]$CodexModel = "gpt-5.6-luna",
    [string]$AntigravityModel = "gpt-oss-120b-medium",
    [ValidateSet("low", "medium", "high")]
    [string]$AntigravityEffort = "low",
    [switch]$NoAntigravitySkipPermissions,
    [string]$Settings,
    [string]$StateRoot,
    [string]$AvatarPath,
    [string]$WorkspaceRoot,
    [string]$WriteRepo,
    [ValidateRange(30, 3600)]
    [int]$TaskTimeout = 300,
    [switch]$NoAvatar,
    [switch]$NoClient,
    [ValidateSet("Desktop", "Widget", "Browser", "Shell")]
    [string]$Client = "Shell",
    [switch]$SetupVoice,
    [ValidateSet("none", "chat", "voice", "memory", "activity", "agents", "paths", "board", "content", "integrations", "settings", "appearance", "menu", "quit")]
    [string]$ShellPanel = "none",
    [ValidateSet("auto", "deterministic")]
    [string]$Provider = "auto"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
# The native app is the ordinary client (V1). It owns SORA's lifetime, so a headless
# -NoClient start without an explicit client keeps the plain Core path.
if ($NoClient -and -not $PSBoundParameters.ContainsKey('Client')) { $Client = "Desktop" }
if ($Client -eq "Shell") {
    # Delegate before helper builds, setup or default-port selection. Only the
    # singleton primary may start services, using the fixed typed manual script.
    $shellParameters = @{
        Client = "Shell"; ShellPanel = $ShellPanel; Provider = $Provider
        CodexModel = $CodexModel; AntigravityModel = $AntigravityModel
        AntigravityEffort = $AntigravityEffort
        AntigravitySkipPermissions = -not $NoAntigravitySkipPermissions
        TaskTimeout = $TaskTimeout; NoAvatar = $NoAvatar; SetupVoice = $SetupVoice
        NoClient = $NoClient
        UnifiedSettingsOnly = $true
    }
    foreach ($selection in @("StateRoot", "Settings", "AvatarPath", "WorkspaceRoot", "WriteRepo")) {
        if ($PSBoundParameters.ContainsKey($selection)) { $shellParameters[$selection] = $PSBoundParameters[$selection] }
    }
    if ($PSBoundParameters.ContainsKey("Port")) { $shellParameters.Port = $Port }
    & (Join-Path $projectRoot "Start-SORA.ps1") @shellParameters
    return
}
$testRoot = if ($StateRoot) { [IO.Path]::GetFullPath($StateRoot) } else { Join-Path $projectRoot ".local/manual-test" }
$tokenFile = Join-Path $testRoot "private/sora-api-token"
$settingsFile = if ($Settings) { [IO.Path]::GetFullPath($Settings) } else { Join-Path $testRoot "data/sora-settings.json" }
$resolvedWorkspace = if ($WorkspaceRoot) { [IO.Path]::GetFullPath($WorkspaceRoot) } else { Join-Path $testRoot "workspace" }
$resolvedWriteRepo = if ($WriteRepo) { [IO.Path]::GetFullPath($WriteRepo) } else { $resolvedWorkspace }
$openScript = Join-Path $projectRoot "scripts/open-manual-test.ps1"

$helpers = [ordered]@{
    Capture = @{
        Project = Join-Path $projectRoot "clients/windows_capture/windows_capture.csproj"
        Exe     = Join-Path $projectRoot "clients/windows_capture/bin/Debug/net10.0-windows/windows_capture.exe"
    }
    Bridge = @{
        Project = Join-Path $projectRoot "clients/windows_bridge/windows_bridge.csproj"
        Exe     = Join-Path $projectRoot "clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe"
    }
    Action = @{
        Project = Join-Path $projectRoot "clients/windows_action/windows_action.csproj"
        Exe     = Join-Path $projectRoot "clients/windows_action/bin/Debug/net10.0-windows/windows_action.exe"
    }
    Type = @{
        Project = Join-Path $projectRoot "clients/windows_type/windows_type.csproj"
        Exe     = Join-Path $projectRoot "clients/windows_type/bin/Debug/net10.0-windows/windows_type.exe"
    }
}
$player = Join-Path $projectRoot "clients/unity/Builds/Windows/SORA.exe"

if (-not $NoAvatar -and -not (Test-Path -LiteralPath $player -PathType Leaf)) {
    throw "Build the 3D companion with scripts/build-embodiment.ps1 first, or use -NoAvatar."
}
if ($AvatarPath -and -not (Test-Path -LiteralPath $AvatarPath -PathType Leaf)) {
    throw "Avatar file was not found: $AvatarPath"
}
foreach ($command in @("uv", "dotnet")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "$command is required. Follow scripts/bootstrap.ps1, then retry."
    }
}

$coreUrl = "http://127.0.0.1:$Port"
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    if ($PSBoundParameters.ContainsKey("Port")) {
        throw "Something is already listening at $coreUrl. Stop it or choose another -Port."
    }
    $listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $Port = $listener.LocalEndpoint.Port
    $listener.Stop()
    $coreUrl = "http://127.0.0.1:$Port"
    Write-Host "Default port is occupied; using $coreUrl."
}

Push-Location $projectRoot
try {
    if ($SetupVoice) { & (Join-Path $projectRoot "scripts/setup-local-voice.ps1") }
    Write-Host "Building Windows helpers (capture, bridge, action, type)..."
    foreach ($helper in $helpers.Values) {
        & dotnet build $helper.Project --verbosity quiet | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Build failed: $($helper.Project)" }
        if (-not (Test-Path -LiteralPath $helper.Exe -PathType Leaf)) {
            throw "Helper was not built: $($helper.Exe)"
        }
    }
    if (-not $NoClient) {
        $clientProject = switch ($Client) {
            "Desktop" { "clients/desktop_app/desktop_app.csproj" }
            "Widget" { "clients/desktop_widget/desktop_widget.csproj" }
            default { $null }
        }
        if ($clientProject) {
            & dotnet build (Join-Path $projectRoot $clientProject) --verbosity quiet | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "Build failed: $clientProject" }
        }
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $tokenFile) -Force | Out-Null
    New-Item -ItemType Directory -Path $resolvedWorkspace -Force | Out-Null
    if (-not (Test-Path -LiteralPath (Join-Path $resolvedWriteRepo ".git") -PathType Container)) {
        if ($WriteRepo) {
            throw "Write repository is not a Git repository: $resolvedWriteRepo. Managed coding writes need a Git base."
        }
        & git -C $resolvedWriteRepo init --quiet
        if ($LASTEXITCODE -ne 0) { throw "Could not initialise the delegation workspace as a Git repository." }
        & git -C $resolvedWriteRepo commit --allow-empty --quiet -m "SORA delegation workspace"
        if ($LASTEXITCODE -ne 0) { throw "Could not create the delegation workspace base commit." }
        Write-Host "Delegation workspace initialised as a Git repository so coding writes have an owned base."
    }

    Write-Host ""
    Write-Host "Full SORA test state : $testRoot"
    Write-Host "API                  : $coreUrl (token: $tokenFile)"
    Write-Host "Windows helpers      : capture, observation bridge, action (press), type"
    Write-Host "Desktop awareness    : observation/capture/targets/press/type/attention all wired"
    Write-Host "Chat actions         : pose keywords, walk-to-pointer, look-at-screen (needs a vision dialogue model)"
    Write-Host "Delegated agents     : auto-routed (Hermes, Codex, Antigravity); workspace $resolvedWorkspace"
    Write-Host "Codex model          : $CodexModel"
    Write-Host "Antigravity model    : $AntigravityModel (effort: $AntigravityEffort)"
    if (-not $NoAvatar) { Write-Host "3D companion         : $player" }
    if (Test-Path -LiteralPath $settingsFile -PathType Leaf) {
        Write-Host "Dialogue             : selected by the unified Settings page ($settingsFile)"
    } else {
        Write-Host "Dialogue             : no settings file at $settingsFile yet; Settings page creates it"
    }
    Write-Host ""

    function ConvertTo-PowerShellLiteral([string]$Value) {
        return "'" + $Value.Replace("'", "''") + "'"
    }

    $command = "Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue; "
    $command += "& uv run --locked sora"
    $command += " --root $(ConvertTo-PowerShellLiteral $testRoot)"
    $command += " --identity-root $(ConvertTo-PowerShellLiteral (Join-Path $projectRoot 'identity'))"
    $command += " --provider $(ConvertTo-PowerShellLiteral $Provider)"
    $command += " --workspace-root $(ConvertTo-PowerShellLiteral $resolvedWorkspace)"
    $command += " --task-timeout $TaskTimeout"
    $command += " --codex-cwd $(ConvertTo-PowerShellLiteral $resolvedWriteRepo)"
    $command += " --codex-write-base HEAD"
    $command += " --codex-workspace-root $(ConvertTo-PowerShellLiteral (Join-Path $testRoot 'coding-workspaces'))"
    $command += " --codex-model $(ConvertTo-PowerShellLiteral $CodexModel)"
    $command += " --windows-capture $(ConvertTo-PowerShellLiteral $helpers.Capture.Exe)"
    $command += " --windows-bridge $(ConvertTo-PowerShellLiteral $helpers.Bridge.Exe)"
    $command += " --windows-action $(ConvertTo-PowerShellLiteral $helpers.Action.Exe)"
    $command += " --windows-type $(ConvertTo-PowerShellLiteral $helpers.Type.Exe)"
    $command += " --settings $(ConvertTo-PowerShellLiteral $settingsFile)"
    $command += " --antigravity-model $(ConvertTo-PowerShellLiteral $AntigravityModel)"
    $command += " --antigravity-effort $(ConvertTo-PowerShellLiteral $AntigravityEffort)"
    if (-not $NoAntigravitySkipPermissions) {
        $command += " --antigravity-arg=--dangerously-skip-permissions"
    } else {
        # Core now skips Antigravity's permission prompts by default; this keeps the opt-out.
        $command += " --antigravity-ask-permissions"
    }
    if (-not $NoAvatar) {
        $command += " --embodiment-player $(ConvertTo-PowerShellLiteral $player)"
        if ($AvatarPath) { $command += " --avatar-path $(ConvertTo-PowerShellLiteral ([IO.Path]::GetFullPath($AvatarPath)))" }
    }
    $command += " --serve --api-host 127.0.0.1 --api-port $Port"
    $command += " --api-token-file $(ConvertTo-PowerShellLiteral $tokenFile)"

    $encodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    $powerShellExe = (Get-Process -Id $PID).Path
    $startedAt = [DateTime]::UtcNow

    Write-Host "Starting SORA Core in a separate PowerShell window with every helper wired."
    $coreProcess = Start-Process -FilePath $powerShellExe -ArgumentList @(
        "-NoProfile", "-EncodedCommand", $encodedCommand
    ) -WorkingDirectory $projectRoot -WindowStyle Normal -PassThru

    $deadline = $startedAt.AddSeconds(660)
    $ready = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        $coreProcess.Refresh()
        if ($coreProcess.HasExited) {
            throw "SORA Core exited during startup. Check the Core window for its startup/model error."
        }
        if ((Test-Path -LiteralPath $tokenFile -PathType Leaf) -and
            (Get-Item -LiteralPath $tokenFile).LastWriteTimeUtc -ge $startedAt.AddSeconds(-1)) {
            $token = (Get-Content -Raw -LiteralPath $tokenFile).Trim()
            try {
                $null = Invoke-RestMethod -Uri "$coreUrl/api/v1/status" -Headers @{
                    Authorization = "Bearer $token"
                } -TimeoutSec 2
                $ready = $true
                break
            }
            catch {
                # Core may have written its token before the API starts listening.
            }
        }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) {
        throw "SORA Core did not become ready within eleven minutes. Check the Core window for its startup/model error."
    }

    if ($NoClient) {
        Write-Host "Open a client later with: .\scripts\open-manual-test.ps1 -Client $Client -Port $Port"
    } else {
        & $openScript -Client $Client -Port $Port -StateRoot $testRoot
    }
    Write-Host "SORA is ready at $coreUrl. Press Ctrl+C in the Core window to stop it."
}
finally {
    Pop-Location
}
