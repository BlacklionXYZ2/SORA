# Physics body and avatar layer: fixing the audit's findings

Model name: **Opus 5.5**. Checkpoint **2026-10-22 19:50:00 +01:00**, Europe/London (work from
2026-10-18). Status: **fixed and component-tested; the player is rebuilt but not launched, and the
owner hasn't reviewed it**.

The owner, after the audit of the physics engine and VRM translation layer: "Could you work on
fixing those?"

Evidence: [MOTION_MA-AUDIT-FIXES_Opus-5.5_2026-10-22](../docs/verification/MOTION_MA-AUDIT-FIXES_Opus-5.5_2026-10-22.md),
with a table of every finding and what happened to it.

## Changes

**motion-lab avatar layer** (`unity-env/Assets/AvatarLayer/`, copied into SORA with
`scripts/sync-to-sora.ps1`):
- `StandInMotion`: one gait for walking and running. The step rate, the share of the stride a
  foot is down and the flight phase depend on speed. The stance leg uses two-bone IK
  (`LegIk`), with the hips just low enough for the planted foot to reach. Push-off heel lift is
  scaled by speed.
- `PhysicsBody`:
  - collision shapes are fitted to the mesh, and rigid accessories get their own boxes;
  - only the thighs collide with each other;
  - skin friction material;
  - joint limits widened to M0 where anatomical (knee 150°);
  - the balance helper can hold any part at any point;
  - the help log estimates the helper's force;
  - the pelvis hold scales with exempt-joint rigidity.
- `FallController`:
  - "at rest" is measured over 0.1 s;
  - angular damping while settling;
  - after 12 s a fall goes to getting up, and after 22 s she's put back on her feet;
  - "caught herself";
  - no allocations per step;
  - diagnostics for the last part to settle.
- `AvatarFit`: a rest-pose check, an allocation-free `Fold`, and the IK fallback fixed.
- Environment: a run scenario, mesh-based fall checks, fall diagnostics and a trace hook. New
  tests cover stance IK, falls at every help step, the help log, holding by the head and display
  scale. An explicit diagnostic, `DiagnosticsTests.RunTrace`, is not part of the gates.

**SORA** (`clients/unity/Assets/Scripts/Avatar/`):
- `AvatarPhysicsBody`:
  - held where she's grabbed;
  - SORA's drop at real gravity;
  - movement stops when she falls;
  - fallbacks for setup errors and an unknown help setting;
  - up to 8 physics steps a frame;
  - after getting up she settles over both feet before stepping, then steps with the higher foot
    first.
- `AvatarLocomotion` (`Stop`, `TeleportToWorld`), `AvatarGrabController` (`GrabPointWorld`),
  `AvatarSimplePhysicsController` (gravity property), `SoraBootstrap` (wiring and fallback).
- `P18PhysicsBodyTests`: 10 tests through the real grab, drop and landing wiring.
- `ProjectSettings/DynamicsManager.asset`: the TGS solver.

**Docs:**
- `HOW_TO_USE.md`: running, being held where grabbed, real-gravity drops, the fall time limit,
  mesh-fitted shapes, and the help-setting fallback.
- The motion roadmap's MA status.
- motion-lab's `docs/MA.md`.

## Verification

- **motion-lab:** 15 passed / 2 failed of 17. Both failures are Seed-san's fall at full help
  (2.33 s to settle against a 2 s gate) plus the A1 clipping that waits. Walking and running pass
  at realistic strength on all three avatars, with no foot slide.
- **SORA:** 89 of 89 Unity tests pass. The player is rebuilt.
- **Not run:** SORA live, and the full ladder after the last heel-lift change (fitting tests
  rerun: 7 of 7).

## Deferred, with reasons

- Left/right conversion test: nothing produces model-frame poses yet (M1, M8).
- One floor only: needs M7's climbing and jumping skills.
- A1 hair and clothing clipping: owner's decision.

Nothing committed.
