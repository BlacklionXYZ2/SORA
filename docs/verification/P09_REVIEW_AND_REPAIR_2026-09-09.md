# P09 independent review and repair

- Review/repair verification recorded: **2026-09-09 08:48:35 +01:00 (Europe/London)**.
- Reviewer: Codex, current task; original implementation attributed to Gemini 3.8 Flash.
- Outcome: **P09 is partially implemented. Portable/Core repairs verified; Unity/VRM/desktop acceptance remains open.**
- Scope: existing P09 source, Core API integration, Python/C# tests, ADR 0010, historical verification/changelog and current plan. No provider calls, personal data inspection, Git staging/commits or graphical desktop interaction.
- Environment: current locked Python environment, Windows, installed .NET SDK. Portable sources compile as .NET Standard 2.1; executable test host/probe targets .NET 10. No Unity editor was found on PATH or under the standard `C:\Program Files\Unity\Hub\Editor` location. No editor install, Unity license activation or avatar download was attempted.

## Findings and corrections

### 1. Discontinuous coordinates hidden by round-trip-only tests

The original transform scaled monitor-local offsets by DPI around monitor centers while placing those centers with unscaled physical pixels. On adjacent 1920-wide displays at 100%/150% DPI, `(1919,400)` mapped to roughly `(3.838,-0.8)` and `(1920,400)` to `(4.48,-0.8933)`: a one-pixel move jumped hundreds of equivalent pixels. Tests supplied the correct monitor hint to the inverse, hiding both the seam and nearest-center ambiguity.

Python and C# now map positions to one continuous plane:

```text
world.x = (global.x - primary.rect.x) / base_pixels_per_meter
world.y = -(global.y - primary.rect.y) / base_pixels_per_meter
world.z = 0
```

DPI remains display metadata and may affect avatar presentation size, not global position or pixel velocity. Inverse mapping needs no guessed monitor; gap coordinates remain mathematically representable but are rejected for commands. Added explicit seam/expected-position/inverse-without-hint tests, finite-value rejection and virtual-bounds containment checks. Existing eight-topology fixtures remain supported. Physical scale calibration, work-area/taskbar fixtures and camera projection still require the Unity slice.

### 2. The client and server did not share a functioning command protocol

Core expected an initial WebSocket hello and sent P08 events as `type=event` with `envelope`. The original C# client sent no hello, expected a different event shape, had no actual cursor implementation and parsed a different resync format. Core's embodiment queue was never registered by a real WebSocket consumer. HTTP nevertheless returned `dispatched` even with zero consumers or a full queue.

The repaired protocol explicitly separates durable P08 task events from transient P09 presentation:

- Authenticated WebSocket `/api/v1/events/ws` with hello `{"client_kind":"embodiment","since_sequence":0}`.
- Scoped persisted `embodiment.connect` grant, owner/device binding, one active embodiment consumer and a fresh `embodiment.snapshot`.
- Live `embodiment.command` messages; old movement is **not replayed** after reconnect. This prevents historical animations from becoming new actions. P08 durable task replay is unchanged.
- HTTP command response is `queued`, not a claim of physical execution. Disconnected/full queues, stale revisions, expired/future timestamps and off-display targets are rejected. Command IDs deduplicate within the bounded live session.
- Separate `embodiment.command` and `embodiment.topology` grants; authorization checked through Core, again before command delivery, and periodically for connection revocation/expiry.
- Topology updates invalidate queued old commands, send a new snapshot and clamp reported positions. Incoming state must match the current revision and containing monitor. Disconnect clears volatile connection state; initial 1080p topology is labeled `fallback`, not detected hardware.
- Bounded message size, cancellation/stop, reconnect backoff and HTTP timeouts; local-only plaintext transport prevents sending tokens to arbitrary remote hosts. Remote encrypted transport is still later work.

The real C# probe connects to the real Python Core on an ephemeral loopback port, hydrates a snapshot, sends/receives an authorized command, reports state and observes its postcondition, reconnects without old-command replay, reports a changed topology and verifies rejection of a stale command. Closing the C# client leaves Core serving. This is protocol acceptance with synthetic data, not a rendered-avatar test.

### 3. C# compatibility and Unity-thread boundaries

The original .NET 10 test project compiled only coordinate/network files and did not establish Unity compilation. Network code depended on System.Text.Json without a corresponding Unity package and used newer HTTP overloads.

Shared network/coordinate code now builds in `clients/core_transport/core_transport.csproj` targeting .NET Standard 2.1 with Newtonsoft.Json. The Unity manifest declares Unity's Newtonsoft package; package resolution and the complete VRM/URP stack still need an actual editor build. A `SoraEmbodimentBehaviour` source component wires snapshots, registered P09 commands, HUD, gaze/locomotion and bounded state feedback through main-thread `Update()` callbacks. Tokens/grants are read from environment rather than serialized into scenes. This component is **source-level work, not Unity-compiled or PlayMode-verified**.

### 4. Native hit testing and unsupported visual claims

The original native hook passed global Windows coordinates directly to Unity client-pixel raycasting and invoked Unity physics/camera APIs inside WndProc. It also relied on HTTRANSPARENT as proof of cross-process click-through.

Native source now converts coordinates with ScreenToClient, performs raycasts on the Unity main thread, uses a cached hit in WndProc, toggles layered-window WS_EX_TRANSPARENT for non-avatar areas, defers display callbacks to Update and restores captured styles/subclass on teardown. These changes require packaged visual/input acceptance; they are not certified by the portable tests. DPI-awareness timing, compositor/render-pipeline settings, focus behavior, alpha edges and cross-process input must be measured in the actual player.

Microsoft documents HTTRANSPARENT in terms of underlying windows on the **same thread**, so the original return value alone cannot establish click-through into unrelated apps. See [WM_NCHITTEST](https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-nchittest) and [layered-window hit testing](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features#layered-windows). Shared transport compatibility is deliberately checked against a portable target; see [Unity .NET profile guidance](https://docs.unity.cn/6000.1/Documentation/Manual/dotnet-profile-support.html) and [Unity Newtonsoft package](https://docs.unity3d.com/Packages/com.unity.nuget.newtonsoft-json@3.2/manual/index.html). These sources inform the repair; they do not replace local Unity acceptance.

### 5. Published schemas and repeatable checks

The prior report said embodiment contracts were registered, but the public schema registry omitted them. Registered/exported DisplayTopology, MonitorDescriptor, EmbodimentCommand and EmbodimentState. Added `scripts/verify-embodiment.ps1`, which fails immediately on a failed build/test/schema command. C#/Unity generated build products are ignored without deleting existing files.

## Verification performed

| Check | Current result |
|---|---|
| Original Python embodiment suite before repair | 19 passed |
| Original C# suite before repair | 11 passed; insufficient to reveal the above defects |
| `dotnet build clients/protocol_probe --verbosity quiet` | Passed; portable transport dependency built with zero warnings/errors |
| `dotnet test clients/csharp_tests --verbosity quiet` | **12 passed**, no skips |
| `scripts/verify-embodiment.ps1` | Passed; **27 Python embodiment tests**, including actual C# ↔ Core probe, plus C# and schema checks |
| `$env:SORA_TEST_CSHARP='1'; uv run --locked pytest -q` | **208 passed in 20.35 seconds**, no skips at that run |
| `uv run --locked ruff check src tests scripts/export-contracts.py` | Passed |
| `uv run --locked mypy src tests scripts/export-contracts.py` | Passed across **116 source files** |
| `uv run --locked python scripts/export-contracts.py --check` | Passed |
| `uv run --locked python -m compileall -q src tests` | Passed |
| `git diff --check` | Passed; existing Git newline-conversion warnings do not constitute whitespace errors |

The 208-test full run preceded the final small explicit `topology_source` label and incoming-JSON-object guard; the subsequent 27-test embodiment gate and full static/schema checks include them. Earlier Gemini 200-test and hardware claims are preserved as historical reports, not silently substituted for these current runs.

## Remaining original acceptance gates

All six P09 plan checkboxes remain open because their complete acceptance criteria have not passed:

1. Select the real editor/version and licensed VRM; create ProjectSettings, camera/render pipeline, scene and player build configuration. The repository currently contains scripts/manifest, not a ready packaged Unity project.
2. Compile and exercise the actual MonoBehaviours, scene wiring, idle/locomotion/gaze, safe hydration and independent client shutdown.
3. Finish work-area/taskbar fixtures and calibrate actual screen↔overlay↔world/depth projection. Choose and implement single-window versus per-monitor presentation with measured evidence.
4. Wire real Windows monitor/DPI/work-area enumeration and display/hotplug/sleep events into topology reports. The existing display callback alone does not enumerate monitors.
5. Record visual target alignment, transparency/click-through over unrelated apps, safe hide/exit, frame times and idle CPU/GPU. No 60 FPS result is claimed.
6. Implement and visually verify the separate SORA attention marker and semantic-hook presentation; a debug HUD is not the marker.

Do not treat a WinForms spike, a .NET test run or source-level controller edits as a licensed VRM packaged-player demonstration. No public endpoint, model invocation, P10 desktop action or speculative P11 physics implementation was added.
