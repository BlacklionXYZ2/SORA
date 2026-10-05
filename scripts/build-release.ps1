[CmdletBinding()]
param(
    [string]$ReleaseId,
    [string]$OutputDirectory,
    [string]$UnityEditor = $env:SORA_UNITY_EDITOR,
    [switch]$ReuseVerifiedUnityBuild,
    [switch]$SkipUnityBuild
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ReleaseId) {
    $ReleaseId = "sora-" + (Get-Date -Format "yyyyMMdd-HHmmss")
}
if ($ReuseVerifiedUnityBuild -and $SkipUnityBuild) {
    throw "ReuseVerifiedUnityBuild and SkipUnityBuild are mutually exclusive."
}
if ($ReleaseId -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$') {
    throw "ReleaseId must contain 1-80 safe filename characters."
}
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $projectRoot ".local/releases"
}
$outputRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
$bundleRoot = Join-Path $outputRoot $ReleaseId
$archive = Join-Path $outputRoot ($ReleaseId + ".zip")
if ((Test-Path -LiteralPath $bundleRoot) -or (Test-Path -LiteralPath $archive)) {
    throw "Release output already exists for $ReleaseId; choose a new ReleaseId."
}

foreach ($command in @("uv", "dotnet")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "$command is required to build the SORA release."
    }
}
if (-not $UnityEditor) {
    $UnityEditor = Join-Path $env:ProgramFiles "Unity/Hub/Editor/6000.6.0f1/Editor/Unity.exe"
}
if (-not $SkipUnityBuild -and -not (Test-Path -LiteralPath $UnityEditor -PathType Leaf)) {
    throw "Unity 6000.6.0f1 is required. Pass -UnityEditor or use -SkipUnityBuild for a non-acceptance engineering bundle."
}

$payload = Join-Path $bundleRoot "payload"
$portablePythonRoot = Join-Path $payload "core/python"
$wheelRoot = Join-Path $bundleRoot ".build/wheels"
$downloadedPythonRoot = Join-Path $bundleRoot ".build/python"
$requirements = Join-Path $bundleRoot ".build/runtime-requirements.txt"
New-Item -ItemType Directory -Force $wheelRoot | Out-Null

Push-Location $projectRoot
try {
    & uv build --wheel --out-dir $wheelRoot
    if ($LASTEXITCODE -ne 0) { throw "SORA wheel build failed." }
    & uv python install 3.12.10 --install-dir $downloadedPythonRoot --no-bin --no-registry --compile-bytecode
    if ($LASTEXITCODE -ne 0) { throw "Portable CPython acquisition failed." }
    $downloadedPython = Get-ChildItem -LiteralPath $downloadedPythonRoot -Recurse -Filter python.exe |
        Where-Object FullName -NotMatch '\\Lib\\venv\\' | Select-Object -First 1
    if (-not $downloadedPython) { throw "Portable CPython executable was not produced." }
    Copy-Item -LiteralPath $downloadedPython.Directory.FullName -Destination $portablePythonRoot -Recurse

    & uv export --locked --no-dev --no-emit-project --format requirements.txt --output-file $requirements
    if ($LASTEXITCODE -ne 0) { throw "Locked runtime dependency export failed." }
    $portablePython = Join-Path $portablePythonRoot "python.exe"
    $sitePackages = Join-Path $portablePythonRoot "Lib/site-packages"
    & uv pip install --python $portablePython --target $sitePackages --compile-bytecode --requirement $requirements
    if ($LASTEXITCODE -ne 0) { throw "Locked runtime dependency installation failed." }
    $wheel = Get-ChildItem -LiteralPath $wheelRoot -Filter *.whl | Select-Object -First 1
    & uv pip install --python $portablePython --target $sitePackages --compile-bytecode --no-deps $wheel.FullName
    if ($LASTEXITCODE -ne 0) { throw "SORA wheel installation into portable runtime failed." }

    $identityDestination = Join-Path $payload "resources/identity"
    New-Item -ItemType Directory -Force (Join-Path $payload "resources") | Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot "identity") -Destination $identityDestination -Recurse
    Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination (Join-Path $payload "resources/README.md")
    Copy-Item -LiteralPath (Join-Path $projectRoot "docs/runbooks/SORA_BACKUP_AND_RESTORE.md") `
        -Destination (Join-Path $payload "resources/SORA_BACKUP_AND_RESTORE.md")

    $helperProjects = @("windows_bridge", "windows_action", "windows_type", "windows_capture")
    foreach ($helper in $helperProjects) {
        $project = Join-Path $projectRoot "clients/$helper/$helper.csproj"
        $destination = Join-Path $payload "helpers/$helper"
        & dotnet publish $project -c Release -r win-x64 --self-contained true `
            -p:PublishSingleFile=true -p:PublishTrimmed=false -p:DebugType=None -o $destination
        if ($LASTEXITCODE -ne 0) { throw "$helper self-contained publish failed." }
        if (-not (Test-Path -LiteralPath (Join-Path $destination "$helper.exe") -PathType Leaf)) {
            throw "$helper did not produce the expected executable."
        }
    }

    $widgetProject = Join-Path $projectRoot "clients/desktop_widget/desktop_widget.csproj"
    $widgetDestination = Join-Path $payload "clients/widget"
    & dotnet publish $widgetProject -c Release -r win-x64 --self-contained true `
        -p:PublishSingleFile=true -p:PublishTrimmed=false -p:DebugType=None -o $widgetDestination
    if ($LASTEXITCODE -ne 0 -or
        -not (Test-Path -LiteralPath (Join-Path $widgetDestination "SoraWidget.exe") -PathType Leaf)) {
        throw "SORA widget self-contained publish failed."
    }

    $desktopProject = Join-Path $projectRoot "clients/desktop_app/desktop_app.csproj"
    $desktopDestination = Join-Path $payload "clients/desktop"
    & dotnet publish $desktopProject -c Release -r win-x64 --self-contained true `
        -p:PublishSingleFile=true -p:PublishTrimmed=false -p:DebugType=None -o $desktopDestination
    if ($LASTEXITCODE -ne 0 -or
        -not (Test-Path -LiteralPath (Join-Path $desktopDestination "SoraDesktop.exe") -PathType Leaf)) {
        throw "SORA full desktop self-contained publish failed."
    }

    $unityStatus = "omitted_by_explicit_non_acceptance_switch"
    if ($ReuseVerifiedUnityBuild) {
        $unityBuild = Join-Path $projectRoot "clients/unity/Builds/Windows"
        $unityExecutable = Join-Path $unityBuild "SORA.exe"
        $unityResults = Join-Path $projectRoot ".local/p09-unity-evidence/playmode-results.xml"
        if (-not (Test-Path -LiteralPath $unityExecutable -PathType Leaf) -or
            -not (Test-Path -LiteralPath $unityResults -PathType Leaf)) {
            throw "No verified Unity build/results are available for reuse."
        }
        [xml]$unityReport = Get-Content -Raw -LiteralPath $unityResults
        if ($unityReport.'test-run'.result -ne 'Passed') {
            throw "The reusable Unity PlayMode report did not pass."
        }
        $unitySources = Get-ChildItem -LiteralPath (Join-Path $projectRoot "clients/unity/Assets") `
            -Recurse -File
        $latestUnitySource = $unitySources | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        $latestAuthoredUnitySource = $unitySources |
            Where-Object FullName -NotLike '*\Assets\Scenes\SoraOverlay.unity' |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        $latestUnityOutput = Get-ChildItem -LiteralPath $unityBuild -Recurse -File |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($latestUnityOutput.LastWriteTime -lt $latestUnitySource.LastWriteTime -or
            (Get-Item -LiteralPath $unityResults).LastWriteTime -lt $latestAuthoredUnitySource.LastWriteTime) {
            throw "The reusable Unity build or test report predates current Unity source."
        }
        Copy-Item -LiteralPath $unityBuild -Destination (Join-Path $payload "unity") -Recurse
        $unityStatus = "fresh_verified_unity_6000.6.0f1_windows_x64_build_reused"
    }
    elseif (-not $SkipUnityBuild) {
        & (Join-Path $projectRoot "scripts/build-embodiment.ps1") -UnityEditor $UnityEditor
        if ($LASTEXITCODE -ne 0) { throw "Unity verification/build failed." }
        $unityBuild = Join-Path $projectRoot "clients/unity/Builds/Windows"
        if (-not (Test-Path -LiteralPath (Join-Path $unityBuild "SORA.exe") -PathType Leaf)) {
            throw "Unity build did not produce SORA.exe."
        }
        Copy-Item -LiteralPath $unityBuild -Destination (Join-Path $payload "unity") -Recurse
        $unityStatus = "fresh_unity_6000.6.0f1_windows_x64_build"
    }

    foreach ($script in @("install.ps1", "update.ps1", "rollback.ps1", "uninstall.ps1")) {
        Copy-Item -LiteralPath (Join-Path $projectRoot "packaging/windows/$script") `
            -Destination (Join-Path $bundleRoot $script)
    }
    Copy-Item -LiteralPath $requirements -Destination (Join-Path $payload "resources/runtime-requirements.lock.txt")
    Copy-Item -LiteralPath (Join-Path $projectRoot "docs/runbooks/SORA_INSTALL_UPDATE_UNINSTALL.md") `
        -Destination (Join-Path $bundleRoot "OPERATIONS.md")

    $metadata = [ordered]@{
        python = "CPython 3.12.10 portable windows-x86_64"
        core = "locked wheel installed into portable runtime"
        helpers = "self-contained win-x64 single-file .NET 10"
        widget = "self-contained win-x64 SORA companion widget; owner loopback API only"
        desktop = "self-contained win-x64 SORA full application; owner loopback API only"
        unity = $unityStatus
        signed = $false
        startup = "disabled unless explicitly enabled per user"
        personal_data = "outside install root; retained on uninstall unless PurgeData is explicit"
        credentials = "outside release and backup; generated/configured after install"
        bundled_assets = @("SORA identity", "PWA", "Windows widget", "Windows full application", "Unity avatar and attribution when Unity is included")
        external_models = @(
            "Silero VAD, faster-whisper and Kokoro model files are not bundled; provision separately using recorded licences and digests"
        )
    }
    $metadataPath = Join-Path $bundleRoot "release-metadata.json"
    [System.IO.File]::WriteAllText(
        $metadataPath,
        (($metadata | ConvertTo-Json -Depth 6) + "`n"),
        [System.Text.UTF8Encoding]::new($false)
    )

    Remove-Item -LiteralPath (Join-Path $bundleRoot ".build") -Recurse -Force
    & $portablePython -B -m sora.operations.cli build-manifest `
        --bundle $bundleRoot --release-id $ReleaseId --metadata $metadataPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Release manifest generation failed." }
    & $portablePython -B -m sora.operations.cli verify-manifest --bundle $bundleRoot | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Release verification failed." }

    Compress-Archive -Path (Join-Path $bundleRoot "*") -DestinationPath $archive -CompressionLevel Optimal
    if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) { throw "Release archive was not produced." }
    $archiveHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "Bundle: $bundleRoot"
    Write-Host "Archive: $archive"
    Write-Host "SHA256: $archiveHash"
}
finally {
    Pop-Location
}
