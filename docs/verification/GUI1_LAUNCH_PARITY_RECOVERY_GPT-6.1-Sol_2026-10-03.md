# GUI-1a — launcher parity and recovery hardening

Model/contributor: **GPT-6.1 Sol**. Checkpoint **2026-10-03 22:21:55 +01:00**. Status **in progress**. No new stage-completion timestamp; GUI-0's three completed specification/baseline dates remain unchanged.

## Implementation

- Full startup accepts opt-in Shell and forwards to root before helper build/setup/default-port logic. Typed root/manual/managed options preserve Codex and Antigravity models, supported effort, skip-permission opt-out, profile/settings/avatar/workspace/write repository/timeout/voice flags, and explicit versus default discovery. Compatibility clients remain available, Desktop still default. No speculative GUI redesign/default replacement.
- Full Shell uses canonical settings/defaults only; absence of its settings does not add manual startup's opportunistic legacy llama/external discovery. Existing Core legacy migration rules remain unchanged. Root/manual defaults retain their previous specialist override behavior; the full branch retains its previous skip-permission default and opt-out. No permission settings were changed during QA.
- Removed full launcher's unsupported Antigravity `max` option: Core accepts low/medium/high. Reject before startup, no silent conversion. Model IDs/control characters and boolean values are validated in managed options. Catalogue/provider readiness is not inferred from a forwarded string.
- Quit deadline starts before initialization cancellation/wait. Timeout/caller cancellation retain failure/recovery, forbid a late canceled launch or attachment commit, and do not kill external/owned services. Retry cannot start another initialization while the original remains pending.
- Descriptor save holds a non-linked cooperating-writer lock during fingerprint validation/replacement. Contention preserves original/current hints. Stopped descriptor retains the last Core epoch for inspection. This is not an adversarial filesystem transaction or atomic host-loss launch registration.
- Added boundary-I/O injection for coordinator tests, 10 recovery scenarios plus a descriptor-lock check and four invalid specialist-option cases: **93 →108 C# instances**. Added reusable `scripts/verify-shell-launchers.ps1` effect-free real-branch forwarding verifier.

## Component versus native evidence

Injected coordinator checks cover unknown listener; verified attachment without adopting saved ownership; mismatched identity without auto-picking a port; previous launcher alive/unverifiable/absent; explicit conflicting saved endpoint; corrupt hint preserved with no probe/start; hanging initialization and canceled attachment. Tests start no Core/helpers/providers. Liveness denial is **injected**, not an actual elevated-process proof. Real-loopback tests from the preceding slice remain in the C# suite. Timed-out initialization test also releases the original probe and proves no late child is started. Descriptor-lock test verifies contention/original preservation and successful explicit retry.

The PowerShell forwarding verifier extracts the actual full-launcher parameter block/Shell branch and invokes a temporary effect-free receiver. It checks legacy defaults, explicit path/model/effort/switch/timeout forwarding, no implicit explicit Port, and early `max` rejection. It does not execute a service or prove provider availability. Only its uniquely generated temp receiver/folder are removed afterward; production scripts/profile state are not replaced.

## Actual native full-launcher replay

Computer Use skill used for native GUI inspection/clicks; screenshots inspected inline, not saved. QA profile `.local/gui1-managed-host-20261003`, saved endpoint **18794**, frontend environment `.local/frontend-verify-20261003`, deterministic provider/dialogue, all eight local capabilities false, no avatar/voice/model/provider invocation. Launch:

```powershell
$env:UV_PROJECT_ENVIRONMENT = '.local/frontend-verify-20261003'
.\scripts\start-full-sora.ps1 -Client Shell -StateRoot .local/gui1-managed-host-20261003 `
  -NoAvatar -Provider deterministic -ShellPanel settings -CodexModel qa-codex-selection `
  -AntigravityModel qa-antigravity-selection -AntigravityEffort high -NoAntigravitySkipPermissions
```

Primary host **17016**, started **22:17:45 +01:00**; launcher **15912**, 22:17:48; Sora **58012** and Python **6312**, 22:17:53. Descriptor epoch **36adf416-de31-42ea-9d1a-670b5670a04f**, session **fde51c9d-dee4-4850-b1a6-ca87a31912e9**, state `owned`. Read-only exact QA commandline checks confirmed both specialist selections/high effort and absence of the skip-permission argument; only booleans, not raw credential-bearing commandlines, were printed. The diagnostic PowerShell process itself also contained query strings and was excluded from ownership evidence.

Settings accessibility showed owned Core connected, model readiness separate and canonical projection. Initial occluded screenshot showed the editor rather than Settings; it is **not visual proof of Settings**. The primary command menu was then explicitly activated and its fresh screenshot/tree showed connected ownership and reachable controls. Repeat full launch (no explicit Port/default panel) produced secondary **36876**, summoned that menu and retained primary/Core/session identity.

Fresh native Quit click opened the local consequence dialog. Fresh screenshot-backed Yes accepted it. Immediate observation still showed host while cleanup finished, so success was not inferred from the click. By **22:19:31 +01:00**, exact QA launcher/host/Core and listener18794 were absent; descriptor `stopped` retained the matching epoch. **No force kill or Ctrl+C was used this turn.** No prompt/draft typing, live model reply, avatar, microphone, helper effect or specialist task was tested.

## Fresh gates

- `scripts/verify.ps1` with the dedicated frontend environment: exit0; lint/schema/compile checks pass; mypy262 files; **703 Python passed /25 opt-in skipped in 102.73s; 8 PWA passed**.
- `dotnet test clients/csharp_tests/csharp_tests.csproj --verbosity quiet`: **108 passed, zero warnings/errors**.
- Shell/full-app/widget builds: zero warnings/errors. Four modified/added PowerShell scripts are checked separately for syntax/forwarding.
- `scripts/verify-shell-launchers.ps1`: defaults/explicit selections/unsupported-effort rejection passed; effect-free fixture only.

No Unity suite, real model/provider or hardware gate was rerun. Opt-in skips remain unverified.

## Remaining work / preservation

Pre-API graceful cancellation is still missing; a Quit during model/build startup may safely retain the host as unconfirmed. The new whole-operation deadline does not magically deliver that channel. Host-loss windows around child launch/descriptor registration, actual unresponsive control/cleanup recovery, physical inaccessible/PID/network failure matrix, native attached-Core behavior with the new coordinator, and broader GUI-0b/preferences/accessibility acceptance remain open. Existing component liveness/identity checks are not a substitute for those tests.

Production Chat/attachments/scroll/IME, retained task/content/integration surfaces, existing voice integration, full Settings, Memory/semantic services, scheduler, graph/reference styling and default-release parity remain planned. GUI-1a and the full goal stay active.

Owner Sora **52000**, start **2026-09-29 21:49:32.7934609 +01:00**, remained unchanged. No owner GUI/runtime/config/model restart, privacy UI mutation, forced termination, commit/reset or stage closure. Original reference images/design and overview preserved.

[Roadmap](../../SORA_GUI_IMPLEMENTATION_ROADMAP.md) · [Runbook](../runbooks/SORA_DESKTOP_SHELL.md) · [Progress log](../../changelog/2026-10-03T222155+0100_GUI1-LAUNCH-PARITY-RECOVERY-PROGRESS_GPT-6.1-Sol.md).
