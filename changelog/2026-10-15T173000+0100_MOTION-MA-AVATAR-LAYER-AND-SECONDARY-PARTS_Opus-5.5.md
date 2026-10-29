# Motion roadmap gains stage MA (avatar layer); hair, clothing and accessories get their own physics

Model name: **Opus 5.5**. Checkpoint **2026-10-15 17:30:00 +01:00**, Europe/London. Status:
**roadmap updated; MA part A1 implemented in SORA's avatar player; A2 to A4 not started**.

The owner asked for:
- a translation layer so any VRM can be swapped in;
- a physics model before training, where falls ragdoll onto the real ground but are "more
  sophisticated than just a ragdoll";
- the model "singularly subject to the physics constraints", with helper forces only where
  needed;
- hair, clothing and bones that behave differently.

Then: "Yes, then start on implementing physics v2 (this)."

## Changes

**Roadmap** ([MOTION-CORE-ROADMAP_2026-10-11](../docs/plans/MOTION-CORE-ROADMAP_2026-10-11.md)):
- **New stage MA (avatar layer),** alongside M1, in four parts:
  - **A1:** moving parts (hair, clothing and accessories);
  - **A2:** fitting and proportions;
  - **A3:** the physics body, with a help dial that defaults to zero;
  - **A4:** falls (trigger, reaction, impact and settling, getting up).

  It also defines the physics ladder (the least help each scenario needs), optional
  physics-in-training, and a gate.
- **Rule 7:** falling is physical, not a preset animation; being dragged stays deterministic.
- **Knock-on edits:**
  - M1 adds fall and get-up intents, pose perturbations and the ladder;
  - M2 shrinks (physics handles contact and joint limits);
  - M7's getting-up starts from where the body came to rest;
  - M8 drives MA's body;
  - the M8 prerequisite's test no longer lists "wave".
- **Records:** §5 has a new row, and §6 has decision 10 (the help dial).

**SORA's avatar player** (`clients/unity`):
- **New `Avatar/AvatarSecondaryParts.cs`:**
  - **Classifying chains:** each spring chain is sorted as hair, clothing or an accessory, with
    a finer kind: ponytail, skirt, coat, tie, sleeve, ear, tail, prop, ornament or soft. The
    clues are names (VRoid, MMD, romanised and written Japanese) and the humanoid bone the chain
    hangs from.
  - **The override file:** `<avatar>.vrm.parts.txt`.
  - **Physics per kind:**
    - hair: stiffness ≥ 1.5, gravity ≥ 0.25;
    - clothing: gravity ≥ 0.35, drag ≥ 0.6;
    - ears stiff; the tail stiffer; props heavy.
  - **Generated body colliders:** capsules sized from the avatar's bones, added only to chains
    the author gave none. A chain gets no collider group that its own root sits inside (a tail
    that starts inside the torso would otherwise be shoved).
- **`AvatarSecondaryMotionTuner.cs`:** settings are written onto the joints, then the spring
  simulation is rebuilt once. Pushing settings into the running buffers and then rebuilding
  loses them; found with a test.
- **`SoraBootstrap.cs`:** passes the override path beside the configured avatar.
- **Tests:** new `Tests/PlayMode/P16SecondaryPartsTests.cs` (5 tests): names, overrides,
  physics per kind, Seed-san, and Alice (skipped when her file is absent).

**Docs:**
- [HOW_TO_USE.md](../HOW_TO_USE.md): the moving-parts paragraph and the override file.

## Verification

- **Unity, native:**
  - PlayMode 68 passed / 0 failed (63 before, plus 5 new);
  - the Windows player was rebuilt in place.
- **Live, isolated profile** (`.local\physics-v2-qa-2026-10-15`, Alice, with SORA's own player):
  - **Every chain classified:** 70 hair, 39 skirt, 3 tie, 10 ear, 2 tail, 14 prop, 2 ornament
    and 6 soft; all 310 joints tuned.
  - **Sit and walk work.** The removed "waving" state is rejected.
  - **While she walks,** her ponytail hangs at about 45° instead of streaming out flat. Before
    and after screenshots are in `shots-run1\` and `shots\`.
- **Found while checking:**
  - **What the streaming thing was:** her rig's `Skn_Tail` chain is a real, short tail at hip
    height. The streaming part was her ponytail (hair).
  - **"Never connected" was my test harness, not SORA:** my background jobs can't reach
    localhost. SORA's startup is normal.
- **Not run:**
  - the clothing gravity of 0.35 (raised after the live check, to keep clothing heavier than
    hair). It is covered by the tests but not seen live;
  - the clipping checks over the 60 s scenarios;
  - the oddly proportioned test avatar;
  - your own SORA, which picks the change up the next time it starts.

## Limits and next

- **Physics values are first settings,** tuned on Alice. Seed-san loads and simulates, but
  wasn't judged visually.
- **Next in MA:** A3, Alice's physics body (articulation bodies with motors and the help dial),
  prototyped in motion-lab's `unity-spike/`, with a fall onto a taskbar-like surface as the first
  scenario.

HOW_TO_USE.md: updated.
