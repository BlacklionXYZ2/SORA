# GUI-1a — managed host integration progress

Model/contributor: **GPT-6.1 Sol**. Logged **2026-10-03 22:06:25 +01:00**. Status **in progress**; no new stage completion. Final native owned-Quit check confirmed **22:02:23 +01:00**.

## Changes implemented

- Added `clients/desktop_shell/ManagedCoreOptions.cs`, `CoreDescriptor.cs` and `ShellCoreCoordinator.cs`: typed fixed-script launches, original-preserving profile discovery hints, identity/owned-session binding, listener/liveness checks, explicit recovery/retry and positively owned graceful Quit.
- Integrated options/coordinator into `ShellProfile`, `Program`, `ShellHost`, `ShellSession`, `ShellForm` and `CommandMenuForm`. The profile singleton precedes service launch; startup/failure status stays visible; managed Quit has a local consequence confirmation and uncertain cleanup retains the host. Secondary IPC cannot silently stop owned services.
- Added root opt-in `-Client Shell` / `-ShellPanel` path and manual-script deterministic-provider/voice-setup forwarding. Kept Desktop default, compatibility clients and observation/capture/press/type/model/settings/workspace/avatar options. Full startup script parity remains open.
- Fixed two bugs exposed by actual native testing: Windows loopback refusal required more than the original two-second probe deadline; lifecycle JSON needed Content-Length instead of unsupported chunked transfer. Added descriptor/options/real-TCP tests and a lifecycle wire-format assertion.
- Updated roadmap to v1.8, host runbook and dated ownership-specification notes; added detailed managed-host verification. Earlier contributor history and GUI-0 completion dates retained.

## Verification and limits

Final regression: **703 Python passed /25 opt-in skipped**, **8 PWA passed**, mypy262 files and lint/schema/compile gate passed; **93 C# passed**; Shell/full-app/widget final builds zero warnings/errors. Actual isolated native startup, repeat launches, Chat hide/model-unavailable status and final owned Quit were tested. Intermediate failed startup/Quit and its normal Ctrl+C cleanup are explicitly separated from final passing shutdown-channel evidence in the report.

Owner Sora PID52000/start time unchanged; no owner restart/configuration change, force kill, commit/reset or goal completion. This is not live-model, avatar/voice/helper-effect, full launcher, visual-reference or hardware/accessibility acceptance. GUI-1a remains open for full-launcher parity, pre-API/deadline/failure recovery matrix and broader placement/accessibility; subsequent GUI stages remain planned.

**22:11:22 final preservation check:** 65 document links valid; root/manual PowerShell AST checks pass; five original reference sizes/hashes preserved; overview unchanged; three original completed scope dates retained; QA host/launcher/listener absent and owner Core unchanged. Tracked diff whitespace check exits0 with existing line-ending warnings only.

[Verification](../docs/verification/GUI1_MANAGED_HOST_GPT-6.1-Sol_2026-10-03.md) · [Roadmap](../SORA_GUI_IMPLEMENTATION_ROADMAP.md) · [Runbook](../docs/runbooks/SORA_DESKTOP_SHELL.md).
