# Motion MA: the avatar layer and training environment, measured

Model name: **Opus 5.5**. Date: **2026-10-17**. Code: `~/Desktop/motion-lab/unity-env`
(uncommitted), described in `~/Desktop/motion-lab/docs/MA.md`. Plan:
[MOTION-CORE-ROADMAP](../plans/MOTION-CORE-ROADMAP_2026-10-11.md), stage MA.

**Kind of evidence: component and simulation.** Unity PlayMode tests in batch mode on the owner's
PC (Unity 6000.6.0f1, PhysX with the TGS solver at 120 Hz). The motion is the **stand-in**
(hand-made poses), not a trained model. Nothing ran in SORA's player, and **the owner has not
seen any of it** (the "falls look realistic" gate is theirs).

## Result: 8 of 9 tests pass

The ninth, the physics ladder, fails **only** on hair and clothing clipping (A1, below). Every
motion scenario passes at full help.

### A2, fitting

| Avatar | Leg | Root scale | Hips travel for 1 canonical m | Worst planted-foot drift |
|---|---|---|---|---|
| Alice | 0.756 m | 1.000 | 0.996 m | 3.2 mm |
| Seed-san | 0.731 m | 0.966 | 0.962 m | 4.8 mm |
| Odd (long legs, short arms) | 0.950 m | 1.255 | 1.250 m | 6.2 mm |

- The C# avatar map agrees with Python's `adapter.py` on all 21 shared cases (7 sets of missing
  joints × 3 random poses).
- The canonical tables match `canonical_skeleton.json`.

### A3, the physics body

- **Drive units, measured:** Unity's articulation drive stiffness is per radian. A 9.81 N·m
  load sagged 4.41°; per radian predicts 5.62° (joint friction takes the rest), per degree 0.10°.
- **Drive accuracy:** without gravity, every joint reaches its target in all five test poses
  (stand, sit, kneel, fall forward, fall right) to 0.0°.
- **Steadiness:** standing with full help, the worst joint is 0.6° off its target on every
  avatar, and no link wobbles measurably (0.000° per 0.1 s).
- **Cost:** 0.25 to 0.28 ms of physics per 60 Hz frame (two 120 Hz steps); the gate is 1 ms.

### A4, falling (a window closes under her, half her height above the taskbar)

Every fall at every help step passed. Help is off during a fall, so the steps differ only in how
she stood beforehand.

| Avatar | Settled after impact | Gap to the taskbar | Into the taskbar |
|---|---|---|---|
| Alice | 0.75 to 1.22 s | 0.0 cm | 0.001 cm |
| Seed-san | 1.39 to 1.69 s | 0.0 cm | 0.001 to 0.002 cm |
| Odd | 1.72 to 1.76 s | 0.0 cm | 0.001 to 0.003 cm |

Gate: at most 2 s, 1 cm and 1 cm. Settling is sensitive to passive damping, and not
monotonically: with damping at the level of 45%, 60%, 75% and 100% muscle tone, Alice took 1.23,
0.99, 1.40 and 4.45 s, and Odd 1.72, 2.10, 2.44 and (not measured). With no damping floor, an
earlier, slightly different measurement gave Alice 2.84 s. The setting is 45%, the only one
tried where all three passed. The margin is about 0.25 s on Odd.

### The physics ladder: least help each scenario needs

| Scenario | Alice | Seed-san | Odd |
|---|---|---|---|
| stand | 3 realistic motor strength | 3 | 3 |
| walk (60 s at 0.5 m/s) | 3 | 3 | 3 |
| sit | 3 | 3 | 3 |
| push (5 shoves of 0.5 m/s) | 3 | 3 | 3 |
| fall | 4 no help at all | 4 | 4 |
| get up (stand-in) | 3 | 3 | 3 |

- Without the balance helper, the stand-in poses tip over: they hold a pose but don't balance a
  body. That is expected, and it is what the motion core has to learn (roadmap: a model trained
  only on motion capture isn't expected to pass step 4 either).
- The worst foot slide in stand, walk, sit and push at steps 1 to 3 was 1.4 cm.

### A1, hair and clothing clipping (at full help): over the 1 cm allowance

Measured against the body colliders each chain collides with (SORA's generated ones):

| Scenario | Alice | Seed-san | Odd |
|---|---|---|---|
| stand | 0.2 cm | none | none |
| walk | **1.5 cm**, skirt into right hip | none | none |
| sit | **4.6 cm**, skirt into right hip | none | none |
| push | 0.8 cm | none | none |
| fall | **8.9 cm**, weapon prop into hips | **2.7 cm**, hair into hips | **1.2 cm**, hair into chest |
| get up | **8.7 cm**, weapon prop into hips | none | none |

These are findings about SORA's hair and clothing code (`AvatarSecondaryParts.cs`, A1), which the
environment copies unchanged. The likely causes:
- spring bones collide only with body capsules, never with the floor, so props and hair are
  pulled through the body when she lies down;
- the skirt is pressed into the thigh capsules when sitting.

Not fixed here: SORA's code is the source of truth.

## Bugs found and fixed while building

- The drive units were per radian, not per degree, so motors were about 57 times too weak.
- A balance helper using explicit forces on the light hips link produced NaN forces; it is now a
  PhysX-solved joint to an invisible anchor.
- Self-collision of arms against the torso and thighs against the trunk shoved links apart at up
  to 18,000°/s in ordinary poses; now only the legs collide with each other.
- A light collarbone carrying a 2 kg arm made the articulation unstable; light links get a
  minimum rotational inertia.
- Non-root links' reported velocities carried a steady 5.5 cm/s offset at rest, so settling is
  judged from how far links actually move.
- The odd avatar's thighs (thickness scaled by height) touched each other at rest; limb thickness
  now also follows her width.
- The stand-in get-up handed back control before both feet were down; it now waits for them.

## Not run or not done

- The owner's judgement of falls (needs a way to watch them; nothing visual exists yet).
- Integration into SORA's player (stage M8).
- Fingers (a separate hand expert, owner decision 2026-10-16).
- The A1 fixes above.
