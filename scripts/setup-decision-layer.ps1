[CmdletBinding()]
param(
    # GPU build of the laya runner. vulkan works on AMD, Intel and NVIDIA; cuda-sm86 / cuda-sm89
    # suit NVIDIA RTX 30 / 40 cards.
    [ValidateSet("vulkan", "cuda-sm86", "cuda-sm89")]
    [string]$Build = "vulkan"
)

# Installs SORA's decision layer (System-1) once. See docs/plans/DECISION_LAYER_2026-10-08.md.
#
# - Laya (Convai Innovations, Apache 2.0): a 421M-parameter ModernBERT-large decision model,
#   compiled to GGUF with ggmlc and quantized to Q8_0 (mys/laya-GGUF, about 430 MB).
# - The `laya` runner from ggmlc (MIT), which runs that GGUF on the GPU. These files are not
#   llama.cpp GGUFs, so SORA's llama-server cannot load them.
#
# Both go to .local/decision/, are checked against published SHA-256 hashes, and are never
# replaced once present. Windows PowerShell 5.1 compatible.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$projectRoot = Split-Path -Parent $PSScriptRoot
$folder = Join-Path $projectRoot ".local/decision"
$release = "v0.9.7"
$runners = @{
    "vulkan"    = "e879d1e9a37eb9898f66cff7ad9fe4955c6670d28d974bcba74eaa8c54660ae6"
}
$modelUrl = "https://huggingface.co/mys/laya-GGUF/resolve/main/laya_english_q8_0.gguf"
$modelSha256 = "6243305fb16cf22e53b932c220bd029be2adbfbec6ce120356517b8ae2f38382"
New-Item -ItemType Directory -Force $folder | Out-Null

function Get-Checked([string]$Url, [string]$Target, [string]$Sha256) {
    if (Test-Path -LiteralPath $Target) { Write-Host "Already present: $Target"; return }
    $partial = "$Target.partial"
    Invoke-WebRequest -Uri $Url -OutFile $partial -UseBasicParsing
    $hash = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Sha256 -and $hash -ne $Sha256) {
        Move-Item -LiteralPath $partial -Destination "$Target.rejected-$hash" -Force
        throw "$Url did not match its expected checksum; kept as $Target.rejected-$hash."
    }
    Move-Item -LiteralPath $partial -Destination $Target
}

$zipName = "laya-windows-x86_64-$Build.zip"
$zip = Join-Path $folder ($zipName -replace "\.zip$", "-$release.zip")
if ($Build -eq "vulkan") { $runnerFolder = Join-Path $folder "laya-$release" } else { $runnerFolder = Join-Path $folder "laya-$release-$Build" }
Write-Host "Downloading the laya runner ($Build, about 18-70 MB)..."
Get-Checked "https://github.com/monatis/ggmlc/releases/download/$release/$zipName" $zip $runners[$Build]
if (-not (Test-Path -LiteralPath (Join-Path $runnerFolder "laya.exe"))) {
    Expand-Archive -LiteralPath $zip -DestinationPath $runnerFolder
}
Write-Host "Downloading Laya Q8_0 (about 430 MB, once)..."
Get-Checked $modelUrl (Join-Path $folder "laya_english_q8_0.gguf") $modelSha256
& (Join-Path $runnerFolder "laya.exe") info (Join-Path $folder "laya_english_q8_0.gguf") | Select-String "device:|checkpoint:"
Write-Host "Decision layer ready. SORA starts it with Core (Settings -> Models -> Decision layer)."
