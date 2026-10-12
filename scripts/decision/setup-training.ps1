[CmdletBinding()]
param(
    # Python whose site-packages already hold a GPU torch (the owner's ROCm build). The training
    # environment inherits it instead of downloading another torch.
    [string]$BasePython = "python"
)

# One-time setup for training the decision layer. See docs/runbooks/TRAINING_LAYA.md.
#   .local/decision/train-env/     venv over $BasePython's packages + laya and ggmlc (no deps)
#   .local/models/laya/            the full-precision Laya checkpoint to fine-tune from
#   .local/decision/ggmlc-v0.9.7/  ggmlc's Laya compile scripts (compile_laya.py, laya_trunk.py)
# Windows PowerShell 5.1 compatible. Nothing is replaced once present.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$env_ = Join-Path $projectRoot ".local/decision/train-env"
$python = Join-Path $env_ "Scripts/python.exe"
$ggmlcRelease = "v0.9.7"
$wheelUrl = "https://github.com/monatis/ggmlc/releases/download/$ggmlcRelease/ggmlc-0.9.7-cp312-cp312-win_amd64.whl"

& $BasePython -c "import torch, sys; ok = torch.cuda.is_available(); print('base torch', torch.__version__, 'GPU' if ok else 'CPU only', torch.cuda.get_device_name(0) if ok else ''); sys.exit(0 if ok else 3)"
if ($LASTEXITCODE -eq 3) { Write-Warning "That torch has no GPU; training will be very slow." }
elseif ($LASTEXITCODE -ne 0) { throw "$BasePython has no torch. Install a GPU torch (ROCm or CUDA) there first, or pass -BasePython." }

if (-not (Test-Path -LiteralPath $python)) {
    & $BasePython -m venv --system-site-packages $env_
    if ($LASTEXITCODE -ne 0) { throw "Could not create $env_" }
}
& $python -m pip install --quiet --no-deps "laya==0.4.1" $wheelUrl
if ($LASTEXITCODE -ne 0) { throw "Could not install laya and ggmlc into $env_" }

$scripts = Join-Path $projectRoot ".local/decision/ggmlc-$ggmlcRelease"
New-Item -ItemType Directory -Force $scripts | Out-Null
foreach ($name in @("compile_laya.py", "laya_trunk.py")) {
    $target = Join-Path $scripts $name
    if (-not (Test-Path -LiteralPath $target)) {
        Invoke-WebRequest "https://raw.githubusercontent.com/monatis/ggmlc/$ggmlcRelease/examples/laya/$name" -OutFile $target -UseBasicParsing
    }
}

$checkpoint = Join-Path $projectRoot ".local/models/laya"
if (-not (Test-Path -LiteralPath (Join-Path $checkpoint "config.json"))) {
    Write-Host "Downloading the Laya checkpoint to fine-tune from (about 800 MB)..."
    & $python -c "import sys; from huggingface_hub import snapshot_download; snapshot_download(repo_id='convaiinnovations/laya', local_dir=sys.argv[1], allow_patterns=['*.json', '*.safetensors', 'encoder/*', 'tokenizer/*', '*.py'], ignore_patterns=['multilingual/*', 'typed-decisions/*'])" $checkpoint
    if ($LASTEXITCODE -ne 0) { throw "Could not download the Laya checkpoint." }
}
& $python -c "import torch, laya, ggmlc; print('training environment ready: torch', torch.__version__, '| laya', laya.__version__, '| ggmlc', ggmlc.__version__)"
