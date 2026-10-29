# Motion MA: audit fixes to the physics body and avatar layer, measured

Model name: **Opus 5.5**. Dates: **2026-10-18 to 2026-10-22**. Code: `~/Desktop/motion-lab/unity-env`
(the source, uncommitted) and its copies in SORA's `clients/unity/Assets/Scripts/AvatarLayer/`,
plus SORA's `AvatarPhysicsBody.cs`. Plan:
[MOTION-CORE-ROADMAP](../plans/MOTION-CORE-ROADMAP_2026-10-11.md), stage MA. Earlier record:
[MOTION_MA-ENVIRONMENT_Opus-5.5_2026-10-17](MOTION_MA-ENVIRONMENT_Opus-5.5_2026-10-17.md).

**Kind of evidence: component and simulation.** Unity PlayMode tests in batch mode on the owner's
PC (Unity 6000.6.0f1, PhysX TGS at 120 Hz). The motion is still the **stand-in** (hand-made poses),
not a trained model. The rebuilt SORA player was **not launched**, and **the owner has not seen
these changes**.

## What the audit found, and what happened to each item

| # | Finding | Now |
|---|---|---|
| 1 | Running was beyond the stand-in gait and untested | **Fixed.** One gait for walking and running (step rate, contact share and flight depend on speed); the stance leg uses two-bone IK so the planted foot stays on the floor; a "run" scenario in the ladder and two run tests in SORA (800 and 1,200 px/s) |
| 2 | Falling mid-walk slid her across the screen | **Fixed.** SORA's movement stops when she falls (`AvatarLocomotion.Stop`) |
| 3 | SORA's tests skipped the real grab, drop and landing wiring | **Fixed.** P18 builds the real wiring (grab controller, SORA's drop, landing event) |
| 4 | The model-to-Unity left/right conversion is unused and untested | **Deferred to M1/M8**: nothing produces canonical poses in the model's frame yet; the conversion formula was checked by hand (a reflection conjugation) |
| 5 | The help log recorded zero balance-helper force | **Fixed.** Estimated from the spring law (Unity reports no force for joints on articulations); test added |
| 6 | Any physics setup error took the avatar down | **Fixed.** Falls back to the posed body; an unknown `SORA_PHYSICS_HELP` falls back to `realistic` with a warning |
| 7 | Fall measurements were of estimated shapes, not the mesh | **Fixed.** Shapes fitted to the mesh (accessories get their own boxes); the fall gate now measures the mesh |
| 8 | Joint limits tighter than M0 | **Widened** to M0's maxima where anatomical; the knee stays at 150° (at 160° a fallen body wedged its foot) |
| 9 | The 12 s cutoff yanked her upright | **Fixed.** At 12 s she goes to getting up; only at 22 s is she put back on her feet |
| 10 | A drop could change her help setting | **Fixed** (held help is never recorded as normal help) |
| 11 | Slow frames and fast flings made her teleport | **Reduced.** Up to 8 physics steps a frame; held at the grab point |
| 12 | Allocations every physics step | **Fixed** in the per-step checks and `Fold` |
| 13 | SORA's drop fell at 71% of real gravity | **Fixed.** 9.81 m/s² at her size |
| 14 | Her body knows one floor only | **Deferred** (climbing and jumping between windows need M7's skills) |
| 15 | Held from her hips | **Fixed.** Held where grabbed (head, arm, foot) |
| 16 to 19 | Garbled comments, a backwards IK fallback, a stale ladder, no T-pose check | **Fixed** (rest-pose check warns) |
| 20 | Two inherited assumptions | Kept, documented |
| A1 | Hair and clothing clipping | **Waits** (owner, 2026-10-17: it doesn't affect training) |

## Other problems found and fixed along the way

- **Falls that never came to rest.** The "at rest" check read one physics step's movement, so a
  toe buzzing a millimetre against the floor kept her "moving". It now averages over 0.1 s. Her
  shapes also got a skin friction material (static 1.0, dynamic 0.9), so a limp hand stops
  instead of creeping.
- **Full help was less stable than realistic help when running.** Exempt joints make her limbs
  almost rigid, and they out-pushed the balance helper's pelvis hold, so a foot touching early
  pitched her whole body. The hold now scales with that rigidity.
- **In SORA she fell straight after getting up from a drop.** When she first counts as up, her
  hips are still moving into place (here 22 cm off her feet, pelvis pitched 14° and rolled 12°),
  and she began stepping on the spot at once, sometimes lifting the one foot she stood on. She
  now settles over both feet for 0.6 s, then steps only if her feet aren't under her, the higher
  foot first. Push-off heel lift is now scaled by speed, so stepping on the spot is flat-footed.

## Results

### motion-lab, the whole suite (2026-10-22 19:25, 17 tests)

**15 passed / 2 failed.** The two failures:
- **`FallsSettleAtEveryHelpStep`:** Seed-san's fall at full help took **2.33 s** to settle (gate
  2 s); her left hand, which carries her robot arm, rolls slowly over the arm's box. The other 11
  falls settled in 0.64 to 1.70 s. More settling damping (2.5) made four falls fail instead of one,
  so it was put back to 1.5. Settling stays sensitive to damping, not monotonically.
- **`PhysicsLadder`:** the same Seed-san fall, plus the A1 clipping rows that wait.

Least help each scenario needs (the last step that passes, removing help in order):

| Scenario | Alice | Seed-san | Odd |
|---|---|---|---|
| stand | 3 realistic strength | 2 no exempt joints | 2 no exempt joints |
| walk | 3 realistic strength | 3 realistic strength | 3 realistic strength |
| run | 3 realistic strength | 3 realistic strength | 1 full help (step 2 tips over; step 3 passes) |
| sit, push, get up | 3 realistic strength | 3 realistic strength | 3 realistic strength |
| fall | 4 no balance helper | fails at step 1 (2.33 s); 2 to 4 pass | 4 no balance helper |

- **Walking and running at realistic strength** (SORA's default): pose error 2.9 to 6.4°, planted
  foot slide 0.0 cm on all three avatars.
- **Body mesh at rest after a fall:** 0 to 6.1 cm into the floor, never hovering (gate 7 cm).
- **Cost:** 0.24 to 0.27 ms of physics a frame (gate 1 ms).
- Every scenario except falling still needs the balance helper: balancing is the motion core's job.
- **After that run**, push-off heel lift was scaled by speed. It changes only speeds below
  0.4 m/s (the first 0.17 s of the run scenario's ramp); the fitting tests (7) were rerun and pass.
  The full ladder was not rerun.

### SORA's Unity suite (2026-10-22 18:38 UTC)

**89 passed / 0 failed / 0 skipped**, including the 10 physics-body tests (P18) through the real
grab, drop and landing wiring. The player was rebuilt ("Build Finished, Result: Success";
`Sora.Embodiment.dll` written 19:38 local). **Not launched.**

## Not run

- SORA live: the owner's review of running, holding and drops.
- The full ladder after the heel-lift change.
- Any trained model (M1 doesn't exist yet), so nothing here says the motion looks natural.
