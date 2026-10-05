# SORA Unity embodiment

P09 targets **Unity 6.6 (6000.6.0f1)**, **UniVRM 0.131.2**, the built-in render pipeline, and Windows x64 Mono/.NET Standard 2.1. Actual Unity compilation, the original four P09 PlayMode tests, Windows packaging and isolated Core/player acceptance pass. P11.1 adds three passing PlayMode fixtures for semantic presentation and procedural reaching; P11.2 adds five for the shared registered-action lifecycle; P11.3 adds three registered PRESS outcome cases, bringing the current editor total to fifteen. Physical resolution/DPI/hotplug/sleep transitions remain separately unverified. See the [Unity 6 verification record](../../docs/verification/P09_UNITY6_ACCEPTANCE_GPT-6-Astra_2026-09-10.md), [P11.1 verification record](../../docs/verification/P11_ANIMATION_IK_PRESENTATION_GPT-5.6-Sol_2026-09-15.md), [P11.2 verification record](../../docs/verification/P11_ACTION_REGISTRY_LIFECYCLE_GPT-5.6-Sol_2026-09-15.md), and [P11.3 verification record](../../docs/verification/P11_AUTHORIZED_PRESS_GPT-5.6-Sol_2026-09-15.md). The earlier Unity 2022 attempt is retained as historical evidence.

## Build and test

Install and activate Unity 6000.6.0f1, with Windows build support. From the SORA repository root:

```powershell
.\scripts\verify-embodiment.ps1
.\scripts\build-embodiment.ps1
.\scripts\verify-packaged-embodiment.ps1
```

The second script imports packages, prepares project settings, runs fifteen PlayMode tests, and builds `clients/unity/Builds/Windows/SORA.exe`. Logs/results go to `.local/p09-unity-evidence`. `-TestOnly` omits packaging; `-SkipTests` is an explicit build-only option and does not establish test acceptance. A missing editor, activation failure, compile error, absent test results or unsuccessful build fails the command. The editor path can instead come from `SORA_UNITY_EDITOR`.

The third script starts an isolated temporary Core and the packaged player, runs movement/gaze/marker/reconnect checks and briefly opens a white input fixture beneath SORA. It verifies the target process before sending two test clicks and restores the pointer if it has not been moved independently. It captures only SORA's own camera, checks composed transparency at a fixture pixel and records about one minute of frame timing. Both test windows close automatically. It does not modify your normal Core's data or credentials.

`Assets/Scenes/SoraOverlay.unity` contains the bootstrap. `SoraBuild.Prepare` regenerates this bootstrap scene and its build settings, sets Direct3D 11 with the BitBlt presentation path, disables HDR/MSAA, enables background operation/frame statistics, and retains shaders used by runtime-loaded VRMs. It does not require a provider or serialize credentials. Use the **SORA** editor menu for interactive preparation/building. The default output is a development build for acceptance, not a signed release installer.

## Runtime configuration

Run a separately managed local SORA Core on port 8000. Before launching the player, provide these process environment variables from your existing approved Core configuration:

| Variable | Purpose |
|---|---|
| `SORA_API_TOKEN` | Local API bearer token; never put it in a scene or command line. |
| `SORA_CORE_PORT` | Optional local Core port, 1–65535; defaults to 8000. |
| `SORA_EMBODIMENT_CONNECT_GRANT` | Persisted grant for `embodiment.connect`. |
| `SORA_EMBODIMENT_TOPOLOGY_GRANT` | Persisted grant for `embodiment.topology`. |
| `SORA_EMBODIMENT_DEVICE_ID` | Device matching those grants; defaults to `device-local`. |
| `SORA_VRM_PATH` | Optional local VRM 1.0/0.x avatar; default is bundled Seed-san. |
| `SORA_DEBUG_OVERLAY=1` | Show coordinate/nav/gaze/target/frame diagnostics without taking keyboard focus. F12 also toggles them when Unity receives keyboard input. |
| `SORA_PRESENTATION_EVIDENCE_DIR` | Optional local directory for bounded `presentation-metrics.json` output after warmup and on exit. |

The renderer does not create grants, start/stop Core, or run inference. An external command caller needs its own `embodiment.command` grant and matching `X-SORA-Device-ID` header. The player stays disconnected/degraded when authorization is unavailable. A loaded avatar can remain visible while Core is offline. A missing/bad avatar is reported as not visible.

## Presentation and coordinate contract

Win32 enumeration supplies actual monitor bounds, work areas, DPI and primary display. One-second polling and Unity resume/focus callbacks trigger reconciliation. A snapshot matching the current native layout is required before applying commands. Topology loss, disconnect, mismatched snapshots and changes stop motion/gaze and clear the marker. Reports require the corresponding Core grant. Managed window-procedure subclassing was removed after a reproducible player-exit crash; dynamic `WS_EX_TRANSPARENT` hit testing provides click-through without that teardown hazard.

Positions are physical pixels in the Windows virtual desktop, with x right and y down; negatives and gaps are valid mathematical coordinates. World origin is the primary monitor's top-left, at **500 px/m**, x right/y up. The orthographic camera covers the whole virtual desktop at z=-10m; avatar feet/nav plane is z=0m and marker is z=-1m. DPI is metadata and is not multiplied into positions. The normalized avatar is 300 physical pixels tall. Movement destinations are adjusted to a safe feet anchor with a 90px half-width/300px height footprint inside a work area; the reported position is the actual adjusted anchor, not an assertion of reaching an unsafe requested point. Tiny displays use the largest feasible bounds. P12 owns richer support/physics.

Live commands use a current `topology_revision`, unique `command_id` and aware `created_at` within 30 seconds. Reconnect never replays historical movement. `queued` means accepted into a bounded live queue, not executed. The HTTP endpoint is `POST /api/v1/embodiment/command`; inspect `GET /api/v1/projections/embodiment` for state and interpreted target identity.

| Verb | Fields / behavior |
|---|---|
| `move_to` | `target_point`, `speed_px_per_sec`; deterministic movement. |
| `look_at` | `target_point`; clamped head gaze. |
| `set_state` | Semantic `idle`, `thinking`, `listening`, `speaking`, `waiting_for_agent`, `reading` or `typing`, plus optional `presentation_style`. Movement and looking remain derived from active commands. `idle` also stops motion/gaze and clears the marker. |
| `show_marker` | `target_point`, optional `target_rect`/`target_id`, `marker_duration_seconds` in (0,30]; rectangle must fit one active display and contain the point. |
| `hide_marker` | Clear independent marker. |
| `presentation_phase` | `semantic_action_id`, optional presentation-facing `semantic_action`/`presentation_style`, and one of navigate/align/reach/contact/verify/retract/completed/cancelled/failed. Publish a presentation hook without performing or proving an OS effect. |

The marker has no collider and never injects pointer input. Command handlers are registered independently; future P11 actions must retain the shared lifecycle/registry architecture.

## P14.4 audio-driven mouth and emotion

`AvatarVoicePresentationController` consumes only client-local, audio-derived presentation frames.
Each frame is bound to a playback ID, output epoch, exact sequence and monotonic PCM position. It
applies bounded mouth openness to the VRM `aa` expression and one coarse utterance emotion to standard
VRM expressions. Pause, interruption, output-device loss, disconnect, failure and normal completion
reset the mouth and emotion to neutral. A new playback rejects callbacks from every older identity or
epoch.

Voice frames are intentionally not `EmbodimentCommandDto` verbs and are not registered in
`SoraEmbodimentBehaviour`'s Core command map. Dialogue models can provide text and a coarse semantic
emotion through the voice pipeline, but they cannot send animation frames. The local audio client
derives frames from PCM amplitude and supplies them directly to the local presentation sink.

## P11.1 presentation and procedural reach

Semantic states/actions/styles resolve through `PresentationProfileRegistry` to replaceable blend,
gaze, reach, arm-choice and torso-pose parameters. `AvatarPresentationController` consumes those
parameters without branching on state names; adding a state such as THINKING is a profile
registration. Profiles are visual configuration, not capability grants or evidence of an effect.

`AvatarReachController` binds to the validated humanoid's upper/lower arms and hands, chooses a
reachable left/right arm, and applies deterministic two-bone fingertip IK after the idle and gaze
layers. Completion, interruption, replacement, disable and out-of-reach paths restore a valid idle
controller state and the pre-reach local pose. This layer does not invoke controls or inject input.
P11.2 supplies the generic registered-action lifecycle described below; P11.3 supplies its first
authorized action component and Core-owned effect boundary.

## P11.2 registered-action lifecycle

`EmbodimentActionRegistry` accepts independent action components that own their semantic-effect
start/polling, verification, controller requirements and cleanup. One
`EmbodimentInteractionController` drives every component through Navigate → Align → Reach → Contact
→ SemanticEffect → Verify → Retract. Its switches enumerate lifecycle phases only, never actions.

`PresentationOwnershipArbiter` atomically assigns locomotion/gaze/reach controllers and prevents a
second interaction from partially grabbing them. `AvatarInteractionEnvironment` connects the
generic phases to P11.1's profiles, gaze and reach, but intentionally supplies no OS effect.
Cancellation, timeout, target loss and disconnect before the semantic effect execute nothing and
release ownership. Interruption after an unverified effect attempt is `UnknownOutcome`; effect start
and polling are separate so a pending effect is not blindly repeated. Cleanup exceptions cannot leak
claims or turn verified work into a false failure.

P11.2 acceptance uses deterministic POINT/PRESS/new-action fixtures.

## P11.3 authorized PRESS

`AuthorizedPressAction` is an independently registered component that uses the same P11.2 lifecycle.
At semantic contact it calls Core through `IDesktopPressTransport`. Core consumes the exact
`desktop.interact:<target-id>:press` grant, performs fresh target/geometry revalidation, claims a
durable attempt ID, and calls the separately configured one-shot Windows action helper. The component
maps Core's authoritative no-effect, verified and uncertain results to Failed, Completed and
UnknownOutcome without making Unity animation authoritative.

The component receives its target-specific grant/postcondition through an injected resolver; neither
is serialized into a scene. P11.3 fixtures register it directly and cover all three terminal result
classes. A native Core fixture independently proves one real UIA `InvokePattern` press and unchanged
press count after duplicate contact. P11.4 still owns runtime coordinator wiring and the complete
walk/reach/contact/Pause demonstration.

VRM loading uses UniVRM's per-avatar standalone spring-bone runtime so its native buffers share the avatar's disposal lifetime. PlayMode enables allocation stack tracing; the build harness rejects native leak reports. Periodic metrics survive scene teardown without reading already-destroyed objects.

## Avatar credit and acceptance

Bundled **Seed-san © VirtualCast, Inc.**, unmodified, is used under [VRM Public License 1.0](https://vrm.dev/en/licenses/1.0/index) and its embedded settings. Keep [the attribution](Assets/StreamingAssets/AVATAR_LICENSE.md) and metadata with builds. This is a verification character, not SORA's final character design. Configure your own avatar through `SORA_VRM_PATH` and retain its required attribution.

Complete the verification record's packaged acceptance matrix before closing P09: avatar render, transparency/topmost, avatar clicks/cross-process pass-through, motion/gaze/reconnect, topology changes/sleep, marker/hook behavior and measured frame performance. CPU/GPU timing values of zero mean unavailable. The metrics file deliberately does not assert visual alignment or click-through; those require separate observation.
