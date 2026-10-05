# P15.4 integrated user scenarios — GPT-5.6 Sol

Status: **complete 2026-09-22 19:29:02 +01:00**.

P15.4 adds one reproducible acceptance runner for the companion-first scenarios that cross phase
boundaries. The runner records commands, timing, environment, readable logs, linked structured
evidence and explicit limits in
[`p15-integrated-scenarios/acceptance.json`](p15-integrated-scenarios/acceptance.json). All eight
scenarios passed in the final run.

## Scenario acceptance

| Scenario | Result and linked evidence | Environment | Limits |
|---|---|---|---|
| Immediate companion conversation | Passed; [`core-scenarios.log`](p15-integrated-scenarios/logs/core-scenarios.log) | Hermetic Core and configured deterministic dialogue fixture | Proves routing and companion availability, not live hosted-model quality |
| Exact telemetry-file analysis while dialogue remains available | Passed; [`core-scenarios.log`](p15-integrated-scenarios/logs/core-scenarios.log) | Two exact temporary UTF-8 CSV files and a delayed deterministic specialist through canonical orchestration | Arbitrary formats and live provider tool quality remain provider concerns |
| Isolated coding | Passed; [`core-scenarios.log`](p15-integrated-scenarios/logs/core-scenarios.log) | Real temporary Git repository/worktree, protocol-faithful fake Codex app server and host verification | Consumes no live Codex quota; proves transport, isolation and artifact capture |
| Exact editor context | Passed; [`core-scenarios.log`](p15-integrated-scenarios/logs/core-scenarios.log) | Owned repository fixture with exact bytes, digest, selection, provider task and verified-line presentation | Does not claim a run against the user's live editor |
| Multi-monitor point and press | Passed; [`secondary-monitor-press/acceptance.json`](p15-integrated-scenarios/secondary-monitor-press/acceptance.json), [`packaged-secondary-monitor-press.log`](p15-integrated-scenarios/logs/packaged-secondary-monitor-press.log) | Packaged Unity player, actual attached displays, WinForms media fixture on non-primary `DISPLAY6`, UIA `InvokePattern` and postcondition verification | Fixture is deterministic media, not Spotify; no display setting or power state changed |
| Physics and recovery | Passed; [`unity-acceptance.json`](p15-integrated-scenarios/unity-acceptance.json), [`packaged-unity-physics.log`](p15-integrated-scenarios/logs/packaged-unity-physics.log) | Packaged Unity player connected to a fresh temporary Core on the actual desktop | Bounded screen-plane physics only; the separately described primary-display native-input probe was not rerun |
| Local streaming voice | Passed; [`core-scenarios.log`](p15-integrated-scenarios/logs/core-scenarios.log) | Deterministic VAD/STT/TTS/playback adapters with client-local PCM and authenticated semantic Core traffic | No physical microphone/speaker or live speech model was used; P14 retains its independent benchmark evidence |
| Mobile-compatible reconnect | Passed; [`core-scenarios.log`](p15-integrated-scenarios/logs/core-scenarios.log), [`browser-reconnect.log`](p15-integrated-scenarios/logs/browser-reconnect.log) | Real local TLS socket, one-time pairing/session/revocation, replay backlog and two independent JavaScript projection stores | Same-host browser-compatible fixture and test certificate; physical phone/certificate trust remains P15.2's open gate |

## Multi-monitor and embodied evidence

The reference machine exposed two monitors. The secondary target was `DISPLAY6`, a non-primary
1280×1024 display at virtual coordinates `(-1280, 813)`. The media fixture's Pause control was
centered at `(-1052, 1018)`. The packaged avatar was first placed on that display, then completed the
normal registered `PRESS` lifecycle:

`target_selected → navigate → align → reach → contact → invoke → verify → retract → completed`

Core invoked the target through UIA, verified that playback changed from playing to paused and that
its clock stopped, and recorded one effect with no duplicate. Grant material was absent from Unity
commands and evidence.

The packaged physics run freshly exercised movement over both attached monitors, reconnect without
movement replay, front/back/left/right ragdoll recovery, constrained joints, pose-lease release,
moving/minimized/closed/occluded support surfaces, 28 SpringBone joints, semantic physics feedback
and scoped desktop-object look/point/touch affordances. It does not claim unconstrained rigid-body or
limb-level desktop collision.

An unrelated full-screen application obscured the owned fixture used by the primary-display raw
mouse-input/drag probe. The bounded ownership check refused to inject input, so the final P15.4 run
explicitly set `SORA_SKIP_NATIVE_INPUT_PROBE=1`. Consequently, raw cross-process input and the simple
drag/fall sub-check are recorded as **not run**, not passed. The independent secondary-monitor Pause
scenario still exercised the authorized UIA effect and verified its postcondition.

## Environment

- Windows NT 10.0.26200.0 on `OSCARS-PC`
- PowerShell 7.6.5
- Python 3.12.10
- Node.js v24.18.0
- .NET SDK 10.0.103
- Packaged P15.3 Unity player SHA-256:
  `718444f6a718fa668da96eb0a58445b009673310e6129152a63dbf7a92b8de00`

## Verification gates

| Gate | Result |
|---|---|
| `scripts/verify-user-scenarios.ps1` | 8/8 scenarios passed |
| Focused Core scenarios | 7 passed |
| Browser/PWA runtime | 7/7 passed |
| Windows bridge/action/media/input fixture builds | 4/4 passed |
| Packaged Unity physics/recovery/support run | passed |
| Packaged secondary-monitor press | passed, one verified effect |
| Full repository verification | 340 passed, 10 explicit opt-in native/Unity skips |
| Static/contracts | Ruff passed; strict mypy passed across 185 source files; schemas fresh; compileall passed |

Run the integrated acceptance again from the repository root with:

```powershell
.\scripts\verify-user-scenarios.ps1
```

The script selects a packaged P15.3 Unity player, writes readable logs below
`docs/verification/p15-integrated-scenarios/logs`, and replaces the structured P15.4 acceptance
record only after the constituent runs complete.

Roadmap after P15.4: **81/91 checklist items (89.0%)**. P15.5 is next; P15.2's physical paired-phone
and certificate-trust acceptance remains independently open. No commit, tag or staging operation was
performed.
