[CmdletBinding()]
param(
    # Skip the one-time download of the faster full-precision Kokoro voice model (325 MB).
    [switch]$NoFastVoiceModel
)
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$voiceEnvironment = Join-Path $projectRoot ".local/voice-runtime"
$previousEnvironment = $env:UV_PROJECT_ENVIRONMENT
$fastModelUrl = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
$fastModelSha256 = "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5"
$ttsFolder = Join-Path $projectRoot ".local/p14-voice-benchmark/models/tts"
$fastModel = Join-Path $ttsFolder "kokoro-v1.0.onnx"
Push-Location $projectRoot
try {
    $env:UV_PROJECT_ENVIRONMENT = $voiceEnvironment
    & uv sync --locked --extra voice
    if ($LASTEXITCODE -ne 0) { throw "Local speech dependencies could not be installed." }
    if ($NoFastVoiceModel) {
        Write-Host "Skipped the fast voice model; SORA keeps using the existing int8 model."
    }
    elseif (Test-Path -LiteralPath $fastModel) {
        Write-Host "Fast voice model already present: $fastModel"
    }
    elseif (-not (Test-Path -LiteralPath $ttsFolder)) {
        Write-Host "No existing voice weights in $ttsFolder; the fast voice model was not fetched."
    }
    else {
        # About ten times faster than int8 on a desktop CPU, so she starts speaking sooner.
        $partial = "$fastModel.partial"
        Write-Host "Downloading the fast voice model (325 MB, once)..."
        $ProgressPreference = "SilentlyContinue"
        Invoke-WebRequest -Uri $fastModelUrl -OutFile $partial -UseBasicParsing
        $hash = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne $fastModelSha256) {
            Remove-Item -LiteralPath $partial
            throw "The fast voice model download did not match its expected checksum."
        }
        Move-Item -LiteralPath $partial -Destination $fastModel
        Write-Host "Fast voice model ready. SORA uses it the next time voice starts."
    }
    Write-Host "Local voice runtime ready."
}
finally {
    $env:UV_PROJECT_ENVIRONMENT = $previousEnvironment
    Pop-Location
}
