# P09 implementation follow-through

> Subsequent continuation: actual Unity 6.6 compilation, Windows packaging and native-input results are now recorded in [the GPT 6 Astra Unity 6 acceptance report](P09_UNITY6_ACCEPTANCE_GPT-6-Astra_2026-09-10.md). The earlier installation limitation below is retained as dated history.

- Model name: **GPT 6 Astra**.
- Verification record: **2026-09-09 18:25:45 +01:00 (Europe/London)**.
- Status: **source integration and available verification completed; full phase acceptance blocked on Unity/editor and packaged hardware verification**.
- Full change inventory: [model-attributed changelog](../../changelog/2026-09-09T182545+0100_P09_GPT-6-Astra.md).
- Preserved starting evidence: [morning P09 repair](P09_REVIEW_AND_REPAIR_2026-09-09.md).

## Implemented

1. Added a pinned Unity project entrypoint, bootstrap scene and stable asset metadata. Corrected the invalid UniVRM Git package names/paths to `com.vrmc.gltf` at `Assets/UniGLTF` and `com.vrmc.vrm` at `Assets/VRM10`, version 0.128.0. Built-in rendering with D3D11/BitBlt is configured by the build entrypoint; no URP is needed for this baseline. Runtime material shaders are explicitly retained during packaging.
2. Added runtime VRM loading, cancellation/error handling, normalization to a 300px character, humanoid head binding, deterministic idle/walk pose, camera/light/collider creation and component wiring. An unavailable avatar reports `visible=false`. Added unmodified Seed-san by VirtualCast, Inc., with embedded permission settings and visible/distributed attribution. SHA256: `624D0D554BC205BBDC33E22A68A2C3C20EDEBB3E573011EAD8878A65E5329B23`.
3. Added actual Windows monitor enumeration with physical rectangles, work areas, DPI, primary identity and orientation. Thread DPI awareness is restored after enumeration. Safe placement considers the avatar's footprint and work-area exclusions, with deterministic bounded behavior on tiny monitors. Movement reports the actual safe anchor.
4. Added a viewport reconciler covering negative/offset virtual-desktop coordinates. Native display/DPI/settings/power notifications, polling and resume/focus invalidation trigger reconciliation. Commands wait for a matching Core snapshot; failures, topology changes and disconnect clear movement/gaze/markers. Reconnect does not replay historical commands. Native overlay placement uses no-activate styles/flags to avoid deliberately taking keyboard focus. Removed the ineffective late process-DPI-setting call; window/render DPI alignment remains an explicit packaged test.
5. Added authorized expiring marker commands, optional target rectangle/identity, reported interpreted target, and semantic action phase hooks. Core rejects rectangles crossing a monitor boundary or containing offscreen geometry and clears interpreted targets on topology change. A phase is presentation input only; it authorizes and proves no OS effect. The marker has no collider or input injection.
6. Added debug frame timing, anchor/nav/gaze crosses, target identity, explicit depth/reach-plane diagnostics and opt-in bounded JSON performance evidence. IK remains P11. Added four actual Unity PlayMode test cases and a fail-fast editor/build script, although these could not be executed here.
7. Extended portable C# and Python regressions and the real cross-language probe. The native probe can now write the current display snapshot. Updated README/build/runtime instructions and the plan additively; retained the baseline overview and prior contributor evidence.

## Executed verification

| Check | Result and scope |
|---|---|
| Full `SORA_TEST_CSHARP=1` Python suite | **214 passed in 18.51s**. No live reasoning-provider calls. |
| Final `scripts/verify-embodiment.ps1` | Portable build **0 warnings, 0 errors**; **21 C# tests passed**; **33 Python embodiment tests passed in 1.15s**, including actual loopback C# ↔ Core. |
| Ruff | Passed for `src`, `tests`, and contract exporter. |
| Strict mypy | Passed, **117 source files**. |
| Schema freshness and compileall | Passed. Four embodiment schemas regenerated. |
| Added marker-state invalidation assertions | Final focused file: **6 passed** after adding assertions; full suite count unchanged. |
| Actual Windows monitor enumeration | Passed in C# and captured through the native probe. Snapshot below. |
| PowerShell build harness | Parser passed; invocation fails clearly at missing-editor prerequisite. |
| Git whitespace check | Passed; existing LF/CRLF notices are unrelated to acceptance. No staging/commit/tag performed. |

The loopback probe sends move, show-marker, presentation-phase and hide-marker commands under persisted synthetic test grants, checks interpreted-target state at Core, reconnects without replay, changes topology, rejects stale commands and closes the client while Core remains alive. This verifies the transport and Core boundary; it does not run Unity or prove rendered effects.

The [actual Windows display snapshot](P09_WINDOWS_DISPLAY_SNAPSHOT_2026-09-09.json), captured at 17:20:03 UTC, reports:

- Virtual bounds: x=-1280, y=0, width=5120, height=2160.
- Primary DISPLAY1: 3840×2160 at (0,0), DPI scale 1.5; work area 3840×2088.
- Secondary DISPLAY6: 1280×1024 at (-1280,813), DPI scale 1.0; work area 1280×976.

This is actual enumeration on an offset mixed-DPI desktop. It is not evidence of moving the Unity overlay across these monitors, changing their settings, unplugging hardware, or sleep/resume.

## Environment block

No Unity editor, Hub, or licensed installation was found in the checked standard locations or PATH. The official Unity 2022.3.74f1 installer was downloaded to `.local/toolchains/UnitySetup64-2022.3.74f1.exe` (3,511,915,136 bytes). Authenticode validation returned **Valid**, signer **Unity Technologies SF**. Windows then canceled the installer launch with “The operation was canceled by the user.” No installation or activation success is claimed; the launch was not retried around that cancellation.

`scripts/build-embodiment.ps1 -TestOnly` consequently stopped with the missing-editor prerequisite. Unity C# compilation, package resolution, PlayMode tests and Windows packaging are **not run**, not passed. No executable or Unity performance measurements were produced. The installer remains available for the user to install/activate. The working editor path may be passed via `-UnityEditor` or `SORA_UNITY_EDITOR`.

## Remaining packaged acceptance

After installation/activation, run the build command in `clients/unity/README.md`. Record date, editor/package lock, GPU/API, monitor layout and observations separately from synthetic fixtures.

| Scenario | Required observation | Current status |
|---|---|---|
| Import/build/VRM | Resolve packages; pass all four PlayMode tests; produce player; see recognizable licensed VRM with working head/pose. | Not run |
| Overlay/input | Transparent background, topmost character, avatar receives clicks, unrelated controls in another process receive clicks through empty overlay; keyboard focus is not stolen. | Not run |
| Controller | Idle, left/right movement, clamped look-at and safe work-area anchor; no provider request from frame loop. Close/reopen Unity and verify Core remains usable and old movement is absent. | Portable transport passes; Unity not run |
| Coordinate alignment | Compare rendered crosses and rectangle edges against known fixture physical pixels on both current monitors, including negative offset/gap boundaries. Error within one physical pixel. | Mathematical fixtures pass; rendered check not run |
| Topology/recovery | Change resolution/DPI/taskbar edge, disconnect a display and sleep/resume. Revision advances when layout changes; old command stops; avatar remains visible in a valid work area. | Native enumeration and synthetic placement pass; transitions not run |
| Marker/semantic phase | Show/expire/hide rectangle without changing Windows pointer; inspect matching target ID; inject reach/contact/cancelled phases and observe hook without an OS action. | Core/C# transport passes; rendering not run |
| Performance | Run idle and movement separately after warmup with evidence directory set; record mean/p50/p95 and available CPU/GPU frame time, plus profiler CPU/GPU utilization. Assess stable 60 FPS on this host. | Instrumentation supplied; no measurement |

Only P09.3's fixture-based coordinate acceptance is checked in the plan. P09.1/.2/.4/.5/.6 and the overall phase DoD remain open. The hooks do not implement P11 IK/action authorization; the sample character is not final art; this is not a release installer.

## Primary implementation references

- [Unity 2022.3.74f1 release/download](https://unity.com/releases/editor/whats-new/2022.3.74f1).
- [Unity flip-model setting and DWM transparency limitation](https://docs.unity.cn/2023.3/Documentation/ScriptReference/PlayerSettings-useFlipModelSwapchain.html); the 2022.3 reference also exposes this setting. D3D11/BitBlt is a deliberate compatibility choice to be measured in the player.
- [UniVRM 0.128.0 VRM package](https://github.com/vrm-c/UniVRM/blob/v0.128.0/Assets/VRM10/package.json) and [runtime loader API](https://github.com/vrm-c/UniVRM/blob/v0.128.0/Assets/VRM10/Runtime/IO/Vrm10.cs).
- [Seed-san source/credit](https://github.com/vrm-c/vrm-specification/tree/master/samples/Seed-san) and [VRM Public License 1.0](https://vrm.dev/en/licenses/1.0/index); usage settings were read from the downloaded file's metadata.
