[CmdletBinding()]
param(
    [string]$UnityEditor = $env:SORA_UNITY_EDITOR,
    [switch]$TestOnly,
    [switch]$SkipTests
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $UnityEditor) { $UnityEditor = Join-Path $env:ProgramFiles 'Unity/Hub/Editor/6000.6.0f1/Editor/Unity.exe' }
if (-not (Test-Path -LiteralPath $UnityEditor)) { throw 'Unity 6000.6.0f1 is required. Set SORA_UNITY_EDITOR or pass -UnityEditor.' }
$unityProject = Join-Path $projectRoot 'clients/unity'
$evidence = Join-Path $projectRoot '.local/p09-unity-evidence'
New-Item -ItemType Directory -Force $evidence | Out-Null
function Invoke-Unity([string[]]$Arguments, [string]$LogName) {
    $log = Join-Path $evidence $LogName
    $allArguments = @('-batchmode', '-projectPath', $unityProject, '-logFile', $log) + $Arguments
    $quotedArguments = $allArguments | ForEach-Object { '"' + $_ + '"' }
    $process = Start-Process -FilePath $UnityEditor -ArgumentList $quotedArguments -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(900000)) { $process.Kill(); throw "Unity exceeded 15 minutes. See $log" }
    if ($process.ExitCode -ne 0) { throw "Unity failed ($($process.ExitCode)). See $log" }
    if ((Get-Content -Raw -LiteralPath $log) -match '(?m)error CS\d+|Aborting batchmode|Failed to activate|Leak Detected') {
        throw "Unity reported compilation, activation, or native allocation failure. See $log"
    }
}
Invoke-Unity @('-quit', '-executeMethod', 'SoraBuild.Prepare') 'prepare.log'
if (-not $SkipTests) {
    $results = Join-Path $evidence 'playmode-results.xml'
    if (Test-Path -LiteralPath $results) { Remove-Item -LiteralPath $results }
    # No -quit: the test runner exits after writing results. Rendering remains enabled.
    Invoke-Unity @('-runTests', '-testPlatform', 'PlayMode', '-testResults', $results,
        '-assemblyNames', 'Sora.Embodiment.PlayModeTests') 'playmode.log'
    if (-not (Test-Path -LiteralPath $results)) { throw 'Unity produced no test results.' }
    [xml]$report = Get-Content -Raw -LiteralPath $results
    if ($report.'test-run'.result -ne 'Passed' -or [int]$report.'test-run'.total -lt 4) {
        throw "Unity tests did not pass. See $results"
    }
}
if (-not $TestOnly) { Invoke-Unity @('-quit', '-executeMethod', 'SoraBuild.Windows') 'build.log' }
Write-Host "Unity evidence: $evidence"
