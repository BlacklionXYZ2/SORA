[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "SORA/app"),
    [string]$StateRoot = (Join-Path $env:LOCALAPPDATA "SORA/state"),
    [string]$StartupEntry,
    [switch]$EnableStartup
)

$ErrorActionPreference = "Stop"
$bundleRoot = $PSScriptRoot
$python = Join-Path $bundleRoot "payload/core/python/python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Portable SORA Python runtime is missing: $python"
}
$arguments = @(
    "-m", "sora.operations.cli", "install",
    "--bundle", $bundleRoot,
    "--install-root", $InstallRoot,
    "--state-root", $StateRoot
)
if ($StartupEntry) { $arguments += @("--startup-entry", $StartupEntry) }
if ($EnableStartup) { $arguments += "--enable-startup" }
& $python -B @arguments
exit $LASTEXITCODE
