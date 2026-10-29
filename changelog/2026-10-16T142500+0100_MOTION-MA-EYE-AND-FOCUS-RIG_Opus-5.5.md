# Motion MA: eye and focus rig, by rule rather than a learned model

Model name: **Opus 5.5**. Checkpoint **2026-10-16 14:25:00 +01:00**, Europe/London. Status:
**built and component-tested; not yet seen live**.

The owner asked for eyes to be handled algorithmically, and for fingers to go to the motion core
as a separate hand expert (recorded in the motion roadmap, MA status).

## What she does now

- **Saccades:** quick eye jumps lasting about 21 ms + 2.2 ms per degree (the main sequence), with
  a minimum-jerk profile and peak speed capped at 500°/s.
- **Fixations:** holds of 0.3 to 0.9 s on a target (0.6 to 1.6 s on the viewer), with small
  jumps around it.
- **Smooth pursuit:** a slowly moving target is followed at up to 40°/s without catch-up jumps.
- **Eye-head coordination:** the eyes move first. The head stays still for shifts under 12°,
  and turns fully, then stops, for bigger ones.
- **Gaze held on target while the head or body moves** (the vestibulo-ocular reflex): the gaze
  is kept as a world direction, so the eyes counter-rotate.
- **At rest she looks at the viewer**, with a glance away every few seconds. As she starts to
  speak, she looks down and to the side 60% of the time, as when thinking.
- **Blinking:** a 70 ms close, a 40 ms hold and a 140 ms opening. Intervals have a 0.6 s
  minimum plus random variation, sometimes a double blink, and often a blink with a gaze shift
  over 20°. The upper lids follow the eyes down a little on eye-bone avatars.
- **Any VRM:** the rig reads the avatar's own look-at settings. Bone avatars such as Alice have
  their eye bones turned, using UniVRM's applier formula, after every pose writer (execution
  order 20030), so the eyes aim from this frame's head pose. Expression avatars such as Seed-san
  get their look expressions through UniVRM. A comfortable human eye range (35° sideways, 25°
  up, 30° down) is mapped onto the avatar's authored range, so every avatar uses its full eye
  travel.

## Files (`clients/unity`)

- New: `Assets/Scripts/Avatar/GazeModel.cs` (`GazeModel`, `BlinkModel`; pure logic, seeded).
- New: `Assets/Scripts/Avatar/AvatarEyeRig.cs`.
- `Assets/Scripts/Avatar/AvatarLookAt.cs`: the head now engages only past 12° and settles within
  1.5°. Its comment no longer claims it moves the eyes, which it never did.
- `Assets/Scripts/SoraBootstrap.cs`: adds the rig at load. `SORA_EYE_RIG=0` turns it off (a
  diagnostic switch).
- New: `Assets/Tests/PlayMode/P17EyeRigTests.cs` (10 tests).
- `HOW_TO_USE.md`: her eyes, and both diagnostic switches (`SORA_SECONDARY_COLLIDERS` was not
  listed before).
- `docs/plans/MOTION-CORE-ROADMAP_2026-10-11.md`: MA status, including the finger decision.

## Verification

- Unity PlayMode, at SORA's 60 fps: **79 passed / 0 failed** (69 earlier plus 10 new), on
  2026-10-16 at about 14:20. Measured:
  - with her head swung ±15°, Alice's eye yaw spans 34° and her gaze on the target spans 4°
    (fixational jumps); her eye bones turn up to 5°, within her VRM's 10°;
  - blinks a minute: 18.1 at rest, 23.9 speaking, 14.4 attending (simulated over 10 minutes);
  - Seed-san's look expressions and blink expression are applied.
- An earlier uncapped run also passed, but its frames were so short that fixational jumps
  never happened, so the tests now pin 60 fps.
- The avatar player was rebuilt in place (`scripts/build-embodiment.ps1`; SORA and Unity were not
  running).
- **Not run:** a live look in the real player, and any owner judgement of how natural it looks.
  Restart SORA to load the new player.

Nothing committed.
