[CmdletBinding()]
param(
    # SORA profile folder; the default is the normal one used by the Desktop shortcut.
    [string]$StateRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) ".local/manual-test")
)

# Asks the running SORA to reflect once: she reviews the memories made since her last reflection
# against her goals and character, may note progress, add, revise or close goals, and may keep a
# thought. Prints what she did. Her goals are then readable in <StateRoot>\self\goals.md.
# Windows PowerShell 5.1 compatible.

$ErrorActionPreference = "Stop"
$descriptor = Join-Path $StateRoot "desktop-shell/runtime.json"
$tokenFile = Join-Path $StateRoot "private/sora-api-token"
if (-not (Test-Path -LiteralPath $descriptor) -or -not (Test-Path -LiteralPath $tokenFile)) {
    throw "SORA is not running for $StateRoot. Start it from the Desktop shortcut first."
}
$url = ((Get-Content -Raw -LiteralPath $descriptor | ConvertFrom-Json).core_url).TrimEnd("/")
$headers = @{ Authorization = "Bearer " + (Get-Content -Raw -LiteralPath $tokenFile).Trim() }
$result = Invoke-RestMethod -Method Post -Uri "$url/api/v1/self/reflect" -Headers $headers `
    -ContentType "application/json" -Body "{}" -TimeoutSec 600
Write-Host ("Reflected on {0} memories and {1} goals." -f $result.memories_seen, $result.goals_seen)
if (-not $result.actions) { Write-Host "She changed nothing." }
foreach ($action in $result.actions) {
    Write-Host ("- {0}: {1} {2}" -f $action.op, $action.status, ($action.goal, $action.reason -join " ").Trim())
}
$goals = Join-Path $StateRoot "self/goals.md"
if (Test-Path -LiteralPath $goals) { Write-Host "Her goals: $goals" }
