[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765,
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
    [ValidateSet("auto", "deterministic")]
    [string]$Provider = "auto",
    [string]$CodexModel,
    [string]$AntigravityModel,
    [ValidateSet("low", "medium", "high")]
    [string]$AntigravityEffort,
    [switch]$AntigravitySkipPermissions,
    # Full launcher uses canonical settings/defaults only, never a surprise
    # legacy llama import or external-server probe when its settings are absent.
    [switch]$UnifiedSettingsOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if ($SetupVoice) { & (Join-Path $projectRoot "scripts/setup-local-voice.ps1") }
$testRoot = if ($StateRoot) { [IO.Path]::GetFullPath($StateRoot) } else { Join-Path $projectRoot ".local/manual-test" }
$tokenFile = Join-Path $testRoot "private/sora-api-token"
$captureProject = Join-Path $projectRoot "clients/windows_capture/windows_capture.csproj"
$captureHelper = Join-Path $projectRoot "clients/windows_capture/bin/Debug/net10.0-windows/windows_capture.exe"
$observationProject = Join-Path $projectRoot "clients/windows_bridge/windows_bridge.csproj"
$observationHelper = Join-Path $projectRoot "clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe"
$actionProject = Join-Path $projectRoot "clients/windows_action/windows_action.csproj"
$actionHelper = Join-Path $projectRoot "clients/windows_action/bin/Debug/net10.0-windows/windows_action.exe"
$typeProject = Join-Path $projectRoot "clients/windows_type/windows_type.csproj"
$typeHelper = Join-Path $projectRoot "clients/windows_type/bin/Debug/net10.0-windows/windows_type.exe"
$player = Join-Path $projectRoot "clients/unity/Builds/Windows/SORA.exe"
$defaultDialogueModel = "gemma-4-e2b-uncensored-hauhaucs-aggressive-q4_k_p"
$resolvedWorkspace = if ($WorkspaceRoot) { [IO.Path]::GetFullPath($WorkspaceRoot) } else { Join-Path $testRoot "workspace" }
$resolvedWriteRepo = if ($WriteRepo) { [IO.Path]::GetFullPath($WriteRepo) } else { $resolvedWorkspace }
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

$dialogueArguments = @("--dialogue-backend", "deterministic")
$settingsFile = if ($Settings) { [IO.Path]::GetFullPath($Settings) } else {
    Join-Path $testRoot "data/sora-settings.json"
}
$useUnifiedSettings = Test-Path -LiteralPath $settingsFile -PathType Leaf
if (-not $UnifiedSettingsOnly -and -not $LlamaConfig -and -not $DialogueModel -and
    (Test-Path -LiteralPath (Join-Path $projectRoot ".local/llama-server.json"))) {
    $LlamaConfig = Join-Path $projectRoot ".local/llama-server.json"
}
if ($useUnifiedSettings -or $UnifiedSettingsOnly) {
    Write-Host "SORA settings: $settingsFile (canonical settings/defaults; legacy model arguments are ignored)."
}
elseif ($LlamaConfig) {
    $LlamaConfig = (Resolve-Path -LiteralPath $LlamaConfig).Path
    if ($DialogueModel) { throw "Choose either -LlamaConfig or an external -DialogueModel." }
    $dialogueArguments = @("--llama-config", $LlamaConfig, "--dialogue-timeout", "90")
    Write-Host "SORA will load the local GGUF and explicit projector from $LlamaConfig; LM Studio is not used."
}
else {
$requestedModel = if ($DialogueModel) { $DialogueModel } else { $defaultDialogueModel }
$endpoint = $null
$endpointValid = [Uri]::TryCreate($DialogueBaseUrl, [UriKind]::Absolute, [ref]$endpoint) -and
    $endpoint.Scheme -eq "http" -and
    $endpoint.Host -in @("127.0.0.1", "localhost", "::1") -and
    $endpoint.AbsolutePath.TrimEnd('/') -eq "/v1"
$dialogueServerReady = $false
if ($endpointValid) {
    try {
        $null = Invoke-RestMethod -Uri "$($DialogueBaseUrl.TrimEnd('/'))/models" -TimeoutSec 4
        $dialogueServerReady = $true
    }
    catch {
        $dialogueServerReady = $false
    }
}
if ($DialogueModel -and -not $dialogueServerReady) {
    throw "The local model server is unavailable at $DialogueBaseUrl. Start LM Studio's local server and load the model first."
}
if ($dialogueServerReady) {
    $dialogueArguments = @(
        "--dialogue-backend", "openai-compatible",
        "--dialogue-model", $requestedModel,
        "--dialogue-base-url", $DialogueBaseUrl,
        "--dialogue-timeout", "90"
    )
}
else {
    Write-Warning "LM Studio is not answering at $DialogueBaseUrl, so this start keeps the offline dialogue fixture. Start the local server and reload $requestedModel for real-time speech."
}
}

$dialogueArguments += @("--settings", $settingsFile)
Push-Location $projectRoot
try {
    # Core needs these helpers, so a failed build stops the start.
    foreach ($project in @($captureProject, $observationProject, $actionProject, $typeProject)) {
        & dotnet build $project --verbosity quiet
        if ($LASTEXITCODE -ne 0) { throw "Build failed: $project" }
    }
    # The frozen full app and widget are not needed to run Core. An open copy locks its .exe,
    # so a failed rebuild must not stop SORA from starting; warn and keep the previous build.
    foreach ($project in @(
        (Join-Path $projectRoot "clients/desktop_widget/desktop_widget.csproj"),
        (Join-Path $projectRoot "clients/desktop_app/desktop_app.csproj")
    )) {
        & dotnet build $project --verbosity quiet
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not rebuild $project (is it open?). Continuing with its previous build."
        }
    }
    if (-not (Test-Path -LiteralPath $captureHelper -PathType Leaf)) {
        throw "Windows capture helper was not built: $captureHelper"
    }
    if (-not (Test-Path -LiteralPath $observationHelper -PathType Leaf)) {
        throw "Windows observation helper was not built: $observationHelper"
    }
    foreach ($helper in @($actionHelper, $typeHelper)) {
        if (-not (Test-Path -LiteralPath $helper -PathType Leaf)) {
            throw "Windows interaction helper was not built: $helper"
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
    Write-Host "SORA test state: $testRoot"
    Write-Host "Windows helpers: capture, native observation, press and type (subject to saved Companion access)."
    if ($Provider -eq "deterministic") { Write-Host "Reasoning tasks: deterministic QA provider; no specialist invocation." }
    else { Write-Host "Reasoning tasks: auto-routed across installed specialists (Hermes, Codex, Antigravity); availability is checked at runtime." }
    Write-Host "Delegated agent workspace: $resolvedWorkspace"
    Write-Host "Managed coding writes: base HEAD of $resolvedWriteRepo (worktrees stay under $testRoot)"
    if ($useUnifiedSettings -or $UnifiedSettingsOnly) { Write-Host "Dialogue: selected by canonical Settings/defaults." }
    elseif ($LlamaConfig) { Write-Host "Dialogue: importing legacy llama.cpp configuration into GUI Settings." }
    else { Write-Host "Dialogue model: $requestedModel at $DialogueBaseUrl" }
    if (-not $UnifiedSettingsOnly -and -not $useUnifiedSettings -and -not $LlamaConfig -and -not $dialogueServerReady) {
        Write-Host "Dialogue is currently the offline fixture; saved Settings still take precedence on restart."
    }
    Write-Host "In a second PowerShell window run: .\scripts\open-manual-test.ps1 -Client Desktop -Port $Port"
    Write-Host "Press Ctrl+C here to stop Core. The isolated test state is retained under .local/manual-test."
    $soraArguments = @(
        "run", "--locked", "sora",
        "--root", $testRoot,
        "--identity-root", (Join-Path $projectRoot "identity"),
        "--provider", $Provider,
        "--workspace-root", $resolvedWorkspace,
        "--task-timeout", "$TaskTimeout",
        "--codex-cwd", $resolvedWriteRepo,
        "--codex-write-base", "HEAD",
        "--codex-workspace-root", (Join-Path $testRoot "coding-workspaces"),
        "--windows-capture", $captureHelper,
        "--windows-bridge", $observationHelper,
        "--windows-action", $actionHelper,
        "--windows-type", $typeHelper,
        "--serve", "--api-host", "127.0.0.1", "--api-port", "$Port",
        "--api-token-file", $tokenFile
    ) + $dialogueArguments
    if ($CodexModel) { $soraArguments += @("--codex-model", $CodexModel) }
    if ($AntigravityModel) { $soraArguments += @("--antigravity-model", $AntigravityModel) }
    if ($AntigravityEffort) { $soraArguments += @("--antigravity-effort", $AntigravityEffort) }
    if ($AntigravitySkipPermissions) { $soraArguments += "--antigravity-arg=--dangerously-skip-permissions" }
    if (-not $NoAvatar) {
        $soraArguments += @("--embodiment-player", $player)
        if ($AvatarPath) { $soraArguments += @("--avatar-path", [IO.Path]::GetFullPath($AvatarPath)) }
    }
    & uv @soraArguments
    if ($LASTEXITCODE -ne 0) { throw "SORA Core exited with code $LASTEXITCODE." }
}
finally {
    Pop-Location
}
