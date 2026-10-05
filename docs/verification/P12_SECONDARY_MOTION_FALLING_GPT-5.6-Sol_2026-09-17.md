# P12.2 secondary motion and simple falling — GPT-5.6 Sol

Status: **complete 2026-09-17 11:09:00 +01:00**.

P12.2 introduces bounded presentation physics after P12.1 releases the avatar. Monitor work-area bottoms are the only support surfaces in this stage; selected window surfaces remain P12.4, and full-body ragdoll/recovery remains P12.3.

## Implementation

- P12.1 keeps raycast contact and spring dragging, then transfers its already capped physical-pixel release velocity exactly once to `AvatarSimplePhysicsController`. When simple physics is configured, the older release integrator is cleared rather than running alongside it.
- The simple controller applies 2400 px/s² downward gravity, caps horizontal release speed at 1400 px/s and fall speed at 2600 px/s, applies separate air/ground exponential damping, and stops below 8 px/s.
- Each frame simulates at most 100 ms and is divided into at most 1/120-second substeps. Long stalls cannot create an unbounded impulse or tunnel across a monitor support in one integration step.
- The existing topology/work-area placement contract supplies the initial P12.2 support surface. A landing zeros vertical velocity; ground damping settles horizontal velocity before the controller becomes inactive.
- Core locomotion or an active P11 interaction stops simple physics so two presentation owners cannot write the avatar transform concurrently. Capture loss, pause and teardown move a held/falling avatar to a safe support and clear velocity.
- Non-finite release velocity or simulation state triggers a safe work-area support reset, clears all physics velocity and resets SpringBone state. NaN/Infinity are never written to the transform.
- `AvatarSecondaryMotionTuner` sanitizes imported SpringBone stiffness to 0–4, gravity power to 0–1.5, drag to 0.35–0.9, radius to 0–0.2 and gravity direction to a finite unit vector. It applies runtime-only `BlittableJointMutable` settings through `Vrm10Runtime.SpringBone.SetJointLevel`; the VRM asset is not rewritten.
- The existing per-avatar `Vrm10FastSpringboneRuntimeStandalone` remains in use, preserving the P09 allocation/leak fix and avoiding global-service disposal races.

## Deterministic acceptance

Unity PlayMode performs 100 alternating drops on the 100% primary and 150% secondary layouts. Release vectors include both horizontal limits and varying upward velocity. Every drop reaches the current monitor work-area bottom, becomes inactive, has exactly zero residual velocity and retains finite world coordinates. Separate fixtures cover a non-finite release, a 1000-second frame input capped to bounded catch-up, explicit support loss, and the grab→physics handoff.

SpringBone fixtures sanitize invalid/explosive parameters and load the bundled licensed Seed-san VRM through the production standalone runtime. Runtime tuning finds and updates more than zero joints; the packaged player reports **28 tuned joints** on both initial launch and reconnect.

## Packaged Windows acceptance

The owned native-input fixture remained beneath the actual avatar. The probe routed blank input through the overlay, captured avatar input, lifted the avatar 160 physical pixels and released it. Core observed the drag and then a landing at `y=2087`, the actual 3840×2088 primary work-area bottom minus one physical pixel. A Core movement command restored the prior anchor; the player exited zero and reconnected without movement replay. No desktop content was captured and no external application received an avatar click.

The actual display topology remained the two-monitor 5120×2160 virtual desktop recorded for P09.4/P12.1. No physical monitor or power setting was changed.

## Verification

| Gate | Result |
|---|---|
| Unity 6000.6.0f1 PlayMode | 29/29 passed; P12.2 tests 5/5 |
| Unity Windows build | Passed; accepted launcher SHA-256 `718444F6A718FA668DA96EB0A58445B009673310E6129152A63DBF7A92B8DE00` |
| Packaged Core/player/native input | 1/1 passed in 78.84 seconds |
| Portable C# / embodiment | 22/22 C#; 35 passed, 3 explicit opt-in skips |
| Repository | 273 passed, 9 explicit opt-in skips |
| Static/contracts | Ruff passed; official locked mypy passed across 147 source files; schemas and compileall passed |

Machine-readable evidence is in [`p12-secondary-motion/acceptance.json`](p12-secondary-motion/acceptance.json). Raw logs and runtime files remain under ignored `.local/p09-unity-evidence`.

## Boundary and next stage

This is deliberately simple falling, not a Rigidbody ragdoll. It does not simulate bounce, limb collision, arbitrary UI geometry, window-top support, occlusion, get-up animation or semantic fall/land events. P12.3 owns ragdoll joints, orientation/settle classification, front/back/side recovery, controller arbitration during get-up and timeout reset.
