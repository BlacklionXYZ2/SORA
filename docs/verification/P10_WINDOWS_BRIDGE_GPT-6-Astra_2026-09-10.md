# P10.1 Windows bridge — GPT 6 Astra

Recorded **2026-09-10 09:15:32 +01:00**. Status: **first implementation slice verified; P10.1 in review; Phase 10 in progress**. P09.4 remains deferred/open by the user's sequencing decision.

## Delivered

A real .NET 10 Windows helper enumerates the approved process's visible windows and bounded UI Automation control trees, with physical rectangles and focus/enabled/offscreen/password flags. Core exposes `POST /api/v1/desktop/observe` using existing bearer authentication and exact persisted `tool.invoke` grants scoped to `desktop.observe:<pid>`. The operator supplies a trusted helper path through `--windows-bridge`; default configuration leaves it disabled.

Each observation runs in a separate MTA console process over inherited stdin/stdout. Core caps concurrent workers at one, enforces a three-second deadline and 512 KiB response bound, and kills/reaps stalled, malformed or cancelled workers. Native traversal has maximum depth/node/string bounds. No helper listener, elevation, input injection, focus mutation, ValuePattern/TextPattern reading or production observation persistence was added.

Grant use is consumed before observation. Revocation, expiry or changed approval/grant evidence while awaiting the worker discards its result. A Core topology revision change likewise returns `stale_layout` without nodes. Password nodes redact names and no field values are requested. UIA labels are untrusted external data.

## Executed evidence

| Check | Actual result |
|---|---|
| `dotnet build clients/windows_bridge --verbosity quiet` | Succeeded, zero warnings/errors. |
| `dotnet build clients/uia_fixture --verbosity quiet` | Succeeded, zero warnings/errors. |
| `scripts/verify-desktop.ps1 -Native` | 12 tests passed in 2.44 seconds at the focused run. |
| Full suite with `SORA_TEST_CSHARP=1` and `SORA_TEST_UIA=1` | **226 passed, 1 skipped in 20.89 seconds**. The skipped test is the separate opt-in Unity packaged player, which this P10 change did not rebuild or rerun. |
| Ruff | Passed. |
| Strict mypy | Passed over 124 source files. |
| Published schemas and compileall | Passed. |

The full-suite run includes the final API allow/deny/device-scope assertions. Earlier focused runs exposed a test insertion syntax error and typing errors; those were corrected before the passing full/static gates.

The real WinForms fixture demonstrates:

- Scoped window enumeration returns the fixture's PID/HWND and title.
- UIA resolves `Confirm fixture` as a button with automation ID `fixture-confirm`.
- Its observed physical rectangle matches the independent fixture rectangle to within one pixel. The recorded run expects `(191,235,170,40)` and observes the same rectangle.
- The password element is identified, its name is redacted, and the sentinel password text is absent from the response.
- A one-node request returns one node with `truncated=true`.
- An invalid HWND returns `unavailable`.
- Deliberately hanging the fixture's UI thread returns `timeout`; the runtime remains responsive.
- After killing the owned fixture, another observation returns `unavailable`.
- Six observation attempts consume a six-use grant; a seventh attempt is denied.

[Archived fixture evidence](p10-windows-bridge/fixture-acceptance.json) contains only the owned fixture's observations, not unrelated desktop contents. [Evidence manifest](p10-windows-bridge/manifest.json) records file hashes and archive time.

Separate real-child-process tests verify a sleeping worker deadline, malformed/oversized/extra output, cancellation cleanup and busy behavior. `access_denied` and `elevated_target` results are exercised through deterministic child responses. Runtime tests cover missing/wrong-process/wrong-device/revoked authority, invalid API operations, disabled configuration, in-flight revocation and layout invalidation.

## Limits and next work

**Do not mark P10.1 complete yet:** the helper implements denied-token and elevated-target checks, but the full live matrix against inaccessible/elevated applications has not been executed. Deterministic error responses establish transport behavior, not native privilege classification. The observed focus fields are read-only; active focus-changing behavior belongs to navigation authority later.

The bridge enumerates windows for an explicitly authorized PID, not all desktop window titles. Request-local node IDs/PIDs/HWNDs are observations, not durable targets or approval tokens. P10.2 must establish process/window identity lifetime, target expiry, ambiguity handling and distinct observation/presentation/navigation authorization before these observations drive actions. P10.3 semantic pointing, P10.4 editor/file/selection handoff and P10.5–.7 attention/content display remain unimplemented by this slice.

P09.4 physical resolution/DPI/hotplug/sleep acceptance remains open. Layout invalidation here is a Core revision test and does not substitute for that hardware gate. No previous stage is reopened or marked complete by this change.

See [bridge build/API documentation](../../clients/windows_bridge/README.md) and [model-attributed changelog](../../changelog/2026-09-10T090638+0100_P10_GPT-6-Astra.md).

## 2026-09-10 P10.2/P10.3 continuation amendment

GPT-5.6 Sol continued from this verified P10.1 boundary without changing Astra's original attribution. The bridge now reports process start time and bounded UIA runtime IDs so Core can detect PID/HWND reuse during a short target lifetime. Desktop observation migrated from generic `tool.invoke` to the already-defined `desktop.observe` operation; target presentation and navigation use distinct exact `desktop.present:<target-id>` and `desktop.navigate:<target-id>` resources.

The continuation adds a bounded, non-persistent target registry, five-minute maximum expiry, cross-device/project isolation, process/layout/runtime-identity revalidation, ambiguity and truncation handling, and in-flight authority checks. Level 1 walk/turn/point requests revalidate before queuing P09 movement/look/marker commands. No focus, input, or UIA semantic action was added.

The native WinForms/UIA gate passed 20/20, including real process-start/runtime-ID acquisition, target revalidation and a point command matching the fixture's independently measured rectangle. The native-enabled full suite passed 234 tests with only the separately opt-in packaged Unity player skipped. Detailed evidence and attribution are in `P10_TARGET_LIFECYCLE_PRESENTATION_GPT-5.6-Sol_2026-09-10.md` and `changelog/2026-09-10T191816+0100_P10-CONTINUATION_GPT-5.6-Sol.md`.
