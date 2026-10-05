# Exercise the real full-launcher Shell forwarding branch against an effect-free
# temporary receiver. No service, helper, GUI, provider or settings mutation.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$parseTokens = $null
$parseErrors = $null
$fullAst = [System.Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $projectRoot 'scripts/start-full-sora.ps1'), [ref]$parseTokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'Full launcher parse failed.' }
$shellBranch = @($fullAst.EndBlock.Statements | Where-Object {
    $_ -is [System.Management.Automation.Language.IfStatementAst] -and
    $_.Clauses[0].Item1.Extent.Text -eq '$Client -eq "Shell"'
})
if ($shellBranch.Count -ne 1) { throw 'Expected one Shell forwarding branch.' }
$fixtureRoot = Join-Path ([IO.Path]::GetTempPath()) ('sora-launch-forward-' + [Guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $fixtureRoot
try {
    # A fixture receiver, not a modified production startup script.
    $receiver = @'
[CmdletBinding()]
param([string]$Client,[string]$ShellPanel,[string]$Provider,[string]$CodexModel,
    [string]$AntigravityModel,[string]$AntigravityEffort,[switch]$AntigravitySkipPermissions,
    [int]$TaskTimeout,[switch]$NoAvatar,[switch]$SetupVoice,[switch]$NoClient,
    [switch]$UnifiedSettingsOnly,[string]$StateRoot,[string]$Settings,[string]$AvatarPath,
    [string]$WorkspaceRoot,[string]$WriteRepo,[int]$Port)
$captured = @{}
foreach ($key in $PSBoundParameters.Keys) {
    $value = $PSBoundParameters[$key]
    $captured[$key] = if ($value -is [System.Management.Automation.SwitchParameter]) { $value.IsPresent } else { $value }
}
$captured
'@
    [IO.File]::WriteAllText((Join-Path $fixtureRoot 'Start-SORA.ps1'), $receiver)
    $branch = [ScriptBlock]::Create($fullAst.ParamBlock.Extent.Text +
        "`n" + '$projectRoot = $fixtureRoot' + "`n" + $shellBranch[0].Extent.Text)
    $defaults = & $branch -Client Shell
    if ($defaults.Client -ne 'Shell' -or $defaults.ShellPanel -ne 'none' -or
        $defaults.CodexModel -ne 'gpt-5.6-luna' -or $defaults.AntigravityModel -ne 'gpt-oss-120b-medium' -or
        $defaults.AntigravityEffort -ne 'low' -or -not $defaults.AntigravitySkipPermissions -or
        -not $defaults.UnifiedSettingsOnly -or $defaults.ContainsKey('Port')) {
        throw 'Default forwarding changed legacy options or explicit/default port distinction.'
    }
    $selected = & $branch -Client Shell -ShellPanel settings -Provider deterministic -Port 18897 `
        -CodexModel "synthetic codex ' selection" -AntigravityModel 'synthetic antigravity selection' `
        -AntigravityEffort high -NoAntigravitySkipPermissions -NoAvatar -SetupVoice -NoClient `
        -StateRoot 'profile path' -Settings 'settings path' -AvatarPath 'avatar path' `
        -WorkspaceRoot 'workspace path' -WriteRepo 'write path' -TaskTimeout 731
    foreach ($pair in @(@('Port',18897), @('ShellPanel','settings'), @('Provider','deterministic'),
        @('CodexModel',"synthetic codex ' selection"), @('AntigravityModel','synthetic antigravity selection'),
        @('AntigravityEffort','high'), @('AntigravitySkipPermissions',$false), @('NoAvatar',$true),
        @('SetupVoice',$true), @('NoClient',$true), @('UnifiedSettingsOnly',$true), @('StateRoot','profile path'),
        @('Settings','settings path'), @('AvatarPath','avatar path'), @('WorkspaceRoot','workspace path'),
        @('WriteRepo','write path'), @('TaskTimeout',731))) {
        if ($selected[$pair[0]] -ne $pair[1]) { throw "Forwarding mismatch: $($pair[0])" }
    }
    $activity = & $branch -Client Shell -ShellPanel activity
    if ($activity.ShellPanel -ne 'activity' -or $activity.Client -ne 'Shell') {
        throw 'Activity entry did not forward through the real Shell branch.'
    }
    foreach ($panel in @('agents', 'paths', 'board', 'content', 'integrations', 'voice', 'memory')) {
        $entry = & $branch -Client Shell -ShellPanel $panel
        if ($entry.ShellPanel -ne $panel -or $entry.Client -ne 'Shell') {
            throw "Secondary panel entry did not forward: $panel"
        }
    }
    $rejected = $false
    try { $null = & $branch -Client Shell -AntigravityEffort max }
    catch [System.Management.Automation.ParameterBindingException] { $rejected = $true }
    if (-not $rejected) { throw 'Unsupported max effort did not fail before launch.' }
    Write-Host 'Shell full-launcher forwarding: defaults, explicit selections, Activity/Agents/Paths/Board/Content/Integrations/Voice/Memory and unsupported-effort rejection passed.'
    Write-Host 'Effect-free fixture only; native lifecycle acceptance is recorded separately.'
}
finally {
    # Validate the exact generated fixture target before removing its two files.
    $fixtureAbsolute = [IO.Path]::GetFullPath($fixtureRoot)
    $tempAbsolute = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if (-not $fixtureAbsolute.StartsWith($tempAbsolute, [StringComparison]::OrdinalIgnoreCase) -or
        (Split-Path $fixtureAbsolute -Leaf) -notlike 'sora-launch-forward-*') {
        throw 'Unsafe fixture cleanup target; files retained.'
    }
    Remove-Item -LiteralPath (Join-Path $fixtureAbsolute 'Start-SORA.ps1') -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $fixtureAbsolute
}
