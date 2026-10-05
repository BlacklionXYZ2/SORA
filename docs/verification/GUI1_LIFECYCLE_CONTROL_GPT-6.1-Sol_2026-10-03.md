# GUI-1a managed lifecycle control foundation

Model name: **GPT-6.1 Sol**. Checkpoint: **2026-10-03 21:29:20 +01:00**, Europe/London. Status: **implemented control/client foundation; GUI-1a in progress**. No new whole-stage completion timestamp.

## Implemented

- New strict public `RuntimeLifecycle` / `RuntimeShutdownRequest` contracts and exported schemas. Public projection carries Core epoch, managed-session identity, state and accepted request identity, never the control credential.
- Authenticated owner-local lifecycle projection and shutdown route. External Cores refuse shutdown; remote sessions cannot use either route. Shutdown additionally requires a separate launch credential, explicit current Core epoch, exact managed session and bounded typed request. Exact request retry is idempotent; a different shutdown nonce is rejected.
- CLI consumes/validates paired launch environment variables before settings/model/provider/helper startup, removes them from its environment and keeps the secret in memory. Invalid/incomplete/non-serve managed configuration fails closed without echoing supplied values. No settings/policy toggle grants lifecycle authority.
- HTTP completion hook signals shutdown only after acknowledgement drain; failed delivery does not trigger cleanup and the same nonce can retry. Accepted shutdown fences new non-GET effects. The CLI awaits that event and executes existing avatar/API/runtime/settings cleanup; ordinary non-managed serving remains unchanged. Runtime startup is now inside its cleanup guard.
- Desktop `OwnedCoreLaunch` creates fresh session/credential and retains the exact child handle only after successful launch; clears retained StartInfo credentials, never reconstructs authority from a descriptor/PID/projection, never kills on Dispose. `ManagedCoreLifecycleClient` validates explicit profile/loopback/token, revalidates profile/epoch/session, rejects replacement ownership and mismatched ACK, bounds responses and reuses one shutdown nonce. It distinguishes ACK from process exit.

## Fresh verification

Dedicated Python environment: `.local/frontend-verify-20261003`; owner environment/profile not changed.

- `uv run --locked python scripts/export-contracts.py` generated the two new schemas; subsequent freshness check passed.
- Final `./scripts/verify.ps1`: exit 0; Ruff/schema/compileall passed; mypy **262 source files**; **703 Python passed /25 opt-in skipped in 87.53 seconds**; **8 PWA passed**.
- Final `dotnet test clients/csharp_tests/csharp_tests.csproj --no-restore`: **84 passed /0 failed /0 skipped**, zero analyzer warnings. Four new C# tests cover attached refusal, wrong profile/oversized projections, owned binding/retry/replacement epoch and wrong session/ACK.
- Final shell/full-app/widget builds: **zero warnings/errors** each.
- Actual isolated hidden `python -u -m sora` process, ephemeral loopback port, generated temporary profile, deterministic dialogue/reasoning and all eight local companion effects disabled. Authenticated identity/root/session verified; owner API token without launch authority returned 403 while child remained running; matching control returned 202 with exact request ID; child exited **0**, then health connection was refused. Output/settings did not contain the launch secret. The failure-only exact-child termination safeguard was not reached on passing runs.
- C# authority tests used hidden trusted effect-free Windows PowerShell children waiting on stdin. Each was released by newline/EOF, awaited and returned **0**; no Kill/process-name cleanup. HTTP projections were deterministic handler fixtures, not live Core/GUI integration.
- API/transport tests separately cover malformed/oversized requests, credential redaction/non-inheritance, remote/external/wrong credential/epoch/session rejection, exact nonce retry, acceptance versus delivered ACK, failed drain and shutdown admission fence.

Initial targeted runs found/fixed two line-length and one import-order lint issue. The first full gate had **1 failed /702 passed /25 skipped**: an existing CLI migration test double rejected the new lifecycle keyword. Updated its signature and added an assertion that ordinary launch remains unowned; the final full gate above passed. An initial C# analyzer warning was fixed before the final 84-test/build gate. Failed/intermediate runs are not passing evidence.

## Preservation, boundaries and next work

Owner Core remained **sora PID 52000**, start **2026-09-29 21:49:32**. No owner Core/model/avatar/voice/helper or GUI was restarted. No Computer Use/native GUI operation occurred this turn. No commit/reset, force termination on passing runs, user configuration edit, default-launch change or goal completion.

The new client is **not wired into ShellHost or the launchers**. Next: versioned profile discovery descriptor, singleton-before-launch, known/unknown listener distinction, fixed trusted helper-preserving launch arguments, readiness/startup failure recovery, owned process/endpoint absence checks and bounded shutdown reporting. Model startup before API readiness still requires host-side recovery/ownership handling; this channel alone cannot stop a Core that has not exposed its API. Do not duplicate or force-kill it as a workaround.

GUI-0b physical accessibility/DPI gates, owner-invoked preference reset/repair, production Chat/attachments/IME/scroll, retained secondary surfaces, voice, full Settings, Memory/Automation/semantic services and final visual/default-launch acceptance remain open. Existing attached-host Quit still leaves external Core running.

**21:32:46 +01:00 final documentation/preservation check:** All local links in the five changed/new documents resolve; the same three completed scopes retain their dates; five reference sizes/hashes match; overview diff is empty. No QA desktop host or Windows PowerShell test child remained; owner Core PID/start time was unchanged.

[Roadmap](../../SORA_GUI_IMPLEMENTATION_ROADMAP.md) · [Host runbook](../runbooks/SORA_DESKTOP_SHELL.md) · [Progress changelog](../../changelog/2026-10-03T212920+0100_GUI1-LIFECYCLE-CONTROL-PROGRESS_GPT-6.1-Sol.md).
