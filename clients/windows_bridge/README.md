# SORA Windows observation bridge — P10.1

This .NET 10 Windows helper supplies bounded, read-only UI Automation observations to Core. It is disabled by default. Build and exercise it from the repository root:

```powershell
.\scripts\verify-desktop.ps1 -Native
```

Run the completed Phase 10 acceptance matrix, including a live non-elevated probe against one
elevated process and one inaccessible protected process, with:

```powershell
.\scripts\verify-p10.ps1 -Full
```

That script refuses to claim the privilege result unless its caller has medium integrity. It locates
real targets on the current machine, requires the typed `elevated_target` and `access_denied`
responses, runs the owned UIA fixture and native desktop tests, and writes a redacted evidence record
under `docs/verification/p10-windows-bridge/`. It records process names and IDs but no window titles.

`-Native` briefly opens an owned WinForms fixture, checks control geometry/password redaction, hangs its UI thread deliberately and closes it after verifying timeout behavior. Without that switch, the script builds the helper and runs portable worker/authorization tests; the live fixture is opt-in through `SORA_TEST_UIA=1`.

Start the existing Core CLI with `--windows-bridge` pointing to the trusted absolute path of `clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe`. Keep its adjacent .NET runtime/configuration files. This operator configuration cannot be changed by an observation request. A missing helper yields `unavailable`; an unconfigured bridge yields `not_configured` after authorization.

## Core API

`POST /api/v1/desktop/observe` uses the existing API bearer authentication plus `X-SORA-Grant-ID` and `X-SORA-Device-ID`. The grant must have a persisted, approved exact `desktop.observe` operation and resource `desktop.observe:<process_id>`, with matching owner/device/project. The HTTP client cannot supply approval provenance or a helper command. The earlier generic `tool.invoke` bridge grant was replaced when P10.2 introduced the distinct Level 0–2 desktop operations.

```json
{"schema_version":"1.0","operation":"windows","process_id":1234,"max_nodes":64}
```

This enumerates visible top-level windows belonging to the approved process, including native handle, physical rectangle, enabled/minimized state and whether it is foreground. It does not enumerate unrelated processes' window titles. Use a discovered handle for a control tree:

```json
{"schema_version":"1.0","operation":"tree","process_id":1234,"window_handle":5678,"max_nodes":128,"max_depth":6}
```

Tree nodes expose bounded name/automation ID/control type, UIA runtime ID, physical screen rectangle when available, parent relationship, keyboard-focus/enabled/offscreen/password flags. Successful replies also include the observed process start time. Native target ownership is checked before and after traversal; cross-process child nodes are excluded. Names are redacted on password elements; ValuePattern/TextPattern contents are never read. Application-provided labels remain untrusted data. A rectangle is an observation, not proof of visibility, clickability or permission to act.

Node IDs remain local to one response. PID, HWND, and UIA runtime IDs can be reused and **are not authorization by themselves**. P10.2 wraps selected elements in a bounded, in-memory `DesktopTarget` containing the short-lived process-start/runtime/window identity and topology revision. Every later presentation or navigation attempt must supply a separate exact target-scoped grant and rerun the tree observation before Core will use the rectangle. No focus-changing, clicking, typing, selection capture or text extraction operation exists in this worker.

## Volatile targets and Level 0–2 authority

Acquire one target with a fresh Level 0 observation:

```text
POST /api/v1/desktop/targets
X-SORA-Grant-ID: <desktop.observe grant>
X-SORA-Device-ID: <device>
```

The body identifies the approved process/window and supplies a selector such as `runtime_id` or `automation_id`; zero matches, multiple matches, truncated uncertainty, offscreen elements, missing rectangles, or missing process identity fail closed. Targets expire after at most five minutes and are never persisted to canonical storage.

Before Level 1 presentation or future Level 2 navigation, revalidate with a distinct exact resource:

```text
POST /api/v1/desktop/targets/<target-id>/revalidate
{"authority":"present"}
```

Presentation uses operation/resource `desktop.present` / `desktop.present:<target-id>`. Navigation uses `desktop.navigate` / `desktop.navigate:<target-id>`. Neither grant substitutes for the other. Process restart, window/control disappearance, UIA identity ambiguity, expiry, topology changes, device mismatch, revocation, expiry, exhaustion, or in-flight authority changes prevent reuse.

P10.3 adds `POST /api/v1/desktop/targets/<target-id>/present` with `walk`, `turn`, or `point`. It revalidates under Level 1 and queues the corresponding P09 `move_to`, `look_at`, or `show_marker` command. This is presentation only: it does not focus a window, move the Windows pointer, invoke a control, or synthesize input.

## P10.4 cooperating-editor handoff

P10.4 deliberately does not infer a repository, file, or selection from window titles or arbitrary UIA labels. A local authenticated editor integration submits `POST /api/v1/editor/tasks` with its editor name, configured absolute repository root, repository-relative file path, saved-document SHA-256, one-based/end-exclusive selection, selected text, capture timestamp, and the volatile desktop target covering that selection.

Core requires a persisted `path.read` grant covering the resolved file, consumes it before reading, and independently verifies all of the following before creating the local-only task:

- the repository root is in `--editor-root` or is the configured managed Codex repository;
- the resolved file remains inside that root and is a bounded UTF-8 regular file;
- the saved bytes match the supplied document digest;
- the exact canonical-LF text at the supplied range matches the reported selection;
- the capture is at most 60 seconds old; and
- the desktop target is live and belongs to the same owner, device, and project.

The verified snapshot is stored with the task under normal task retention and enters the provider context ahead of conversation history. Selected text never enters trace fields. Missing metadata, dirty buffers, digest changes, path escape, stale capture, selection mismatch, budget exclusion, and target loss are reported rather than guessed. The initial slice supports clean saved UTF-8 documents; an editor adapter must save or report that the buffer cannot be verified.

A completed provider result may carry typed editor findings bound to the snapshot context ID and selection digest. `POST /api/v1/tasks/<task-id>/editor-finding` accepts only a finding actually present in that completed result, obtains a fresh exact `desktop.present:<target-id>` grant, revalidates current UIA geometry, and queues a marker over the finding's proportional line band. It cannot point at an invented finding and performs no editor or OS mutation.

## Bounds and failure behavior

- One outstanding worker per Core bridge. Concurrent requests receive `busy` rather than accumulating waiting workers.
- Each worker accepts one request over inherited stdin and returns one JSON line on stdout. It opens no listener and receives no API/provider credentials. Core launches it directly without a shell or elevation.
- Core enforces a three-second wall-clock deadline, a 512 KiB response-line limit and exactly one response. Timeout, malformed/oversized/extra output, cancellation and worker exit all clean up the owned child process.
- Requests cap nodes at 256 and depth at 12; strings are capped at 256 characters. `truncated` conservatively signals a traversal bound; it must not be interpreted as a complete tree.
- The worker rejects elevated targets before UIA traversal; access-denied tokens/providers, invalid handles, disappeared elements and hung windows return typed results. A native 200 ms liveness check catches the hung fixture; the parent deadline also bounds stalls inside UIA itself.
- Grants are consumed before observation, including failed attempts. A final-use exhausted grant may receive that result, but further requests fail. Revocation, expiry or changed approval/grant scope while waiting discards the result.
- If Core's display-layout revision changes during observation, the result is `stale_layout` with no nodes. This does not replace P09.4 physical display/power-transition acceptance.
- Observations remain transient API results. The production path does not write window/control contents into canonical memory or logs.

Result statuses: `ok`, `timeout`, `unavailable`, `access_denied`, `elevated_target`, `invalid_request`, `protocol_error`, `not_configured`, `busy`, `stale_layout`. Failed observations have no nodes. Invalid HTTP requests receive 400; missing/invalid/revoked authorization receives 403.

Microsoft documents why UI Automation must stay off the interacting application's UI thread and why its rectangles use physical coordinates: [threading guidance](https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/ui-automation-threading-issues), [physical screen coordinates](https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.automationelement.frompoint?view=windowsdesktop-10.0). SORA additionally isolates those calls in a killable process to bound provider stalls.

The [original P10.1 implementation record](../../docs/verification/P10_WINDOWS_BRIDGE_GPT-6-Astra_2026-09-10.md) preserves GPT 6 Astra's fixture and mocked privilege-error evidence. The [Phase 10 completion record](../../docs/verification/P10_PHASE_COMPLETION_GPT-5.6-Sol_2026-09-14.md) records GPT-5.6 Sol's limited-rights token-query repair and live privilege-matrix closure without replacing that attribution.
