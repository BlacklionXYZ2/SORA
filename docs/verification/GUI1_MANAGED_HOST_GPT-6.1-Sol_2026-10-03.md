# GUI-1a — opt-in managed desktop host progress

Contributor/model: **GPT-6.1 Sol**. Implementation checkpoint: **2026-10-03 22:06:25 +01:00**. Status: **in progress**, not GUI-1a or goal completion. Final native owned Quit was confirmed by **22:02:23 +01:00**. Earlier contributor reports and the three completed GUI-0 baseline/specification timestamps remain unchanged.

## Implemented

- `ManagedCoreOptions` uses typed `ProcessStartInfo.ArgumentList` and the fixed trusted manual startup script, preserving settings/llama/model/avatar/workspace/write repository/timeout/provider/voice setup choices. No encoded command is used in this new Shell path.
- Version-1 `CoreDescriptorStore` validates bounded readable profile/endpoint/token-path/PID-start/session hints and preserves invalid/competing files. Hints do not transfer shutdown authority. Unknown previous-launcher liveness prevents duplicate startup.
- `ShellCoreCoordinator` distinguishes occupied/absent/unknown listeners; authenticates profile/epoch and owned session; keeps recovery usable while waiting; exposes explicit Retry; waits for owned shutdown, launcher exit and listener absence. No auto-restart or force-kill fallback.
- `Program` acquires the profile singleton before managed services. Host/session/menu/settings integrate startup status and effect blocking. Managed native Quit explains consequences; IPC Quit refuses owned/pending managed shutdown rather than silently applying it.
- Root `Start-SORA.ps1 -Client Shell` is opt-in; Desktop remains default. Repeat launches reuse the primary. Default discovery reuses the saved endpoint. `start-manual-test.ps1` keeps native observation/capture/press/type and selected workspace wiring and supports deterministic QA. `start-full-sora.ps1` was not integrated.

The lifecycle credential is private ephemeral launch authority, not stored in descriptor/preferences/settings/projections/argv. Core consumes it before creating its model/provider/native-helper processes. Launcher/build subprocesses run before that consumption; this report does not claim the credential is absent from every ancestor/build process environment.

## Actual user-side QA and bugs found

Computer Use skill guided native inspection/interaction. Screenshots were inspected inline, not exported as evidence files. QA used `.local/gui1-managed-host-20261003`, a separate frontend verification environment, port **18794**, deterministic dialogue, `-NoAvatar`, and all eight static local companion capabilities disabled. No private documents, live model/provider requests, microphone or avatar were exercised.

1. Initial host **26564** stayed available with failed startup/no Core. Windows took **2.085 seconds** to return loopback ConnectionRefused, beyond the initial two-second probe deadline. Fixed probe to five seconds and added a real TCP occupied/refused test. This first attempt was a failure, not startup proof; the host was closed normally through native Quit.
2. Intermediate host **11940** started owned launcher **49312**, Sora **31124** and listener Python **52648**. Native Settings showed connected ownership and 84 canonical fields. Read-only commandline checks confirmed observation/capture/press/type/settings/workspace options present. Helper wiring is proven, not actual helper effects.
3. Same-profile root repeats **12332** (explicit port/Chat) and **43852** (no port/menu) exited as secondary forwarders without replacing host/Core. Native Chat truthfully showed **Model unavailable / Offline test model** and disabled Send. No prompt was sent; no draft typing or live reply is claimed. Native Chat close hid the panel while host/Core remained alive.
4. Intermediate native managed Quit returned **HTTP 400** and correctly retained recovery/Core. Found that C# `JsonContent` sent chunked JSON, unsupported by Core's parser. Changed the lifecycle request to fixed-length UTF-8 JSON and asserted positive Content-Length in the lifecycle client tests. The failed Quit is not passing evidence.
5. The running intermediate binary could not use the fix. After verifying exact QA PID/start/profile, a normal Ctrl+C console event was sent to its dedicated launcher console. QA Core/launcher/listener exited; native host Quit then closed the host normally. **This was graceful console cleanup, not proof of the new shutdown channel. No force kill was used.**
6. Final rebuilt source was launched through root Shell **without `-Port`**. Descriptor discovery reused 18794 rather than the ordinary default port. Host **27180** (22:00:47), launcher **34380** (22:00:49), Sora **46752** (22:00:56), Core epoch **0c11a36f-1f16-4cfa-96d2-1ccf20d6177b**, managed session **26f0c527-749d-4fad-9ad0-e73aed08c9b4** were correlated. Native managed Quit confirmation accepted the request. By **22:02:23**, QA host/Core/launcher and listener were absent and descriptor state was `stopped`. **This final flow needed no Ctrl+C or force termination.**

Native UIA focus/index metadata was sometimes stale; fresh screenshot-backed coordinates were used where required. An attempted composer focus did not establish typing readiness and was not followed by input. No repair/reset/security/privacy UI operation occurred.

## Fresh final-source verification

| Gate | Result |
|---|---|
| `scripts/verify.ps1`, with `UV_PROJECT_ENVIRONMENT=.local/frontend-verify-20261003` | Exit 0; lint/schema/compile checks passed; mypy 262 files; **703 Python passed /25 opt-in skipped in 115.17 seconds; 8 PWA passed** |
| C# component tests | **93 passed**, zero warnings/errors; prior total 84 plus nine descriptor/options/TCP instances; lifecycle request Content-Length assertion added |
| Shell/full app/widget builds | Zero warnings/errors on final source |
| Native managed root start/repeat/hide/final Quit | Narrow isolated evidence above; final owned exit/endpoint absence confirmed |

Opt-in Python skips remain skips, not native/model/hardware proof. No Unity suite was rerun in this slice. No live provider entitlement or managed GGUF readiness is inferred.

## Remaining acceptance and preservation

GUI-1a stays open: full launcher/specialist-option parity; Quit before API readiness; a deadline covering initialization cancellation as well as control/exit waits; unknown/mismatched listeners, stale/reused/inaccessible PIDs, host loss and shutdown timeout matrix. Descriptor concurrency/host-loss windows warrant further hardening; attachment after host loss never silently adopts ownership. Model readiness is separate from Core connectivity.

Physical mixed-monitor/DPI/accessibility, native owner-invoked UI reset/repair, production Chat/attachments/IME/scroll, retained secondary workflows, voice, full Settings, canonical Memory/semantic presentation, automations and final reference-style/default-release acceptance remain open.

Owner **Sora PID 52000**, start **2026-09-29 21:49:32**, remained running unchanged. No owner runtime/settings/model/avatar was restarted, no commit/reset or forced termination occurred. Synthetic QA profile/descriptor remains for inspectable test evidence. The overview and original GUI references are not edited.

**22:11:22 +01:00 final documentation/preservation check:** 65 local links across the five changed/new documents resolve. Root/manual PowerShell scripts parse without errors. All five reference byte sizes/SHA-256 hashes match the original manifest; overview diff is empty. Exactly the same three GUI-0 completion boxes retain 19:24:55 timestamps. `git diff --check` exits 0 (existing LF/CRLF conversion warnings only; untracked sources are outside that check). No QA host/launcher or listener18794 remains; only owner Sora52000 with its unchanged start time is running.

[Roadmap](../../SORA_GUI_IMPLEMENTATION_ROADMAP.md) · [Host runbook](../runbooks/SORA_DESKTOP_SHELL.md) · [Progress changelog](../../changelog/2026-10-03T220625+0100_GUI1-MANAGED-HOST-PROGRESS_GPT-6.1-Sol.md).
