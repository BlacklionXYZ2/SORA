# P13.1 desktop-event awareness — GPT-5.6 Sol

Status: **complete 2026-09-18 09:36:50 +01:00**.

P13.1 adds a volatile semantic event layer above P10's desktop perception and attention targets. It observes meaningful transitions, invalidates stale context, and emits bounded attention hints. It does not capture desktop content, call a provider, start inference, speak, or authorize an action.

## Event and authority boundary

- `DesktopEvent` represents foreground, top-level window, dialog, or canonical task changes using only event kind, identifiers, time, process/window identity, topology revision, and task status. Unknown fields are forbidden; window titles, UI text, pixels, frames and UIA contents are structurally absent.
- External producers send at most 128 timestamp-ordered events through `POST /api/v1/desktop/events` under exact `DESKTOP_OBSERVE` authority for `desktop.observe:events`. Topology and the complete batch are checked before the grant is consumed or context changes.
- `POST /api/v1/desktop/events/subscription` starts or stops the native source. Starting requires a reusable grant because the observation continues beyond one callback. The persisted approval/grant is rechecked for each callback; revocation stops the native source on its next delivery check.
- Task transitions are generated from canonical Core records. Client-supplied `task_changed` events are rejected so an external producer cannot fabricate agent completion.

## Windows subscription

`WindowsDesktopEventSource` owns a daemon message-loop thread and three out-of-context `SetWinEventHook` subscriptions:

| Native event | Semantic event |
|---|---|
| `EVENT_SYSTEM_FOREGROUND` | `foreground_changed` |
| `EVENT_OBJECT_CREATE` / `EVENT_OBJECT_DESTROY`, top-level window object only | `window_opened` / `window_closed` |
| `EVENT_SYSTEM_DIALOGSTART` / `EVENT_SYSTEM_DIALOGEND` | `dialog_opened` / `dialog_closed` |

Callbacks read only the native handle and owning process ID, bind the current Core topology revision, and cross into the asyncio loop with `call_soon_threadsafe`. The source never calls `GetWindowText`, capture APIs, UI Automation, or a model. Shutdown posts `WM_QUIT`, joins the thread with a five-second bound, and fails visibly if the loop cannot stop.

## Burst and stale-context policy

- Exact event IDs are retained in a 1,024-entry ordered set. Same-ID/same-payload replay is `deduplicated`; same-ID/different-payload reuse is rejected.
- Semantic repeats with the same kind and process/window or task/status identity are `debounced` for 350 ms. Semantic keys and device invalidation clocks are independently bounded to 1,024 entries.
- A foreground/window/dialog burst invalidates context at most once per 500 ms. Accepted events remain inspectable as at most 256 content-free decisions.
- Events must fall within a -5/+30-second live window. Desktop events must match the current topology revision.
- Context invalidation clears P10's raw cursor/selection buffers and expires spatial reference evidence without deleting canonical task/content/object referents. Window close marks matching targets unavailable; dialog lifecycle marks matching targets stale for revalidation.
- Dialog-open decisions carry `important`; terminal task decisions carry `notice`; all others carry `none`. These are data-only hints. The result contract fixes `inference_requests` and `speech_requests` to zero.
- Display-topology changes clear both raw attention and event debounce history and expire local spatial evidence.

## Acceptance evidence

The deterministic suite covers exact duplicate and semantic debounce behavior, multi-kind burst coalescing, context/reference/target invalidation, exact grant scope, stale topology, spoofed task rejection before grant use, canonical queued/completed task events, retry-safe task identity, subscription revocation, and native source shutdown. The native Windows test created all three real hooks on this host and stopped the message loop cleanly; it did not manufacture or claim a user-visible foreground/window change.

| Gate | Result |
|---|---|
| P13.1 focused acceptance | 6/6 passed, including native WinEventHook startup/shutdown |
| Retry regression | 1/1 passed |
| Repository | 287 passed, 9 explicit opt-in skips |
| Static/contracts | Ruff passed; strict mypy passed across 155 source files; schemas fresh; compileall passed |

Machine-readable evidence is in [`p13-desktop-events/acceptance.json`](p13-desktop-events/acceptance.json). Public schemas are [`desktop-event.schema.json`](../../contracts/schema/v1/desktop-event.schema.json), [`desktop-event-batch.schema.json`](../../contracts/schema/v1/desktop-event-batch.schema.json), [`desktop-event-batch-result.schema.json`](../../contracts/schema/v1/desktop-event-batch-result.schema.json), and [`desktop-event-subscription-request.schema.json`](../../contracts/schema/v1/desktop-event-subscription-request.schema.json).

P13.2 is next and owns on-demand scoped capture. P13.1 deliberately contains no frame or image data and does not begin a continuous vision loop.
