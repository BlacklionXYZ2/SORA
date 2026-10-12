[CmdletBinding()]
param(
    # Without this switch the script only lists what it would remove and how big it is.
    [switch]$Remove
)

# Frees about 22 GB in .local by removing a fixed, reviewed list of leftovers (2026-10-08):
# superseded P15 release builds, their test installs and unpacked zips, an obsolete Unity 2022
# installer, and an unused decision-layer attempt. Every item was checked on 2026-10-08: nothing
# runs from it and no document, verification record or changelog refers to it. Items cited as
# evidence, the owner's profile (manual-test), voice and the working decision layer are not on
# the list. Paths missing at run time are skipped. Windows PowerShell 5.1 compatible.

$ErrorActionPreference = "Stop"
$local = Join-Path (Split-Path -Parent $PSScriptRoot) ".local"
$items = @(
    "releases\sora-p15.3-acceptance-20260922-r2",
    "releases\sora-p15.3-acceptance-20260922-r2.zip",
    "releases\sora-p15.3-acceptance-20260922-r3",
    "releases\sora-p15.3-acceptance-20260922-r4",
    "releases\sora-p15.3-acceptance-20260922-r4.zip",
    "releases\sora-p15.6-acceptance-20260923-r2",
    "releases\sora-p15.6-acceptance-20260923-r2.zip",
    "releases\sora-p15.6-acceptance-20260923-r3",
    "releases\sora-p15.6-acceptance-20260923-r3.zip",
    "releases\sora-p15.7-acceptance-20260923-r1",
    "releases\sora-p15.7-acceptance-20260923-r1.zip",
    "releases\sora-p15.8-acceptance-20260923-r1",
    "releases\sora-p15.8-acceptance-20260923-r1.zip",
    "p15.3-release-acceptance-0b125baf-e0e8-492c-a1df-d0804be8387a",
    "p15.3-release-acceptance-6e590d34-7fae-452f-9108-e566ca286639",
    "p15.3-release-acceptance-a1156df8-8d68-4077-980d-44ff0a82e56e",
    "p15.3-release-acceptance-81132d82-d16c-4139-9981-ea71ee98fdb5",
    "p15.3-archive-extract-90fb55e6-425e-43da-ab9e-9e29db522186",
    "p15.3-archive-extract-daf62c0b-7133-4a56-85ea-1e7dc1574a5b",
    "p15.3-python\UnitySetup64-2022.3.74f1.exe",
    "decision-runtime",
    "decision-runtime.incomplete-20261008",
    "decision\runs\smoke-20261008"
)

$total = 0
foreach ($item in $items) {
    $path = Join-Path $local $item
    if (-not (Test-Path -LiteralPath $path)) { Write-Host ("  (gone)   {0}" -f $item); continue }
    $entry = Get-Item -LiteralPath $path -Force
    if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        Write-Host ("  (skipped, a link) {0}" -f $item); continue
    }
    $size = if ($entry.PSIsContainer) {
        (Get-ChildItem -LiteralPath $path -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    } else { $entry.Length }
    $total += $size
    if ($Remove) {
        Remove-Item -LiteralPath $path -Recurse -Force
        Write-Host ("  removed  {0,6:N2} GB  {1}" -f ($size / 1GB), $item)
    } else {
        Write-Host ("  would remove {0,6:N2} GB  {1}" -f ($size / 1GB), $item)
    }
}
if ($Remove) { Write-Host ("Freed {0:N1} GB." -f ($total / 1GB)) }
else { Write-Host ("{0:N1} GB would be freed. Run again with -Remove to delete these items." -f ($total / 1GB)) }
