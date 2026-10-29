# Motion MA: her physics body in SORA's avatar player

Model name: **Opus 5.5**. Checkpoint **2026-10-17 14:10:00 +01:00**, Europe/London. Status:
**built, tested, and running in the owner's profile for their review**.

The owner: "Could you build the current physics model into sora? Then relaunch her so I can review
it." This brings stage MA's physics body into SORA ahead of M8.

## Changes

**SORA (`clients/unity`):**
- New, `Assets/Scripts/AvatarLayer/`: copies of motion-lab's avatar layer, which stays the source
  of truth. To update, run motion-lab's `scripts/sync-to-sora.ps1`; a test fails on drift.
- New, `Assets/Scripts/Avatar/AvatarPhysicsBody.cs`:
  - the physics body runs at her real size, in its own physics scene at 120 Hz;
  - SORA's animation is put back before its pose writers run, then read as motor targets, and
    the result is written to her bones (before the eye rig);
  - her movement and turning on screen move and turn the body;
  - a hard landing (1,000 px/s, as before) is a physical fall, replacing the preset ragdoll;
  - help comes from `SORA_PHYSICS_HELP` (default `realistic`); `SORA_PHYSICS_BODY=0` turns it all
    off.
- `Assets/Scripts/SoraBootstrap.cs`: wiring. Grabbing and drop physics wait while she is falling.
- `ProjectSettings/DynamicsManager.asset`: the TGS solver with 12 and 4 iterations, needed for
  stable articulations. Nothing else in SORA uses rigid-body physics.
- New, `Assets/Tests/PlayMode/P18PhysicsBodyTests.cs`:
  - the copies match motion-lab's;
  - her body follows her animation;
  - the display matches the simulation;
  - a hard landing is a fall, and she gets up.

**motion-lab:**
- `PhysicsBody` can simulate away from where the avatar is displayed (`origin`, `RootOffset`,
  `SimPoint`), and takes out a display turn when writing back.
- New: `scripts/sync-to-sora.ps1`.
- The environment's tests still pass: 8 of 8 outside the ladder, after the change.

**Docs:**
- `HOW_TO_USE.md`: her physical body, and both new switches.
- The roadmap's MA status.

## Verification

- SORA Unity PlayMode: **82 passed / 0 failed**. Measured on Seed-san at SORA's scale:
  - pose error 0.5°;
  - hips within 3 cm of rest;
  - after a hard landing her head went down to 0.10 units, and she stood up again after 6.4 s.
- The avatar player was rebuilt (`Sora.Embodiment.dll` at 14:04).
- **Relaunch:**
  - SORA's owned Quit can't be sent from outside (the forwarded quit was refused), and Core's
    shutdown needs the app's secret;
  - so, at the owner's request to relaunch, SORA's own processes were stopped directly (app,
    Core, avatar, both llama.cpp servers), then SORA was started as the Desktop shortcut does;
  - Core runs, and the avatar log shows "Physics body: 21 links, 44.4 kg, 1.45 m";
  - a screenshot shows her standing on the taskbar.
- **Not checked:** walking, dragging, a live drop and fall, and any owner judgement.

Nothing committed.
