# P12.4 window surfaces — GPT-5.6 Sol

Status: **complete 2026-09-17 12:06:01 +01:00**.

P12.4 extends P12.2's deterministic falling without turning the desktop into a dense collider mesh. Monitor/taskbar support is derived from the accepted topology, and only deliberately selected window tops cross the Core-to-Unity boundary.

## Implementation

- `AvatarSupportSurfaceController` resolves the nearest support crossed by a downward physics substep. A monitor whose work area ends above its physical bottom exposes `taskbar`; otherwise it exposes `monitor_bottom`.
- Core's authorized, non-replayed `set_supports` command carries at most 32 `window_top` entries. Each entry has only an identifier, physical rectangle, lifecycle state and timestamps—no title, text, process ID, window handle or captured content.
- A selected window surface lives for at most 30 seconds. Core rejects stale/expired observations, stale topology, duplicate IDs and rectangles outside one active display. Unity independently checks count, identity, topology and geometry.
- Active/moving surfaces may support the avatar. A moving surface carries the standing feet anchor only while the avatar remains horizontally covered and the resulting footprint stays inside a work area.
- Minimized, closed, occluded, omitted, expired and moved-away surfaces release support exactly once and call the existing bounded `LoseSupport` path. The avatar then lands on the next eligible selected window or topology-derived taskbar/monitor bottom.
- Unselected windows and individual UI elements never become colliders.

## Acceptance

Unity covers a selected-window landing before the taskbar; movement carry; minimized, closed and occluded release; missing, expired and moved-away release; taskbar versus monitor-bottom classification; stale revision; duplicate identity; and the 32-surface cap.

The rebuilt Windows player received one surface through Core's authorized embodiment command. It confirmed the snapshot, landed on `window_top`, moved upward with that surface, then resumed falling and settled on the host's actual `taskbar` after each of Minimized, Closed and Occluded. Native topology, P12.1 input routing, P12.2 landing, P12.3 recovery, SpringBone tuning, clean shutdown and reconnect remained green. No real external window was moved, minimized, closed or occluded; these lifecycle transitions were bounded synthetic selected-surface snapshots against the actual display topology.

## Verification

| Gate | Result |
|---|---|
| Unity 6000.6.0f1 PlayMode | 47/47 overall; P12.4 fixtures 7/7 |
| Packaged Core/player/native input | 1/1 passed in 95.01 seconds |
| Packaged surface lifecycle | Core snapshot received; moving carry and minimize/close/occlude fallback passed |
| Portable C# / embodiment | 22/22 C#; 39 passed, 3 explicit opt-in skips |
| Repository | 277 passed, 9 explicit opt-in skips |
| Static/contracts | Ruff passed; strict mypy passed across 148 source files; schema freshness and compileall passed |

Machine-readable evidence is in [`p12-window-surfaces/acceptance.json`](p12-window-surfaces/acceptance.json). Raw player logs remain under ignored `.local/p09-unity-evidence`.

P12.4 does not enumerate arbitrary windows, persist window metadata, model per-control geometry or claim that the synthetic lifecycle states changed an external application. P12.6 will connect policy-filtered desktop-object affordances separately.
