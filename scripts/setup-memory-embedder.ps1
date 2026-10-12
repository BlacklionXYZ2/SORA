[CmdletBinding()]
param(
    # Also fetch the image/audio projector (about 530 MB). Text memories don't need it.
    [switch]$WithMedia
)

# Installs the memory manager's embedder once. See docs/plans/MEMORY_MANAGER_2026-10-08.md.
#
# - EmbeddingGemma 2 (Google, Gemma terms), Unsloth's UD-Q4_K_XL GGUF (about 170 MB) from
#   unsloth/embeddinggemma-2-GGUF, plus optionally its mmproj for image and audio parts.
# - llama.cpp b11516, Windows Vulkan x64: EmbeddingGemma 2 needs b11516 or newer, which is newer
#   than the brain's runtime, so the embedder runs as its own small server. The brain's llama.cpp
#   is not changed.
#
# Files go to .local/, are checked against the SHA-256 hashes verified on 2026-10-09, and are
# never replaced once present. Windows PowerShell 5.1 compatible.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$projectRoot = Split-Path -Parent $PSScriptRoot
$local = Join-Path $projectRoot ".local"
$models = Join-Path $local "models/embeddinggemma-2"
New-Item -ItemType Directory -Force $models | Out-Null

function Get-Checked([string]$Url, [string]$Target, [string]$Sha256) {
    if (Test-Path -LiteralPath $Target) { Write-Host "Already present: $Target"; return }
    $partial = "$Target.partial"
    Invoke-WebRequest -Uri $Url -OutFile $partial -UseBasicParsing
    $hash = (Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne $Sha256) {
        Move-Item -LiteralPath $partial -Destination "$Target.rejected-$hash" -Force
        throw "$Url did not match its expected checksum; kept as $Target.rejected-$hash."
    }
    Move-Item -LiteralPath $partial -Destination $Target
}

$build = "b11516"
$zip = Join-Path $local "llama.cpp-$build.zip"
$runtime = Join-Path $local "llama.cpp-$build"
Write-Host "llama.cpp $build (Vulkan, about 60 MB)..."
Get-Checked "https://github.com/ggml-org/llama.cpp/releases/download/$build/llama-$build-bin-win-vulkan-x64.zip" `
    $zip "01dff69c02650624d401be0b170348ea38f4bcdca24cb97a7415cddb7315414b"
if (-not (Test-Path -LiteralPath (Join-Path $runtime "llama-server.exe"))) {
    Expand-Archive -LiteralPath $zip -DestinationPath $runtime
}

$hf = "https://huggingface.co/unsloth/embeddinggemma-2-GGUF/resolve/main"
Write-Host "EmbeddingGemma 2 UD-Q4_K_XL (about 170 MB)..."
Get-Checked "$hf/embeddinggemma-2-UD-Q4_K_XL.gguf" (Join-Path $models "embeddinggemma-2-UD-Q4_K_XL.gguf") `
    "ea905fd08e8061db77a0031cbb5096d459d7cfd2bdd0ad2ba66e483f16719493"
if ($WithMedia) {
    Write-Host "Image and audio projector (about 530 MB)..."
    Get-Checked "$hf/mmproj-Q8_0.gguf" (Join-Path $models "mmproj-Q8_0.gguf") `
        "90e7b0238009e2954f856f2081dcf7f35af026b64c765e98f4777053e1754460"
}
Write-Host "Memory embedder ready. SORA starts it with Core (Settings -> Memory -> Memory manager)."
