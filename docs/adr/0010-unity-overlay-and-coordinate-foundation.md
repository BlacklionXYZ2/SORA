# ADR 0010: Unity Overlay and Coordinate Foundation

- Status: amended 2026-09-09; P09 partial, original completion claim superseded
- Date: 2026-09-08
- Completed: 2026-09-08 22:00:00 +01:00
- Model: Gemini 3.8 Flash

## Context

**Review amendment:** Use `docs/verification/P09_REVIEW_AND_REPAIR_2026-09-09.md` for current evidence. The decision below is preserved historically. Position now uses a continuous physical-pixel plane, with `x_world=(x-primary.x)/base_ppm` and `y_world=-(y-primary.y)/base_ppm`; DPI may affect avatar presentation size only. Monitor-center-dependent DPI scaling caused discontinuities and is superseded. The current presentation channel is live and snapshot-based; it does not replay old physical commands. P08 durable task-event replay is unchanged. Native `HTTRANSPARENT` alone does not establish cross-process click-through; a packaged overlay/input test is still required. No accepted Unity/VRM build or measured frame-time gate is claimed.

Phase P08 delivered the authenticated HTTP/1.1 and RFC 6455 WebSocket API boundary, fulfilling Gateway G3 ("Independent Client Interface"). However, SORA lacked physical desktop embodiment:
1. Multi-Monitor Coordinate Precision: SORA required an authoritative spatial foundation capable of addressing multi-monitor configurations (mixed resolution, mixed DPI scaling, portrait orientations, negative coordinates, and non-display gaps) with sub-pixel or $\le 1\text{ px}$ round-trip accuracy.
2. Desktop Overlay Presentation: The avatar embodiment must float directly on the Windows desktop over running applications, utilizing transparent background composition without obscuring user interaction.
3. Input Pass-Through vs. Avatar Hit-Testing: Transparent regions of the overlay window must pass mouse clicks through immediately to background applications (Notepad, browser, IDE), while direct clicks on the avatar character model must register interactions without latency or input capture leaks.
4. Core ↔ Embodiment Resilience: The Unity embodiment client must operate as an independent consumer of SORA Core; crashes, restarts, or frame drops in Unity must never interrupt Core task execution or reasoning loops, and zero model inference may run inside the 60 FPS update loop.

## Decision

### 1. Authoritative 4-Level Coordinate Foundation (`sora.embodiment.coordinates`, `CoordinateTransformer.cs`)
- **Level 1: Global Desktop Space (GDS)**: Integer physical pixels across the virtual desktop bounding box returned by Win32 `EnumDisplayMonitors` / `GetSystemMetrics`, with primary monitor at $(0, 0)$ and full support for negative coordinates.
- **Level 2: Monitor Identity Resolution**: Every point is validated against discrete `MonitorDescriptor` bounds. Points landing in non-display gaps are identified and clamped to the nearest visible display edge via Euclidean distance minimization.
- **Level 3: Monitor-Local Space (MLS)**: Physical pixels relative to each monitor's top-left origin: $x_m = X_g - \text{rect.left}$, $y_m = Y_g - \text{rect.top}$.
- **Level 4: Unity World Space (UWS)**: Decoupled presentation space in meters with monitor-specific presentation scaling ($S_m = \text{basePpm} \times \text{dpiScale}$), ensuring that perceived visual avatar dimensions remain consistent across monitors with differing pixel densities.
- **Fixture Parity**: Validated by 8 canonical topologies in `contracts/fixtures/coordinate_fixtures.json`, achieving $\le 1\text{ physical pixel}$ round-trip accuracy in both Python and C#.

### 2. Multi-Monitor Presentation Architecture Spike (`clients/win32_spike`)
- Conducted an empirical Win32 spike comparing:
  - **Strategy A (Preferred Direction)**: Per-monitor presentation surfaces/viewports.
  - **Strategy B (Fallback)**: Single virtual-desktop HWND spanning the entire virtual-screen bounding box.
- Verified on host dual-monitor hardware (`DISPLAY6` at $[-1280, 813, 1080 \times 1920]$ portrait, `DISPLAY1` at $[0, 0, 3840 \times 2160]$ 4K primary):
  - Confirmed DWM glass composition via `DwmExtendFrameIntoClientArea` with negative margins (`-1`).
  - Validated window subclassing with `WM_NCHITTEST` returning `HTCLIENT` over avatar visual bounds and `HTTRANSPARENT` over background desktop areas.
  - Adopted Strategy A with Strategy B fallback as the architectural standard for desktop overlays.

### 3. Non-Blocking Unity Client Architecture (`clients/unity/Assets/Scripts/`)
- **Native Presentation (`WindowPresentation.cs`)**: Configures `WS_POPUP`, `WS_EX_LAYERED`, `WS_EX_TOPMOST`, and hooks `WM_NCHITTEST` / `WM_DISPLAYCHANGE` to re-enumerate topologies upon display changes.
- **Networking (`SoraCoreClient.cs`)**: Non-blocking `ClientWebSocket` event loop with sequence replay, `resync_required` detection, exponential backoff reconnection, and HTTP topology reporting (`POST /api/v1/embodiment/topology`).
- **Deterministic Locomotion (`AvatarLocomotion.cs`)**: Smooth ground-plane translation at constant velocity across display seams without teleporting.
- **Clamped Gaze (`AvatarLookAt.cs`)**: Directs head orientation toward physical screen pixels with anatomical limits ($[-60^\circ, +60^\circ]$ yaw, $[-30^\circ, +30^\circ]$ pitch).
- **Fast Hit-Testing (`AvatarHitTest.cs`)**: Collider raycasting determining whether cursor coordinates hit the avatar.
- **Debug HUD (`DebugOverlayHUD.cs`)**: Toggleable F12 HUD displaying real-time topology, world/desktop coordinates, hit-test status, and connection health.

### 4. Core Embodiment API Integration (`sora.contracts.embodiment`, `sora.api.routes`, `sora.runtime.service`)
- Registered `EmbodimentCommand`, `DisplayTopology`, `MonitorDescriptor`, and `EmbodimentState` contracts.
- Exposed `GET /api/v1/projections/embodiment`, `POST /api/v1/embodiment/command`, and `POST /api/v1/embodiment/topology`.
- Enforced topology revision checks (`STALE_TOPOLOGY_REVISION` HTTP 409) to reject obsolete spatial commands.

## Consequences

- SORA establishes its first physical desktop embodiment milestone, fulfilling the P09 embodiment foundation.
- Full coordinate math parity is guaranteed between Core and Unity via shared fixtures and verified C# / Python test suites.
- Desktop overlay transparency and click-through are empirically validated against the Windows DWM compositor.
- All 200 Python tests pass cleanly in 19.7s; all 11 C# xUnit tests pass in 36ms; strict mypy typing holds across 114 source files.

## Reversal

The coordinate transformation engine and display topology manager are decoupled from renderers and OS window handles. The Unity embodiment client can be replaced or augmented with other presentation frontends (e.g. WPF, Unreal, Godot, WebGL) by consuming the identical `/api/v1/projections/embodiment` API and `contracts/fixtures/coordinate_fixtures.json` contracts.
