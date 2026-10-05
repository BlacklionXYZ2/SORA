# P12.1 grab/drag/release — GPT-5.6 Sol

Status: **complete 2026-09-16 20:21:08 +01:00**.

P12.1 adds local physical manipulation of SORA's avatar. It does not inject input into another application, call a desktop semantic action or create authority for P11 effects.

## Implementation

- `AvatarHitTest.TryGetAvatarHit` raycasts the overlay camera and accepts only a collider beneath an `AvatarHitTest` owner. This supports later modular child colliders without a fragile static collider list.
- `AvatarGrabController` records the raycast body contact as a physical-pixel offset from the feet anchor, stops scripted locomotion, and follows the pointer using a bounded spring/damper.
- Drag speed is capped at 4000 px/s. Release velocity is capped at 1400 px/s, decays exponentially and stops below 8 px/s. Work-area collisions clear the blocked velocity component.
- `WindowPresentation` polls the global left button only on Unity's main thread, calls Win32 `SetCapture` at grab start, retains nontransparent hit testing while dragging away from the body, and releases capture on button-up. Missing capture, pause, disable or teardown cancels immediately and discards release momentum.
- The existing P11 controller remains authoritative for embodied semantic actions. A running P11 interaction causes `CanAcceptPhysicalGrab` to reject a competing user grab; the grab itself remains presentation-only.
- Adjacent monitor work areas are treated as a covered union, fixing a discovered 180-pixel seam dead zone caused by the avatar footprint clamp. A real gap remains non-traversable and clamps safely.

## Acceptance evidence

Unity PlayMode covers collider-only initiation, body-anchor retention, a drag from a 100% primary to a 150% secondary, safe union/gap placement, release-speed bounds, eventual settling, and capture-loss cancellation with zero residual velocity. All 24 tests pass.

The rebuilt packaged player ran over an isolated owned WinForms fixture. The OS routed a blank point to that fixture and delivered its click; the avatar point routed to Unity and did not increment the fixture; a 150-pixel synthetic mouse drag began on the avatar while the fixture remained underneath; Core observed the avatar move by at least 75 physical pixels; a Core command restored the exact prior anchor. The overlay background remained composed white through transparency, and topmost/layered/noactivate styles remained set. The player then exited cleanly and reconnected without movement replay.

## Verification

| Gate | Result |
|---|---|
| Unity compile/PlayMode/build | 24/24 passed; Windows build succeeded |
| Packaged player | 1/1 passed in 73.76 s; actual click-through, avatar routing, drag/report/restore and reconnect |
| Focused Python embodiment | 34 passed, 4 explicit opt-in skips before the C# probe; final embodiment gate 35 passed, 3 skips |
| Portable C# | 22/22 passed, zero build warnings/errors |
| Full repository | 273 passed, 9 explicit opt-in skips; Ruff, strict mypy, schemas and compileall passed |

The accepted player SHA-256 is `718444F6A718FA668DA96EB0A58445B009673310E6129152A63DBF7A92B8DE00`. Machine-readable evidence is in [`p09-topology-p12-grab/acceptance.json`](p09-topology-p12-grab/acceptance.json).

## Repairs found during verification

The first cross-monitor fixture found that per-monitor footprint clamping prevented a spring from crossing an otherwise contiguous seam. The placement union repair preserves safe behavior over true gaps. The first packaged probes then exposed a fragile static collider registry: the rendered avatar was at the reported anchor, but its overlay hit region did not become an OS target. Parent-owned collider identification fixed the packaged path. The final run delivered both the blank fixture click and the avatar drag and passed shutdown/reconnect checks.

## Boundary and next work

P12.1 is complete. It does not provide gravity, falling, ragdoll, window support surfaces or semantic physics events. P12.2 secondary motion/simple falling is next.
