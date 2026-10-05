# GUI-1a — pending startup Quit addendum

Model/contributor **GPT-6.1 Sol**. Checkpoint **2026-10-04 00:21:53 +01:00**. Status **in progress**; no stage closure. Continues [launcher parity/recovery](GUI1_LAUNCH_PARITY_RECOVERY_GPT-6.1-Sol_2026-10-03.md) without replacing its historical evidence.

## Changes

`ShellCoreCoordinator` now keeps an owned Quit pending until its Core exposes an authenticated, exact-profile/epoch/session API, within the whole-operation deadline. The host remains `stopping`/effect-blocked throughout readiness; it never briefly returns to send-ready state. It then requests the correlated shutdown, waits for the exact launcher and verifies listener absence. If the child exits before readiness, absence must still be proven. Timeout retains the child/host/ownership and explicit recovery, without auto-restart or force kill.

Readiness now uses an eleven-minute cancellation deadline including probe/identity/lifecycle I/O; the previous iteration-only clock check could not bound a long read. No credential is reconstructed from a descriptor. Added a control-client boundary factory for effect-free coordinator tests, retaining the authenticated production default.

This is **deferred shutdown after readiness**, not immediate pre-API cancellation of builds/model loading. A long pre-API startup can outlast Quit's deadline; the host reports unconfirmed cleanup and remains available. That architectural gap is still open.

## Verification

Final C# **111 passed, zero warnings/errors** (108 previous plus three instances): a real effect-free hidden owned child and synthetic HTTP handler simulate late API readiness followed by authenticated shutdown/normal stdin exit; a wrong-session projection sends no shutdown and retains the child; a never-ready API times out without killing the child and permits normal-exit cleanup/retry. No real model/provider/Core or helper effect is run by these cases. Synthetic children close normally, no Kill().

Final Shell/full-app/widget builds: zero warnings/errors. Effect-free `scripts/verify-shell-launchers.ps1` defaults/selection/rejection checks pass. **00:24:02 final full gate:** `scripts/verify.ps1` with `.local/frontend-verify-20261003` exits0; lint/schema/compile checks pass, mypy262 files, **703 Python passed /25 opt-in skipped in 102.99 seconds; 8 PWA passed**. These skips are not native/model/voice/hardware proof; Unity was not rerun.

Computer Use skill guided actual final-source full-launcher replay against the isolated deterministic profile `.local/gui1-managed-host-20261003`, endpoint18794, all eight capabilities false, no avatar/voice/provider requests. New host **29132** and launcher **48664**, epoch **2cbd9ca2-60a6-46ea-b3fa-c622b5426e60**. Initial native menu showed checking/starting. By the fresh native Quit-dialog observation and **00:21:26** metadata check, Core was already owned/listening. The native Yes click therefore proves **normal final-source owned Quit**, not actual pre-API timing. By **00:21:53**, host/launcher/Core/listener absent and stopped descriptor retained the matching epoch. No force termination/Ctrl+C, prompt/draft typing, model reply, voice/avatar or static access UI change.

Owner Sora **52000**, original start **2026-09-29 21:49:32.7934609 +01:00**, remained unchanged. Full goal, GUI-1a and the physical/failure/pre-API/host-loss gates remain open; production Chat and the later GUI services are still required. Reference/overview and contributor history are preserved.

**00:24:02 documentation check:** 79 local links across seven updated/new documents resolved before the later ownership-spec addendum. **00:25:02 final preservation check:** all five original reference sizes/hashes match, overview diff is empty, the same three scope-completion boxes retain 19:24:55 dates, QA listener absent and only unchanged owner Core52000 running. No QA processes were force-terminated.

[Roadmap](../../SORA_GUI_IMPLEMENTATION_ROADMAP.md) · [Runbook](../runbooks/SORA_DESKTOP_SHELL.md) · [Progress log](../../changelog/2026-10-04T002153+0100_GUI1-STARTUP-QUIT-PROGRESS_GPT-6.1-Sol.md).
