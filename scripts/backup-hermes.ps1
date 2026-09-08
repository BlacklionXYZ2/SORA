[CmdletBinding()]
param(
    [Parameter()]
    [string]$SourceRoot = "C:\Users\oscar\Desktop\agent-workspace\Hermes",

    [Parameter()]
    [string]$DestinationRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) ".local\backups")
)

$ErrorActionPreference = "Stop"
$sourcePath = (Resolve-Path -LiteralPath $SourceRoot).Path

if (-not (Test-Path -LiteralPath (Join-Path $sourcePath "data\ava.db") -PathType Leaf)) {
    throw "The expected legacy database data\ava.db was not found under $sourcePath."
}

$destinationPath = [System.IO.Path]::GetFullPath($DestinationRoot)
[System.IO.Directory]::CreateDirectory($destinationPath) | Out-Null

$stamp = [DateTimeOffset]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$archivePath = Join-Path $destinationPath "hermes-prototype-$stamp.zip"
$hashPath = "$archivePath.sha256"
$manifestPath = Join-Path $destinationPath "hermes-prototype-$stamp.manifest.json"

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$excludedParts = @(".git", ".venv", ".pytest_cache", "__pycache__")
$files = Get-ChildItem -LiteralPath $sourcePath -File -Recurse -Force | Where-Object {
    $relative = [System.IO.Path]::GetRelativePath($sourcePath, $_.FullName)
    $parts = $relative -split '[\\/]'
    -not ($parts | Where-Object { $_ -in $excludedParts }) -and
        $_.Extension -ne ".pyc" -and
        $_.Name -ne ".env"
}

$stream = [System.IO.File]::Open($archivePath, [System.IO.FileMode]::CreateNew)
try {
    $archive = [System.IO.Compression.ZipArchive]::new(
        $stream,
        [System.IO.Compression.ZipArchiveMode]::Create,
        $false
    )
    try {
        foreach ($file in $files) {
            $relative = [System.IO.Path]::GetRelativePath($sourcePath, $file.FullName).Replace("\", "/")
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive,
                $file.FullName,
                $relative,
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
        }
    }
    finally {
        $archive.Dispose()
    }
}
finally {
    $stream.Dispose()
}

$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath $hashPath -Encoding utf8 -Value "$archiveHash  $([System.IO.Path]::GetFileName($archivePath))"

$manifest = [ordered]@{
    schema_version = 1
    created_at_utc = [DateTimeOffset]::UtcNow.ToString("o")
    source_root = $sourcePath
    archive = [System.IO.Path]::GetFileName($archivePath)
    sha256 = $archiveHash
    file_count = @($files).Count
    exclusions = @(".git", ".venv", ".pytest_cache", "__pycache__", "*.pyc", ".env")
    contains_private_runtime_state = $true
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding utf8

Write-Output $archivePath
Write-Output "sha256=$archiveHash"
Write-Output "files=$(@($files).Count)"

