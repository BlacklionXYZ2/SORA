[CmdletBinding()]
param(
    [string]$UnityPlayer = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$evidenceRoot = Join-Path $projectRoot "docs/verification/p15-integrated-scenarios"
$logsRoot = Join-Path $evidenceRoot "logs"
New-Item -ItemType Directory -Force -Path $logsRoot | Out-Null

function Resolve-CommandPath {
    param([Parameter(Mandatory = $true)][string]$Command)
    $resolved = Get-Command $Command -ErrorAction Stop
    return $resolved.Source
}

function Invoke-Captured {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [hashtable]$Environment = @{}
    )
    $logPath = Join-Path $logsRoot "$Id.log"
    $started = Get-Date
    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = Resolve-CommandPath $Command
    $info.WorkingDirectory = $projectRoot
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    foreach ($argument in $Arguments) {
        [void]$info.ArgumentList.Add($argument)
    }
    foreach ($name in $Environment.Keys) {
        $info.Environment[$name] = [string]$Environment[$name]
    }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $info
    if (-not $process.Start()) {
        throw "Failed to start scenario command '$Id'."
    }
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    $process.WaitForExit()
    $stdout = $stdoutTask.GetAwaiter().GetResult()
    $stderr = $stderrTask.GetAwaiter().GetResult()
    $finished = Get-Date
    $combined = @(
        "COMMAND: $Command $($Arguments -join ' ')"
        "STARTED: $($started.ToString('o'))"
        "FINISHED: $($finished.ToString('o'))"
        "EXIT_CODE: $($process.ExitCode)"
        ""
        "STDOUT"
        $stdout.TrimEnd()
        ""
        "STDERR"
        $stderr.TrimEnd()
        ""
    ) -join "`r`n"
    Set-Content -LiteralPath $logPath -Encoding UTF8 -Value $combined
    Write-Host "$Id exit=$($process.ExitCode) duration=$([math]::Round(($finished - $started).TotalSeconds, 2))s"
    return [pscustomobject]@{
        run_id = $Id
        command = @($Command) + $Arguments
        environment = [ordered]@{} + $Environment
        started_at = $started.ToString("o")
        finished_at = $finished.ToString("o")
        duration_seconds = [math]::Round(($finished - $started).TotalSeconds, 3)
        exit_code = $process.ExitCode
        status = if ($process.ExitCode -eq 0) { "passed" } else { "failed" }
        log = "logs/$Id.log"
    }
}

function Assert-Passed {
    param([Parameter(Mandatory = $true)]$Run)
    if ($Run.exit_code -ne 0) {
        throw "Scenario run '$($Run.run_id)' failed; inspect $($Run.log)."
    }
}

Push-Location $projectRoot
try {
    if (-not $UnityPlayer) {
        $candidate = Get-ChildItem -LiteralPath (Join-Path $projectRoot ".local/releases") `
            -Recurse -File -Filter "SORA.exe" -ErrorAction SilentlyContinue |
            Where-Object FullName -Like "*\payload\unity\SORA.exe" |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($null -eq $candidate) {
            throw "No packaged P15.3 Unity player was found; pass -UnityPlayer explicitly."
        }
        $UnityPlayer = $candidate.FullName
    }
    $UnityPlayer = (Resolve-Path -LiteralPath $UnityPlayer).Path
    $runs = [System.Collections.Generic.List[object]]::new()

    $core = Invoke-Captured -Id "core-scenarios" -Command "uv" -Arguments @(
        "run", "--locked", "pytest",
        "tests/scenarios/test_integrated_user_scenarios.py",
        "tests/runtime/test_coding_workspaces.py::test_p06_coding_route_allocates_codex_worktree_and_captures_artifact",
        "tests/desktop/test_editor_handoff.py::test_exact_selection_reaches_task_and_finding_points_at_verified_line",
        "tests/voice/test_sessions.py::test_client_pipeline_keeps_pcm_local_and_completes_tts_playback",
        "tests/api/test_remote_access.py::test_paired_remote_session_is_scoped_revocable_and_audited",
        "tests/api/test_event_replay_and_reconnect.py::test_websocket_streaming_and_reconnect_replay",
        "-q"
    )
    $runs.Add($core)
    Assert-Passed $core

    $browser = Invoke-Captured -Id "browser-reconnect" -Command "node" -Arguments @(
        "--test", "clients/pwa/tests/pwa.test.mjs"
    )
    $runs.Add($browser)
    Assert-Passed $browser

    foreach ($project in @("windows_bridge", "windows_action", "media_fixture", "input_fixture")) {
        $build = Invoke-Captured -Id "build-$project" -Command "dotnet" -Arguments @(
            "build", "clients/$project", "--verbosity", "quiet"
        )
        $runs.Add($build)
        Assert-Passed $build
    }

    $unity = Invoke-Captured -Id "packaged-unity-physics" -Command "uv" -Arguments @(
        "run", "--locked", "pytest",
        "tests/embodiment/test_unity_player.py::test_packaged_unity_core_acceptance",
        "-q", "-s"
    ) -Environment @{
        SORA_UNITY_PLAYER = $UnityPlayer
        SORA_SKIP_NATIVE_INPUT_PROBE = "1"
    }
    $runs.Add($unity)
    Assert-Passed $unity

    $pressEvidence = Join-Path $evidenceRoot "secondary-monitor-press"
    New-Item -ItemType Directory -Force -Path $pressEvidence | Out-Null
    $press = Invoke-Captured -Id "packaged-secondary-monitor-press" -Command "uv" -Arguments @(
        "run", "--locked", "pytest",
        "tests/embodiment/test_unity_interaction.py::test_packaged_pause_records_one_verified_embodied_interaction",
        "-q", "-s"
    ) -Environment @{
        SORA_UNITY_PLAYER = $UnityPlayer
        SORA_TEST_UIA = "1"
        SORA_P11_REQUIRE_SECONDARY = "1"
        SORA_P11_EVIDENCE_DIR = $pressEvidence
    }
    $runs.Add($press)
    Assert-Passed $press

    $unitySource = Join-Path $projectRoot ".local/p09-unity-evidence/player/acceptance.json"
    foreach ($source in @($unitySource)) {
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Packaged Unity evidence was not emitted: $source"
        }
    }
    Copy-Item -LiteralPath $unitySource -Destination (Join-Path $evidenceRoot "unity-acceptance.json") -Force
    $unityEvidence = Get-Content -Raw (Join-Path $evidenceRoot "unity-acceptance.json") |
        ConvertFrom-Json
    $pressAcceptancePath = Join-Path $pressEvidence "acceptance.json"
    if (-not (Test-Path -LiteralPath $pressAcceptancePath -PathType Leaf)) {
        throw "Secondary-monitor press evidence was not emitted."
    }
    $pressEvidenceRecord = Get-Content -Raw $pressAcceptancePath | ConvertFrom-Json
    if (-not $unityEvidence.secondary_monitor_movement_tested) {
        throw "The packaged Unity scenario did not exercise secondary-monitor movement."
    }
    if ($pressEvidenceRecord.target_monitor.primary) {
        throw "The packaged press scenario did not target the secondary monitor."
    }

    $unityHash = (Get-FileHash -LiteralPath $UnityPlayer -Algorithm SHA256).Hash.ToLowerInvariant()
    $recordedAt = Get-Date
    $scenarios = @(
        [ordered]@{
            scenario_id = "conversation"
            title = "Immediate companion conversation"
            status = "passed"
            run_ids = @("core-scenarios")
            evidence = @("logs/core-scenarios.log")
            environment = "Hermetic Core with the configured deterministic dialogue fixture."
            limits = @("No live hosted dialogue model was invoked; this proves routing and availability semantics.")
        },
        [ordered]@{
            scenario_id = "telemetry-file-analysis"
            title = "Exact two-file telemetry analysis while SORA remains responsive"
            status = "passed"
            run_ids = @("core-scenarios")
            evidence = @("logs/core-scenarios.log")
            environment = "Temporary UTF-8 CSV files and a delayed deterministic specialist running through canonical task orchestration."
            limits = @("The specialist is deterministic, not live Hermes/Sol; arbitrary telemetry formats remain provider/tool concerns.")
        },
        [ordered]@{
            scenario_id = "isolated-coding"
            title = "Codex-style isolated coding worktree"
            status = "passed"
            run_ids = @("core-scenarios")
            evidence = @("logs/core-scenarios.log")
            environment = "Real temporary Git repository/worktree with a protocol-faithful fake Codex app server and host verification."
            limits = @("No live Codex quota or remote model was consumed; provider transport and host-side isolation are the claims.")
        },
        [ordered]@{
            scenario_id = "exact-editor-context"
            title = "Exact editor selection handoff and finding presentation"
            status = "passed"
            run_ids = @("core-scenarios")
            evidence = @("logs/core-scenarios.log")
            environment = "Owned repository fixture, exact bytes/digest/selection, provider task, and verified-line presentation."
            limits = @("Uses a deterministic editor/UIA fixture rather than the user's live VS Code session.")
        },
        [ordered]@{
            scenario_id = "multi-monitor-pointing-press"
            title = "Packaged avatar movement and verified Pause on monitor two"
            status = "passed"
            run_ids = @("packaged-unity-physics", "packaged-secondary-monitor-press")
            evidence = @(
                "unity-acceptance.json",
                "secondary-monitor-press/acceptance.json",
                "logs/packaged-unity-physics.log",
                "logs/packaged-secondary-monitor-press.log"
            )
            environment = "Actual attached Windows displays, packaged Unity player, WinForms media fixture on the non-primary display, UIA InvokePattern, and postcondition verification."
            limits = @("The target is a deterministic media fixture, not Spotify; no display settings or power state were changed.")
        },
        [ordered]@{
            scenario_id = "physics"
            title = "Packaged movement, ragdoll recovery, support surfaces and feedback"
            status = "passed"
            run_ids = @("packaged-unity-physics")
            evidence = @("unity-acceptance.json", "logs/packaged-unity-physics.log")
            environment = "Packaged Unity player connected to a fresh temporary Core on the actual desktop."
            limits = @(
                "Physics is the bounded screen-plane implementation; no unconstrained rigid-body or limb-level desktop collision claim is made.",
                "The primary-display raw input/drag probe was not rerun because an unrelated full-screen application obscured the owned fixture; packaged ragdoll, recovery, support-surface and secondary-motion paths were run."
            )
        },
        [ordered]@{
            scenario_id = "voice"
            title = "Local streaming voice turn through authenticated Core"
            status = "passed"
            run_ids = @("core-scenarios")
            evidence = @("logs/core-scenarios.log")
            environment = "Deterministic VAD/STT/TTS/playback adapters with client-local PCM and authenticated semantic Core traffic."
            limits = @("No physical microphone/speaker or live speech model was used in this scenario run; P14 benchmark evidence remains separate.")
        },
        [ordered]@{
            scenario_id = "mobile-reconnect"
            title = "Paired browser-compatible TLS reconnect and projection convergence"
            status = "passed"
            run_ids = @("core-scenarios", "browser-reconnect")
            evidence = @("logs/core-scenarios.log", "logs/browser-reconnect.log")
            environment = "Real local TLS socket, one-time pairing/session/revocation, replay backlog, and two independent JavaScript projection stores."
            limits = @("Same-host browser-compatible fixtures used a test certificate; a physical phone with trusted production certificate remains P15.2's open gate.")
        }
    )
    $acceptance = [ordered]@{
        stage = "P15.4"
        status = "complete"
        recorded_at = $recordedAt.ToString("o")
        model = "GPT-5.6 Sol"
        source_revision = (& git rev-parse HEAD).Trim()
        environment = [ordered]@{
            os = [Environment]::OSVersion.VersionString
            machine = $env:COMPUTERNAME
            powershell = $PSVersionTable.PSVersion.ToString()
            python = (& uv run --locked python --version 2>&1 | Out-String).Trim()
            node = (& node --version 2>&1 | Out-String).Trim()
            dotnet = (& dotnet --version 2>&1 | Out-String).Trim()
            unity_player = $UnityPlayer
            unity_player_sha256 = $unityHash
            monitor_count = @($unityEvidence.topology.monitors).Count
            secondary_monitor_movement_tested = [bool]$unityEvidence.secondary_monitor_movement_tested
            press_target_monitor = $pressEvidenceRecord.target_monitor
        }
        runs = @($runs)
        scenarios = $scenarios
        summary = [ordered]@{
            passed = @($scenarios | Where-Object status -EQ "passed").Count
            failed = @($scenarios | Where-Object status -EQ "failed").Count
            total = $scenarios.Count
        }
        boundaries = @(
            "Live provider/model quality is separate from deterministic orchestration acceptance.",
            "A physical phone and production certificate trust remain the independent P15.2 gate.",
            "The scenario suite changes no display, power, firewall, service, scheduled-task or repository state outside its temporary fixtures and evidence outputs."
        )
    }
    $acceptance | ConvertTo-Json -Depth 12 |
        Set-Content -LiteralPath (Join-Path $evidenceRoot "acceptance.json") -Encoding UTF8
    Write-Output "P15.4 integrated scenarios passed: $($scenarios.Count)/$($scenarios.Count)."
}
finally {
    Pop-Location
}
