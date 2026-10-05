# SORA Windows action bridge — P11.3

This .NET 10 Windows helper performs one narrowly defined Level 3 semantic effect: UI Automation
`InvokePattern.Invoke` for a freshly revalidated `PRESS` target. It is disabled unless Core is
started with both trusted helpers:

```powershell
uv run sora --serve `
  --windows-bridge clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe `
  --windows-action clients/windows_action/bin/Debug/net10.0-windows/windows_action.exe
```

Build and run the owned native fixture acceptance with:

```powershell
.\scripts\verify-desktop.ps1 -Native
```

## Authority and contact protocol

`POST /api/v1/desktop/targets/<target-id>/press` accepts an `attempt_id` and a bounded expected
accessible name after the press. The request requires API authentication, the matching device, and
a persisted approved grant with operation `desktop.interact` and exact resource
`desktop.interact:<target-id>:press`. A presentation or navigation grant cannot be substituted.

At contact, Core reserves the attempt in SQLite, resolves the exact grant from persisted approval
evidence, consumes it, and reruns the bounded read-only UIA tree observation. Process start time,
window/runtime/automation identity, enabled state, accessible name, topology revision and physical
rectangle must still match the target used for reaching. Core marks the attempt `executing` before
starting the action helper, then performs one final authorization check.

The helper receives no bearer token, grant, provider credentials, shell command or arbitrary action.
It validates the process/start time/root window and exact UIA identity again, rejects elevated,
inaccessible, disabled, offscreen, renamed or moved controls, requires `InvokePattern`, and invokes
it at most once. It then reads the same control's accessible name until the specified changed
postcondition is observed or its bounded verification window expires. Animation completion and a
successful `Invoke` return are not treated as proof of the application-level effect.

## No-replay and failure semantics

The attempt ID is a durable idempotency boundary. Reusing it with identical input returns the
journaled result without revalidating, consuming another grant or invoking again. Reusing it with
different input is rejected. An attempt left in `executing` by Core restart becomes
`unknown_outcome`; it is never replayed. Cancellation, worker timeout, malformed output or transport
loss after the execution claim are likewise unknown unless Core has affirmative evidence that no
effect was attempted. Confirmed pre-effect authorization, target, configuration or native-support
failures are `failed`. Only an independently observed postcondition is `completed` and `verified`.

The worker is one-request/one-response, shell-free, non-elevating, limited to one concurrent call,
bounded by Core's three-second timeout and 16 KiB response limit, and killed/reaped on timeout or
cancellation. It does not synthesize pointer/keyboard input, focus arbitrary windows, read values or
password contents, enumerate unrelated processes, or retry an effect.

P11.4 supplies the first user-facing Pause choreography and full interaction-coordinator demo. This
helper is the verified Level 3 PRESS primitive, not a general autonomous desktop-control facility.
