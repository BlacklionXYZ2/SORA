[CmdletBinding()]
param([string]$UnityPlayer)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $UnityPlayer) { $UnityPlayer = Join-Path $root 'clients/unity/Builds/Windows/SORA.exe' }
if (-not (Test-Path -LiteralPath $UnityPlayer)) { throw 'Build the Unity Windows player first.' }
$oldPlayer = $env:SORA_UNITY_PLAYER
Push-Location $root
try {
    dotnet build clients/input_fixture --verbosity quiet
    if ($LASTEXITCODE -ne 0) { throw 'Input fixture build failed' }
    $env:SORA_UNITY_PLAYER = (Resolve-Path -LiteralPath $UnityPlayer).Path
    uv run --locked pytest tests/embodiment/test_unity_player.py -q -s
    if ($LASTEXITCODE -ne 0) { throw 'Packaged acceptance failed; inspect .local/p09-unity-evidence/player' }
}
finally {
    $env:SORA_UNITY_PLAYER = $oldPlayer
    Pop-Location
}
