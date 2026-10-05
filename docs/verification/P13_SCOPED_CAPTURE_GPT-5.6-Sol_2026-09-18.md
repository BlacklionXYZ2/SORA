# P13.2 scoped on-demand capture — GPT-5.6 Sol

Status: **complete 2026-09-18 09:57:44 +01:00**.

P13.2 adds a one-request/one-frame fallback for cases where semantic UI Automation is insufficient. Capture is explicitly authorized and bounded; it is not an ambient desktop feed, durable record, inference trigger, or action authority.

## Capture mechanism decision

The plan permitted `Windows.Graphics.Capture` or a supported equivalent. WGC is oriented around a capture item, Direct3D frame pool and session lifetime. That is useful for streaming but adds a longer-lived graphics/session boundary that P13.2 does not need. The implementation therefore uses a smaller one-shot Win32 equivalent inside the same killable helper architecture already proven by P10:

- Exact region: DPI-aware GDI `CopyFromScreen` for precisely the requested physical-pixel rectangle.
- Exact window: `PrintWindow` with `PW_RENDERFULLCONTENT` for the root window represented by an existing P10 desktop target.
- One request enters one helper process, produces at most one PNG JSON reply and exits. Hardware-accelerated or otherwise uncapturable windows fail `unavailable`; there is no broader screen-copy fallback for a failed window request.

This choice preserves a hard end to capture and avoids creating a persistent frame source. P13.3 can consume a retained frame but cannot turn this helper into a continuous VLM loop.

## Scope and authorization

- `DesktopCaptureRequest` selects exactly one source: a single-monitor `ScreenRect`, or a `desktop_target_id`. It carries the current topology revision and a retention TTL of at most 30 seconds.
- Region authority is exact: `desktop.capture:region:<revision>:<x>,<y>,<width>,<height>` with `DESKTOP_OBSERVE`.
- Window authority is exact: `desktop.capture:window:<desktop-target-id>` with `DESKTOP_OBSERVE`. Core resolves the target only in the authenticated owner/device/project scope, requires an active target/current topology and passes its PID, root HWND and process-start time to the helper.
- The helper independently rejects process-start or PID/HWND mismatch, elevation, hidden/minimized/closed windows, invalid geometry, more than 8,294,400 pixels, or more than 16 MiB of PNG data.
- Core consumes the grant before starting native work and polls persisted authorization at 50 ms intervals. Revocation, approval expiry or scope mutation cancels the capture task; bridge cancellation kills and reaps the helper. Authorization is checked again before any returned data is accepted.
- A topology change after launch returns `stale_layout` and retains nothing. Region requests that do not fit wholly on one active display fail before grant consumption or helper launch.

## Frame validation and retention

- The helper writes no capture file. It encodes the PNG from a `MemoryStream` and writes one bounded JSON line to stdout.
- Core requires a helper timestamp tied to the current request, validates base64, a 16 MiB byte limit, the PNG signature/IHDR dimensions, SHA-256, exact requested region or exact target process/window identity, and current topology.
- `DesktopCaptureStore` is process-memory only and keys frames by owner, device, project and capture ID. Defaults are eight frames and 32 MiB total; a frame is at most 16 MiB, 8,294,400 pixels and 30 seconds old.
- Oldest frames are evicted for capacity/byte pressure. Expired frames are pruned on access/insertion. All frames are cleared on display-topology change and runtime shutdown.
- The authenticated capture response contains the frame requested by that caller. Captures are absent from SQLite, canonical events, traces, ordinary projections and logs. No provider, dialogue path, VLM, speech system or action dispatcher is invoked.

## Acceptance evidence

The deterministic suite covers request exclusivity, exact resource construction, cross-scope absence, PNG signature/dimension/digest checks, TTL/capacity/byte eviction, exact API output, widened-region rejection, off-display rejection before grant use, active revocation cancellation, helper timeout/cancellation cleanup, and topology-change discard/store clearing.

The native WinForms fixture provided a real PID/HWND/process-start identity and known button rectangle. The built helper captured the whole target window using `PrintWindow` and the exact button rectangle using GDI. Core accepted both PNGs after independent dimension, digest, identity, topology, freshness and authority checks. The test did not send either image to a model.

| Gate | Result |
|---|---|
| Capture helper build | .NET 10, 0 warnings, 0 errors |
| Deterministic P13.2 acceptance | 6/6 passed; native test separately enabled |
| Real window + exact-region capture | 1/1 passed |
| Native desktop/vision suite | 57 passed, 1 explicit elevated/inaccessible-process skip |
| Repository | 293 passed, 10 explicit opt-in skips |
| Static/contracts | Ruff passed; strict mypy passed across 160 source files; schemas fresh; compileall passed |

Machine-readable evidence is in [`p13-scoped-capture/acceptance.json`](p13-scoped-capture/acceptance.json). Public schemas are [`desktop-capture-request.schema.json`](../../contracts/schema/v1/desktop-capture-request.schema.json), [`desktop-capture-frame.schema.json`](../../contracts/schema/v1/desktop-capture-frame.schema.json), and [`desktop-capture-result.schema.json`](../../contracts/schema/v1/desktop-capture-result.schema.json).

P13.3 is next and owns normalized, expiring vision evidence. This stage provides a bounded frame only; pixels do not authorize clicks, become permanent facts, or execute captured instructions.
