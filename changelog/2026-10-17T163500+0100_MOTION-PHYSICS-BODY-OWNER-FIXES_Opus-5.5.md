# Physics body in SORA: fixes from the owner's review

Model name: **Opus 5.5**. Checkpoint **2026-10-17 16:35:00 +01:00**, Europe/London. Status:
**fixed, tested and relaunched for the owner's review**.

The owner reported:
- after getting up she slanted to one side and fell again, over and over;
- walking dragged her feet, and she fell when she stopped;
- picked up she ragdolled (wanted), but dropped she froze mid-air, got up floating, then fell
  through the floor and flew around the screen.

## Causes

The helper forces were not the root cause. SORA (screen position) and the physics body
(metres) both tried to own her position, and the floor followed her screen position:
- dragging lifted the floor with her, her feet lost contact, a fall began, and a fall switched
  off SORA's drop: she froze mid-air while her body fell onto a floor left behind;
- the floor then jumped back through her body, and the balance helper hauled her towards a
  target metres away;
- after a fall she stood with her feet behind her **in depth** (into the screen), while the
  helper held her hips at SORA's fixed depth, so she leaned forward about 17° and fell again;
- getting up, she was straightened to face away from the viewer and then twisted back;
- SORA's walk animation only swung her legs; it never lifted her feet.

Along the way: Unity reports zero force for a joint attached to an articulation, so "no balance
force" in the logs was misleading. A new environment test shows the helper does pull, in a
scene of its own too.

## Changes

**`clients/unity/Assets/Scripts/Avatar/AvatarPhysicsBody.cs`:**
- **Three modes, one owner of her position at a time:**
  - standing: SORA places her on screen and her body follows;
  - held (dragged, or carried by SORA's drop): she hangs at 30% muscle tone from the hold, with
    no floor and no falls;
  - falling: her body has itself, and when she is up again SORA's position moves to her.
- **The simulation uses a fixed frame** (world divided by her scale). SORA owns x and y; her body
  owns depth (z), which isn't visible on screen.
- **The floor** goes under her only when she is on a surface. It never moves through her.
- **Walking** uses the stand-in gait for her legs: feet lifted, stride matched to her speed.
  After stopping or getting up, she steps on the spot (up to three cycles) until her feet are
  under her. The foot in the air is placed by gravity, not by her tipped pelvis.
- **After getting up or stepping**, SORA's position moves between her feet, so her hips settle
  over them.
- **The balance helper never asks for a hip height her planted feet can't reach.** It is capped,
  at most 25 cm lower.
- **Resync:** if SORA and her body disagree by more than 0.5 m sideways (or 0.9 m in height),
  her body is moved, not dragged. None happened in the tests.
- **Falls use the way she faces** on screen.
- `SoraBootstrap.cs` tells it when she is held (grabbed, or in SORA's drop).
- `AvatarLocomotion.TeleportToWorld` (new).

**motion-lab's avatar layer** (synced to SORA):
- `FallController.Suspended` and `Facing`;
- `PhysicsBody.BalanceVerticalShare` (default 1, unchanged behaviour), `BalanceAnchor` and
  `BalanceJoint`;
- `StandInMotion.WalkPeriod`;
- a new environment test, `TheBalanceHelperPullsPositionAndRotation`.

**`HOW_TO_USE.md`:** walking, being picked up and falling.

## Verification

- SORA Unity PlayMode: **84 passed / 0 failed**. The four P18 tests reproduce the owner's three
  reports:
  - after a fall she gets up after 6.9 s and 5 s later stands at a 2° lean, facing within 1°;
  - after a walk she ends at a 5° lean, with her feet under her;
  - picked up and dropped, she lies on the floor (hips 6 cm above it), comes no further than
    0.74 m from where she landed, and needs no resyncs.
- The environment's balance helper test passes: 0.300 of 0.3 m and 29.9 of 30°, in both the
  default scene and a separate one.
- Rebuilt (16:25) and relaunched in the owner's profile; a screenshot shows her standing.
- **Not run live:** walking, dragging and dropping in the real player. The owner is reviewing.
- **SORA was stopped by ending its processes** (app, Core, avatar, both llama.cpp servers): its
  tray Quit can't be triggered from outside.

Nothing committed.
