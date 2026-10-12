[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765,
    [ValidateSet("Desktop", "Widget", "Browser", "Shell")]
    [string]$Client = "Shell",
    [string]$DialogueModel,
    [string]$DialogueBaseUrl = "http://127.0.0.1:1234/v1",
    [string]$LlamaConfig,
    [string]$Settings,
    [string]$StateRoot,
    [string]$AvatarPath,
    [string]$WorkspaceRoot,
    [string]$WriteRepo,
    [ValidateRange(30, 3600)]
    [int]$TaskTimeout = 300,
    [switch]$NoAvatar,
    [switch]$SetupVoice,
    [switch]$NoClient,
    [ValidateSet("none", "chat", "voice", "memory", "activity", "agents", "paths", "board", "content", "integrations", "settings", "appearance", "menu", "quit")]
    [string]$ShellPanel = "none",
    [ValidateSet("auto", "deterministic")]
    [string]$Provider = "auto",
    [string]$CodexModel,
    [string]$AntigravityModel,
    [ValidateSet("low", "medium", "high")]
    [string]$AntigravityEffort,
    [switch]$AntigravitySkipPermissions,
    [switch]$UnifiedSettingsOnly,
    # Useful for supervised/automated launches; the normal interactive console stays available.
    [switch]$HiddenCore,
    # The new glass Chat and Settings windows are the default (WebView2). -ClassicPanels opens the
    # previous WinForms windows instead. -WebPanels is still accepted and changes nothing.
    [switch]$ClassicPanels,
    [switch]$WebPanels,
    # Translucency route for web panels: System (Windows 11 acrylic), Accent (older blur) or None.
    [ValidateSet("System", "Accent", "None")]
    [string]$PanelBackdrop = "System"
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$coreScript = Join-Path $projectRoot "scripts/start-manual-test.ps1"
$openScript = Join-Path $projectRoot "scripts/open-manual-test.ps1"
if (-not $StateRoot) { $StateRoot = Join-Path $projectRoot ".local/manual-test" }
$StateRoot = [IO.Path]::GetFullPath($StateRoot)
$tokenFile = Join-Path $StateRoot "private/sora-api-token"
$coreUrl = "http://127.0.0.1:$Port"

if (-not (Test-Path -LiteralPath $coreScript -PathType Leaf) -or
    -not (Test-Path -LiteralPath $openScript -PathType Leaf)) {
    throw "SORA's startup scripts are missing from $projectRoot."
}
function ConvertTo-NativeArgument([string]$Value) {
    # Windows command-line quoting (CommandLineToArgvW rules). ProcessStartInfo.ArgumentList
    # does not exist in Windows PowerShell 5.1, so the native app's arguments are joined here.
    if ($Value -eq "") { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    $escaped = [regex]::Replace($Value, '(\\*)"', { param($m) ($m.Groups[1].Value * 2) + '\"' })
    $escaped = [regex]::Replace($escaped, '(\\+)$', { param($m) $m.Groups[1].Value * 2 })
    return '"' + $escaped + '"'
}

# The native app is the ordinary client (V1). It owns SORA's lifetime, so a headless
# -NoClient start without an explicit client keeps the plain Core path.
if ($NoClient -and -not $PSBoundParameters.ContainsKey('Client')) { $Client = "Desktop" }

# Choose SORA's port before the native app starts. Another program may own the default port (on
# the owner's machine, Antigravity serves 8765); the native app would then refuse to attach to it
# and, correctly, would not start a second Core there, leaving no Core at all.
if ($Client -eq "Shell" -and -not $PSBoundParameters.ContainsKey("Port")) {
    $savedPort = $null
    $descriptor = Join-Path $StateRoot "desktop-shell/runtime.json"
    if (Test-Path -LiteralPath $descriptor -PathType Leaf) {
        try { $savedPort = ([Uri](Get-Content -Raw -LiteralPath $descriptor | ConvertFrom-Json).core_url).Port }
        catch { $savedPort = $null }
    }
    if ($savedPort) {
        $Port = $savedPort  # Reuse this profile's Core address so a running Core is found again.
    }
    else {
        $candidates = @($Port) + (8766..8775)
        $free = $candidates | Where-Object {
            -not (Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue)
        } | Select-Object -First 1
        if (-not $free) { throw "Ports 8765-8775 are all in use. Choose a free one with -Port." }
        if ($free -ne $Port) { Write-Host "Port $Port is used by another program; SORA will use $free." }
        $Port = $free
    }
    $coreUrl = "http://127.0.0.1:$Port"
}
if ($Client -eq "Shell") {
    if ($NoClient) { throw "-Client Shell owns presence and service lifetime; do not combine it with -NoClient." }
    $shellProject = Join-Path $projectRoot "clients/desktop_shell/desktop_shell.csproj"
    & dotnet build $shellProject --verbosity quiet
    if ($LASTEXITCODE -ne 0) { throw "Desktop shell build failed." }
    $shellExecutable = Join-Path $projectRoot "clients/desktop_shell/bin/Debug/net10.0-windows/SoraShell.exe"
    $hostStart = [Diagnostics.ProcessStartInfo]::new($shellExecutable)
    $hostStart.UseShellExecute = $false
    $hostStart.CreateNoWindow = $true
    $hostStart.WorkingDirectory = $projectRoot
    $shellArgs = [Collections.Generic.List[string]]::new()
    foreach ($argument in @("--core-url", $coreUrl, "--token-file", $tokenFile,
        "--state-root", $StateRoot, "--show", $ShellPanel,
        "--managed-project-root", $projectRoot,
        "--managed-powershell", (Get-Process -Id $PID).Path,
        "--managed-timeout", "$TaskTimeout", "--managed-provider", $Provider,
        "--managed-no-avatar", "$($NoAvatar.IsPresent)".ToLowerInvariant(),
        "--managed-setup-voice", "$($SetupVoice.IsPresent)".ToLowerInvariant(),
        "--managed-antigravity-skip-permissions", "$($AntigravitySkipPermissions.IsPresent)".ToLowerInvariant(),
        "--managed-unified-settings-only", "$($UnifiedSettingsOnly.IsPresent)".ToLowerInvariant(),
        "--managed-discovery", $(if ($PSBoundParameters.ContainsKey("Port")) { "explicit" } else { "default" }))) {
        $shellArgs.Add($argument)
    }
    foreach ($selection in @(
        @("--managed-settings", $Settings), @("--managed-llama-config", $LlamaConfig),
        @("--managed-avatar", $AvatarPath), @("--managed-workspace", $WorkspaceRoot),
        @("--managed-write-repo", $WriteRepo)
    )) {
        if ($selection[1]) {
            $shellArgs.Add($selection[0])
            $shellArgs.Add([IO.Path]::GetFullPath($selection[1]))
        }
    }
    if ($DialogueModel) {
        $shellArgs.Add("--managed-model"); $shellArgs.Add($DialogueModel)
        $shellArgs.Add("--managed-model-url"); $shellArgs.Add($DialogueBaseUrl)
    }
    foreach ($selection in @(@("--managed-codex-model", $CodexModel),
        @("--managed-antigravity-model", $AntigravityModel), @("--managed-antigravity-effort", $AntigravityEffort))) {
        if ($selection[1]) { $shellArgs.Add($selection[0]); $shellArgs.Add($selection[1]) }
    }
    $hostStart.Arguments = ($shellArgs | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
    $hostStart.EnvironmentVariables["SORA_PANELS"] = $(if ($ClassicPanels) { "classic" } else { "web" })
    $hostStart.EnvironmentVariables["SORA_PANEL_BACKDROP"] = $PanelBackdrop.ToLowerInvariant()
    $hostProcess = [Diagnostics.Process]::Start($hostStart)
    Write-Host "SORA desktop host requested for $StateRoot (host/forwarder PID $($hostProcess.Id))."
    Write-Host "The host verifies profile ownership before startup. Use tray/menu for recovery and owned Quit."
    return
}
if ($SetupVoice) { & (Join-Path $projectRoot "scripts/setup-local-voice.ps1") }

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

function ConvertTo-PowerShellLiteral([string]$Value) {
    return "'" + $Value.Replace("'", "''") + "'"
}

$command = "& $(ConvertTo-PowerShellLiteral $coreScript) -Port $Port"
$command += " -StateRoot $(ConvertTo-PowerShellLiteral $StateRoot)"
if ($Settings) { $command += " -Settings $(ConvertTo-PowerShellLiteral ([IO.Path]::GetFullPath($Settings)))" }
if ($LlamaConfig) { $command += " -LlamaConfig $(ConvertTo-PowerShellLiteral ([IO.Path]::GetFullPath($LlamaConfig)))" }
if ($AvatarPath) { $command += " -AvatarPath $(ConvertTo-PowerShellLiteral $AvatarPath)" }
if ($NoAvatar) { $command += " -NoAvatar" }
if ($WorkspaceRoot) { $command += " -WorkspaceRoot $(ConvertTo-PowerShellLiteral $WorkspaceRoot)" }
if ($WriteRepo) { $command += " -WriteRepo $(ConvertTo-PowerShellLiteral $WriteRepo)" }
$command += " -TaskTimeout $TaskTimeout"
if ($Provider -ne "auto") { $command += " -Provider $Provider" }
if ($CodexModel) { $command += " -CodexModel $(ConvertTo-PowerShellLiteral $CodexModel)" }
if ($AntigravityModel) { $command += " -AntigravityModel $(ConvertTo-PowerShellLiteral $AntigravityModel)" }
if ($AntigravityEffort) { $command += " -AntigravityEffort $(ConvertTo-PowerShellLiteral $AntigravityEffort)" }
if ($AntigravitySkipPermissions) { $command += " -AntigravitySkipPermissions" }
if ($UnifiedSettingsOnly) { $command += " -UnifiedSettingsOnly" }
if ($DialogueModel) {
    $command += " -DialogueModel $(ConvertTo-PowerShellLiteral $DialogueModel)"
    $command += " -DialogueBaseUrl $(ConvertTo-PowerShellLiteral $DialogueBaseUrl)"
}
$encodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
$powerShellExe = (Get-Process -Id $PID).Path
$startedAt = [DateTime]::UtcNow

Write-Host "Starting SORA Core in a separate PowerShell window. The first run may take a minute to build."
$coreWindowStyle = if ($HiddenCore) { "Hidden" } else { "Normal" }
$coreProcess = Start-Process -FilePath $powerShellExe -ArgumentList @(
    "-NoProfile", "-EncodedCommand", $encodedCommand
) -WorkingDirectory $projectRoot -WindowStyle $coreWindowStyle -PassThru

$deadline = $startedAt.AddSeconds(660)
$ready = $false
while ([DateTime]::UtcNow -lt $deadline) {
    $coreProcess.Refresh()
    if ($coreProcess.HasExited) {
        throw "SORA Core exited during startup. Run .\scripts\start-manual-test.ps1 directly to see the error."
    }
    if (Test-Path -LiteralPath $tokenFile -PathType Leaf) {
        $tokenInfo = Get-Item -LiteralPath $tokenFile
        if ($tokenInfo.LastWriteTimeUtc -ge $startedAt.AddSeconds(-1)) {
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
    }
    Start-Sleep -Milliseconds 500
}
if (-not $ready) {
    throw "SORA Core did not become ready within eleven minutes. Check the Core window for its startup/model error."
}

if (-not $NoClient) { & $openScript -Client $Client -Port $Port -StateRoot $StateRoot }
Write-Host "SORA is ready at $coreUrl. Core launcher process: $($coreProcess.Id)."
if ($HiddenCore) {
    Write-Host "Core console is hidden. This supervised launch must be stopped by its owner."
} else {
    Write-Host "Press Ctrl+C in the Core window to stop it."
}
