# SORA motion core: rationalised roadmap

Prepared **2026-10-11** by **Opus 5.5**. It builds on a draft by Grok Bot, kept unchanged at
[archive/MOTION-CORE-ROADMAP_2026-10-11_GROK-ORIGINAL.md](archive/MOTION-CORE-ROADMAP_2026-10-11_GROK-ORIGINAL.md).
It replaces the [28 September roadmap](archive/MOTION-CORE-ROADMAP_2026-09-28.md).

The owner asked: "Recent developments take precedence over older decisions. Could you
rationalise the roadmap and define each stage for me?"

**Status: current plan. M0 is complete (2026-10-16). MA (the avatar layer and training
environment, added 2026-10-15) is built and measured; the audit's fixes are in (2026-10-22). Its
gate is open on hair and clothing clipping, one slow fall (Seed-san at full help) and the owner's
judgement of falls** (see below). Stage IDs M0 to M8 are kept, so
nothing is renumbered, but several stages have new content (§5). Defaults marked "default" are
this plan's choice; the owner can change any of them (§6). Thresholds marked "proposed" are
confirmed in each stage's task plan.

## 1. Precedence

Where sources disagree, the newer one wins.

| Rank | Source | Date |
|---|---|---|
| 1 | The owner's decision: they will not build or train the motion core themselves, and they don't want to wait until after A Levels. Agents build and train it. The owner supplies dataset sign-ups and licences, training-hardware time and naturalness judgements | 2026-10-11 |
| 2 | [VISION.md](../../VISION.md) and the owner's ChatGPT "Embodied Semantic Observer" brief | 2026-10-05, 2026-10-09 |
| 3 | [Motion interface design](MOTION_INTERFACE_DESIGN_2026-10-05.md) (`MotionSignal`) | 2026-10-05 |
| 4 | The 28 September roadmap (DeepSeek Flash, never signed off), and the `~/Desktop/motion-lab` README and stage briefs written the same day | 2026-09-28 |

VISION.md is updated to record the rank 1 decision (who builds it, and when). Its description of
the model (encoders feeding a GRU that outputs joint rotations, possibly with skill experts) is
unchanged and is what this plan builds.

## 2. Rules for every stage

**Architecture**

1. Language models never drive joints. Core publishes semantic state, and the motion core turns
   it into movement.
2. The motion core's only input from SORA is **`MotionSignal`**: `intent`, `intent_target`,
   `conversation`, `emotion`, `attention`, `audio` and `context`. A new field needs a contract
   version bump agreed with the owner. The 28 September draft `CognitiveMotionState` is retired.
   `CanonicalState`, `CanonicalPose` and the avatar adapter stay internal to motion-lab until M8.
3. Output, outside Core: **joint rotations** for the avatar. Only `EmbodimentFeedbackEvent`
   comes back into Core. The learned core replaces the deterministic layer wholesale, with no
   changes upstream.
4. **Skeleton:** the canonical skeleton is the **full VRM humanoid body, 22 joints** (no
   fingers or eyes in v1). It matches AMASS's and LAFAN1's three-joint spine, so datasets map one
   to one and nothing is merged in training. An avatar without some optional joints (Alice and
   Seed-san have no `upperChest`) is handled at the output by the avatar adapter (owner,
   2026-10-11). Her proportions are those of **Alice**, SORA's default avatar from 2026-10-11.
   - Rotations are relative to the rest pose, in the parent joint's local frame. These
     conventions are written once in the M0 spec, with tests.
   - Never Euler angles.
5. Any velocity fed back as input is computed from the **realised pose (after constraints)**,
   never from the model's own raw output.
6. The network is a pure function `f(state, h) → (output, h')` and exports cleanly to ONNX from
   day one.
7. **What stays deterministic:**
   - the root position: on the screen plane, owned by SORA's existing coordinate system;
   - being dragged.

   **Falling is physical, not a preset animation** (owner, 2026-10-15; this replaces "falling
   and ragdoll stay deterministic"). The motion core's targets drive a physics body (MA), and
   help forces are a dial that defaults to zero. Getting up is a learned skill, starting from
   wherever the body came to rest.
8. **Model size is set by measurement,** by the sizing sweep in M1 (owner decision,
   2026-10-11): the smallest model that performs as well as the best one tried, within the
   runtime budget. It grows later only when evaluation shows a deficiency that more capacity
   could plausibly fix.
9. **SORA lives on a desktop, not in a room.** She stands on taskbars and window tops, sits on
   window edges and climbs onto windows, at screen scale, with her root on a plane. Motion
   capture is people in 3D rooms. Every stage maps the data onto this setting, and §4 says where
   the data has gaps.

**Process**

10. Research lives in `~/Desktop/motion-lab` (Python). SORA receives the model at M8; the
    `MotionSignal` contract and trace logging come earlier (M8 prerequisite, §4).
11. Every stage after M1 is compared against the **M1 control** (the model with neutral inputs)
    and must pass the 60-second stability battery.
12. Gates are measurable thresholds with recorded evidence in
    `docs/verification/MOTION_<stage>_<model>_<date>.md`, labelled by kind (fixture, component,
    native, live model, hardware), as AGENTS.md requires. A gate isn't ticked until it passes.
13. **Agents build, train, evaluate and write up; the owner does what agents can't:**
    - **licences:** agents can't accept a licence or create an account;
    - **GPU time:** training uses the owner's RX 9070 XT, with the ROCm PyTorch environment at
      `.local\decision\train-env` (PyTorch 2.12.0 with ROCm 7.14; GPU visible, checked
      2026-10-11), and only while SORA is idle or closed;
    - **the owner's running SORA** is left alone.
14. AGENTS.md applies: never delete files, write a changelog under your own model name, and don't
    commit, push or merge unless the owner asks.

## 3. Who does what

| Owner | Agents |
|---|---|
| Registers for AMASS (which BABEL uses) and accepts its licence; accepts LAFAN1's licence; picks the speech-and-gesture corpus | Code, data pipelines, training, evaluation, tooling, reports, document updates |
| Gives GPU time while SORA is idle, and Unity time for the runtime spike and M8 | Schedules runs around that time and reports evidence |
| Judges naturalness: M1 idle motion, the M8 A/B test, and optional spot checks in between | Supplies everything else as measured metrics |
| Changes any default in §6 | Proposes defaults and raises conflicts rather than assuming |

## 4. Stages

| Stage | Size | Depends on | Owner input |
|---|---|---|---|
| M0 Foundations and specs | Small | Nothing | None |
| MA Avatar layer: fitting, physics, moving parts (added 2026-10-15) | Medium | M0; M1 for learned falls | Fall judgement |
| M1 Data, motion prior and intent | Large; critical path | M0; AMASS (with BABEL) and LAFAN1 licences | Licences, GPU time, idle judgement |
| M2 Constraint layer | Medium | M1 | GPU time |
| M3 Speech and gesture | Medium | M1, M2; corpus licence | Corpus choice |
| M4 Attention and desktop context | Medium | M1, M2 | GPU time |
| M5 Emotion, and the desktop data factory | Medium to large | M1, M3's corpus | Optional label review |
| M6 SORA's own intents and conversation states | Medium | M1, M4, M5 | GPU time |
| M7 Skill experts (optional) | Medium | M1 to M6 | GPU time |
| M8 SORA integration | Medium | Accepted model; runtime spike; M8 prerequisite | Unity time, A/B acceptance |
| M8 prerequisite: `MotionSignal` and trace logging in SORA | Small | V1 closed | Go-ahead |

The sources give relative sizes only; no durations are promised.

### M0: Foundations and specs (small)

**Status (2026-10-12, Opus 5.5):** built in `~/Desktop/motion-lab` (spec `docs/M0.md`). Every
numeric gate passed, and passed again on Alice's skeleton
([evidence](../verification/MOTION_M0_Opus-5.5_2026-10-11.md)); 35 tests pass, including the
avatar adapter.
- **The runtime spike is done** ([evidence](../verification/MOTION_M0-RUNTIME-SPIKE_Opus-5.5_2026-10-12.md)):
  - **Sentis on the CPU** runs the model.
  - **Sentis has no `GRU` operator,** so the export writes the GRU as its cell equations.
  - **Every size of the M1 sweep fits the budget.** The budget is a tenth of a 60 Hz frame per
    tick (1.67 ms at p99). Driving Alice, the slowest size, 512 × 2, takes p99 1.13 ms.
- **The skeleton table review is done** (2026-10-16): Gemini 4 Argon (medium) reviewed it
  line by line and passed it ([review](../verification/MOTION_M0-SKELETON-REVIEW_Gemini-4-Argon_2026-10-16.md)).
  Opus 5.5 re-checked its main claims (joint order, bone lengths, symmetry to 0.028 mm, the
  0.436 upper-chest ratio, toes on the ground), and the 35 tests pass. **M0's gate has passed.**

- **Purpose:** the maths, skeleton and data formats every later stage uses. Nothing is trained.
- **Builds:**
  - a rotation library: 6D↔R conversion, SO(3) Exp/Log, integration
    `R' = R·Exp(Δt·[ω]×)`, and finite-difference ω (needed for feedback inputs and evaluation,
    whichever output head wins);
  - the canonical skeleton table (joints, parents, rest offsets, joint limits) as the single
    definition every module imports, checked line by line by a second agent;
  - tensor and windowing formats (radians, metres, a 60 Hz tick; LAFAN1's 30 fps is resampled);
  - `MotionSignal` frozen as motion-lab's input schema, once decision 8 (audio fields) is made;
  - an ONNX export-and-reload test in Python.
- **Runtime spike (early, but it doesn't gate M0):** a tiny GRU exported to ONNX and run in a
  scratch Unity 6.6 project at 60 Hz on her VRM, with per-tick latency measured. It chooses
  between Sentis, an ONNX Runtime plugin and a hand-written C# GRU, and sets the runtime budget
  for decision 4. It never touches the owner's SORA install.
- **Gate:**
  - tests green (proposed: 6D round trip < 1e-5; orthonormality error < 1e-4 after 100,000
    integration steps in float32; FK matching a hand-computed fixture; mirror symmetry);
  - the skeleton table reviewed;
  - ONNX output matching PyTorch (proposed: < 1e-5 maximum absolute difference).

### MA: Avatar layer: fitting, physics and moving parts (medium; alongside M1)

**Added 2026-10-15 at the owner's request.** "There should be a translation layer that handles
the differences between the uniform training model and the actual model so that the user can
swap between vrm models." Then: "a better physics model before training", where falling should
"ragdoll onto the ground rather than using a preset animation that leaves a large gap", but be
"slightly more sophisticated than just a ragdoll". And: "Ideally I'd like for the model to be
singularly subject to the physics constraints", with helper forces only where needed.
Hair, clothing and bones "should behave differently".

**Status (2026-10-22, Opus 5.5):**
- **Audit fixes (2026-10-22,
  [evidence](../verification/MOTION_MA-AUDIT-FIXES_Opus-5.5_2026-10-22.md)):** running, collision
  shapes fitted to the mesh, held where grabbed, real-gravity drops, falls that always end, and
  tests through SORA's real grab and drop wiring.
  - motion-lab: 15 of 17 tests pass. Walking and running pass at realistic strength on all three
    avatars, with no foot slide.
  - SORA: 89 of 89 Unity tests pass, and the player is rebuilt. Not yet seen by the owner.
  - Still open: Seed-san's fall at full help takes 2.33 s to settle (gate 2 s); Odd's run fails
    at ladder step 2 only.
  - Deferred: the left/right conversion test (M1, M8) and more than one floor (M7).
- The 2026-10-17 measurements below are superseded where the record above differs.
- **The training environment exists** (owner, 2026-10-17: "the ideal training environment will
  exist before training begins"). It is `~/Desktop/motion-lab/unity-env`, its own Unity project,
  described in motion-lab's `docs/MA.md`. Measured
  ([evidence](../verification/MOTION_MA-ENVIRONMENT_Opus-5.5_2026-10-17.md)), with stand-in
  motion, on Alice, Seed-san and an oddly proportioned avatar:
  - **A2, fitting:** the C# twin agrees with `adapter.py` on 21 shared cases; hips travel
    scales with leg length; planted feet drift at most 6.2 mm.
  - **A3, the physics body:**
    - every test pose is reached exactly;
    - standing is steady (0.6° worst, no wobble);
    - physics costs 0.25 to 0.28 ms a frame (gate 1 ms);
    - help is a logged dial.
  - **A4, falling:** every fall settles in 0.75 to 1.76 s, resting on the taskbar with no gap
    and at most 0.003 cm inside it.
  - **The ladder:** stand, walk, sit, push and the stand-in get-up need the balance helper but
    pass with realistic motor strength; falls need no help.
  - **Still open:**
    - A1 clipping in four of the 18 checks: Alice's skirt (sitting 4.6 cm, walking 1.5 cm),
      her props when lying (8.9 cm), and hair when lying on Seed-san (2.7 cm) and Odd
      (1.2 cm). Likely fix in SORA's code: spring bones collide with the floor too;
    - the owner's judgement of falls (nothing visual yet);
    - fingers (a hand expert).
- **The physics body is in SORA's player** (owner's request, 2026-10-17, ahead of M8).
  `AvatarPhysicsBody.cs` uses the avatar layer (copied from motion-lab, which stays the source;
  a test catches drift). SORA's animation is the motor target; help is "realistic"; a hard
  landing is a physical fall in place of the preset ragdoll. `SORA_PHYSICS_BODY=0` turns it off.
  Component-tested (82 Unity tests) and seen standing in the owner's profile; not yet judged.
- **A1 is in SORA's avatar player.** The code is `AvatarSecondaryParts.cs`, and the Unity
  tests (68) pass.
  - Every one of Alice's chains is classified: hair, ears, ties, a skirt ring, soft tissue, a
    tail and weapon props.
  - Colliders are generated from her body, and each kind gets its own physics.
  - Live check: while she walks, her ponytail now hangs at about 45° rather than streaming out
    flat.
- **Eyes are in SORA's avatar player (2026-10-16, Opus 5.5).** The owner chose rules over a
  learned model for the eyes: saccades on the main sequence, fixations, pursuit, eye-head
  coordination, gaze held on target while the head moves, and blinking at measured rates. The
  code is `GazeModel.cs` and `AvatarEyeRig.cs`, using each VRM's own eye settings.
- **Fingers go to the motion core** (owner, 2026-10-16): a separate hand expert, possibly a
  mixture-of-experts member, outputs the finger joints from the arm, intent and speech. The
  22-joint body skeleton stays as M0 fixed it. Hand-capture data (for example GRAB, BEAT)
  needs its own licences.

- **Purpose:** everything between the motion core's canonical pose and a particular VRM avatar.
  The model never sees the avatar; this layer makes any VRM work, physically. It needs no
  licences, so it runs alongside M1.
- **Where it is built:** in Unity, because that is what ships: motion-lab's `unity-env/`
  (2026-10-17), which reaches SORA's player at M8. Part A1 doesn't depend on the motion core, so it goes into SORA's current
  avatar player straight away. The Python reference (`adapter.py`) stays the source of truth
  for fitting, with shared test cases for the C# twin.
- **A1. Moving parts: body, hair, clothing and accessories.**
  - VRM separates **body bones** (its humanoid map) from **spring bones** (everything that
    moves on its own).
  - Each spring chain is then classified as **hair**, **clothing** (skirt, coat, tie) or an
    **accessory** (tail, ears, ornaments, soft tissue). The clues are where it hangs from (head,
    hips or chest), name patterns across the VRoid, MMD and Japanese conventions, and its shape.
  - A **per-avatar override file** corrects anything misclassified.
  - **Each category has its own physics:**
    - hair is light, with real gravity and air drag;
    - clothing is heavier and more damped, and collides with hips and legs;
    - accessories are tuned per type.
  - **Colliders are generated from the body.** Many models, Alice among them, ship with none
    (and with zero spring gravity, which is why her ponytail streamed out sideways).
  - **Coupling is one way:** the body moves hair and clothing, never the reverse.
- **A2. Fitting (retargeting).**
  - the avatar map (missing joints, done in M0);
  - proportions: root motion scaled by leg length so feet don't slide; contact heights and
    reach from the avatar's own bones;
  - a C# twin that passes the Python cases.
- **A3. The physics body.**
  - Each body segment is a capsule with mass (standard body-segment proportions), built from the
    avatar's bones, with joint limits from the skeleton table. Unity articulation bodies are used.
  - Joint motors (PD drives) pull towards the target pose, with **strength scheduled per
    joint**.
  - Desktop surfaces (taskbar, window tops, screen edges) are colliders.
  - **Help is a dial, defaulting to zero** (owner, 2026-10-15). Everything non-physical is a
    setting from 0 to 1 and logged when used: a balance helper at the hips, motor strength
    above realistic muscle limits, and joints exempted from physics.
  - The physics layer is swappable without touching the model.
- **A4. Falling.**
  1. **Trigger:** losing support, a push, or being dropped. The direction comes from momentum.
  2. **Reaction:** about 0.2 to 0.5 s, with the motors partly on. The motion core's `fall`
     intent drives a catch step, arms out, head tucked, and a turn towards the side. Stand-in
     reaction poses are used until M1 learns them.
  3. **Impact and settling:** muscle tone drops to about 10 to 20 %, with the neck stiffer.
     She comes to rest in real contact.
  4. **Getting up:** from the pose she actually ended in.

  Being dragged stays deterministic.
- **The physics ladder** is the test every trained model runs, starting at M1. Fixed 60 s
  scenarios (stand, walk, sit, push, fall, get up) are run while help is removed step by step:
  1. full help;
  2. no exempt joints;
  3. realistic motor strength;
  4. no balance helper.

  The result is **the least help each scenario needs**, recorded per model, so physical
  progress can be compared between models.
- **Physics in training (optional, later):** a model trained only on motion capture is not
  expected to balance itself at step 4. If the ladder shows help can't otherwise be reduced, the
  trained model is fine-tuned inside a simulator, rewarded for staying close to its own motion
  while staying upright (DeepMimic-style). It is started only on that evidence and judged by the
  same ladder.
- **Gate:**
  - **moving parts:** every spring chain of Alice and Seed-san is classified, and the test
    avatars' overrides are honoured. Hair and skirts don't pass through the body in the 60 s
    scenarios;
  - **falling:** after settling, the gap to the surface is at most 1 cm and penetration at most
    1 cm, with settling within 2 s;
  - **steadiness:** no jitter at rest. With full help, the pose stays within a few degrees of
    the target (threshold set in the task plan);
  - **swapping:** the same results on Alice, Seed-san and an oddly proportioned test avatar,
    and foot slide within the M1 threshold;
  - **cost:** physics at 120 Hz costs at most 1 ms per frame;
  - **owner judgement:** the owner judges falls realistic, in a dated note.
- **Risks:**
  - tuning physics at desktop scale (screen units, not metres);
  - how it interacts with SORA's existing drag and ragdoll code;
  - whether the reaction phase reads as a person rather than a puppet. That depends on M1
    learning falls well.

### M1: Data, motion prior and intent (large; critical path)

**Status (2026-10-26, Opus 5.5): v1, v2 and v3 trained and evaluated.** v3 fixed the drift
into impossible limb poses (outside the data's limits: 21% → 3.6%), but it's even calmer than
v2, and its hips float in 2 of 16 test seeds. **v4 (2026-10-26)** added keywords (a MotionSignal
v2 draft in motion-lab's `specs/`, labels from LAFAN1, 100STYLE and BABEL) and the hips height
above what she stands on.
- **Fixed:** the hips no longer float; limits 2.1%; the lowest error yet.
- **Weak:** the keywords steer only a little (walking at 0.20 m/s against the data's 0.56), and
  the motion still winds down.
- **Proposed next:** probabilistic output (a Motion-VAE-style sampled latent).

**v5 (2026-10-30, Opus 5.5, in motion-lab's `versions/v5/`).** A stress battery
(`motionlab/stress.py`: 5-minute runs, pushes, flicker, cold starts, steering, body checks)
found that v4:
- froze in every 5-minute run;
- glided in 90% of moving frames and hovered with its feet tucked 43% of the time;
- never turned.

**What has been fixed so far, step by step (each measured by the battery):**
1. **A per-tick latent (learned prior).** Alone, with the foot losses, it fixed nothing.
2. **Free-run training:** batches that run alone, scored only on what holds at any horizon:
   feet on the floor, no wrist in the torso, no crossed legs, the limits, an energy band, the
   posture, and following the velocity input. **With the latent this ended the freezing**; a
   deterministic twin trained the same way still froze.
3. **Correlated run-time noise** (ρ 0.98): independent noise each tick made her shake (jitter
   15× the recordings').
4. **A velocity input** (`MotionSignal.velocity`, a v5 draft).

5. **Steering and facing** (counterfactual commands in free runs, a facing reward). Gliding
   models now go where they're sent: `latent-vel-free7` reaches speeds within 10% and
   directions within 2°; `free8` turns to face a new heading in about 4 s.
6. **The foot lock** (the M2 foot lock, built into the step): she travels only by stepping, the
   lowest foot rests on the floor (the ground lock), flight is limited to 0.3 s, and the root
   step is capped.
   - Penalties couldn't stop the gliding (free8); the lock makes it, and hovering,
     impossible.
   - Replaying recordings through it reproduces 84 to 88% of their walking travel.

**Where it stands (2026-10-31, 25 runs):**
- **`latent-vel-lock-sup`**, trained under the locks on the supervised losses alone, is the
  first model that is alive and on planted feet. Energy holds for 5 minutes; feet are carried
  0.04% of the time, against the recordings' 3.4% and free7's 99.7%.
- **Open:** under the lock, no model has yet learned to follow the velocity command (lock-sup
  shuffles at about 0.21 m/s whatever is asked) or to face where it goes.
- Every foot-locked fine-tune with free runs (free9 to free14) collapsed into stillness, a
  crouch or crossed legs instead of learning to step.
- **Training:** `lock-free` (free runs on top of lock-sup) and `lock-sup2`.
- **Also found:**
  - the GRU's memory drifts in long runs (staggered resets help models without free runs);
  - validation's short free runs don't predict 5-minute behaviour, so checkpoints are now
    kept for the battery to choose from.
- Details: motion-lab's `versions/v5/README.md` and changelog.

Each model version is self-contained in motion-lab's `versions/vN/`; motion-lab's `docs/M1.md`
lists them.
- **Data:** LAFAN1, 100STYLE and CMU (with BABEL's labels), about 37 hours, retargeted at 60 Hz
  with foot contacts and split by performer. AMASS's converter is built; AMASS itself wasn't
  downloadable in time.
- **Model:** 828,643 parameters (per-input encoders, FiLM, fusion, a GRU and a decoder; the
  rotation head).
- **v1:** smooth, but it drifts between the datasets' differing neutral poses and winds down.
- **v2:** retargeting relative to each dataset's T-pose fixed the cross-dataset posture
  disagreement. Two things remain:
  - over 60 s free runs it drifts into limb poses no recording has;
  - it is about 10× calmer than the data.
- **v3:** three changes aimed at that drift:
  - a data-quality filter (CMU has flipped hands, heads and feet, and 361 duplicated takes);
  - joint and hips limits measured from the data, with a loss past them (replacing the M0
    placeholders, as this stage planned);
  - rollouts of up to 128 ticks.
  - Trained for 9.4 h; results in motion-lab's `versions/v3/README.md`.
- **Open:**
  - intent and emotion keywords (MotionSignal v2), for the calmness;
  - the 17.5M size test, on v3's setup;
  - the viewer.

- **Purpose:** a stable, natural recurrent model that already does what SORA does most (walk,
  stand, sit, wave, lean, point, look). Its neutral-input version is the **control** for every
  later stage.
- **Data:**
  - AMASS with **BABEL**'s frame-level action labels (about 43 hours; labels include walk,
    stand, sit, wave, lean, point, look/face direction and fall; climbing exists only as stairs);
  - **LAFAN1** (CC BY-NC-ND 4.0: training for private use is fine, but retargeted copies must not
    be shared; 30 fps; 77 sequences), whose categories include fall and get up, ground,
    obstacles, walk and run;
  - both retargeted to the canonical skeleton, resampled to 60 Hz, mirror-augmented and split
    by subject, with contact flags from FK;
  - **intent labels** come from BABEL and LAFAN1's categories, mapped onto `MotionSignal.intent`,
    so intent is trained here rather than waiting for M6.
- **Architecture (decision 2):** a pose encoder plus encoders for intent, emotion, audio,
  attention and context, fused into a GRU and a decoder. In M1 only intent has data; the other
  inputs get `MotionSignal`'s neutral values and are trained in by later stages.
- **Output (decision 1):**
  - a joint-rotation head (normalised 6D per joint), as VISION describes;
  - an angular-velocity head (`ω = ω_max·tanh(raw)`, integrated) trained alongside for
    comparison;
  - the winner is chosen on the gate's measurements.
- **Training:**
  - teacher forcing, then scheduled sampling, then a multi-step rollout loss (a 1→8→32
    curriculum);
  - input noise, hidden-state burn-in, and joint limits from day one;
  - geodesic, velocity, FK-position and acceleration losses.
- **Tools:**
  - an evaluation harness: 60 s+ autoregressive rollouts, drift against horizon, saturation,
    foot slide, jitter, and comparison with the dataset's distribution;
  - **the physics ladder (MA)** once the physics body exists: the least help each scenario
    needs. `fall` and `get_up` are among the intents (LAFAN1's fall-and-get-up, BABEL's fall),
    and training adds random pose perturbations so the model copes when physics moves her off
    its target;
  - a **browser (three.js) VRM viewer** showing dataset clips beside rollouts. The owner judges
    from it.
- **Model size (owner decision, 2026-10-11; updated 2026-10-25).** The size is a measured result,
  not a choice made up front.
  - **2026-10-25:** on the owner's GPU, models under about 100M parameters run almost
    instantly in a few hundred MB, so the CPU budget below no longer caps the size.
  - The end goal, nuanced and expressive motion with meaningful fingers, gaze and unusual
    movements, is expected to need a much bigger model than the first controller.
  - So the sweep reaches larger sizes: a 17.5M model (GRU 1024 × 2) is trained beside the
    0.8M control on v2's data.
  - An open idea: a large semantic part reading the brain's intent from text at a low rate,
    feeding a fast motion part at 60 Hz.
  - **What limits it:**
    - **Runtime is not the limit at this scale.** A GRU costs about its parameter count in
      multiply-adds per tick. 1×256 with a 256-wide fused input is about 0.4M parameters, which
      is about 24M multiply-adds a second at 60 Hz, well under a millisecond on a CPU even in
      plain C#. The runtime spike measures the real ceiling.
    - **Data is the limit.** BABEL's labelled AMASS (about 43 hours) plus LAFAN1 (about 4.6
      hours) is roughly 10M frames at 60 Hz, but neighbouring frames are nearly identical, so
      the true variety is far smaller. Too large a model memorises clips. The subject-disjoint
      split shows it as a gap between training and held-out results.
  - **The sweep:**
    - train widths 128, 256 and 512, each with one and two GRU layers (six runs), on identical
      data and recipe, with the chosen output head;
    - plot every gate metric against parameter count: stability, distribution match, intent
      accuracy, transition smoothness and the train/held-out gap;
    - **adopt the smallest model within noise of the best on every metric** (proposed: within
      5%), provided it runs with at least 10× headroom under the spike's measured budget;
    - record the curve in the M1 evidence. The estimate is 256 to 512 units (about 0.4M to
      1.2M parameters), but the sweep decides;
    - prefer a moderate hidden state over the very smallest: the body-awareness observer (B4)
      reads it later.
  - **Growing it later:** only when a stage's evidence shows the model is short of capacity
    (for example, training loss that stops improving while held-out results lag), and never
    because "bigger should be better".
- **Gate:**
  - **stability:** 60 s rollouts on held-out data with no NaN, divergence or saturation;
  - **realism:** statistics within the dataset's distribution (thresholds in the M1 task plan);
  - **intent:**
    - a classifier trained on BABEL recognises the commanded intent in rollouts (proposed:
      ≥ 85% on held-out intents);
    - intent switches don't pop (proposed: peak transition acceleration within the dataset's
      99th percentile);
  - **decisions recorded:**
    - the rotation-head versus ω-head comparison;
    - the model size, from the sizing sweep and the spike's latency;
    - **the per-skill report** (input to the M7 decision): the same metrics broken down by
      movement type (idle, walking, sitting, waving, leaning, pointing, getting up), so it is
      clear whether rare skills lag behind common ones;
  - **the owner judges the idle motion not stiff,** in a dated note.

### M2: Constraint layer (medium)

- **Purpose:** a deterministic pass that makes predicted motion valid. It's built in Python as
  the reference the C# runtime must later match. **Since MA (2026-10-15)** the physics body
  handles contact and joint limits at runtime, so M2 keeps foot lock, gaze IK and the soft
  training losses.
- **Builds:**
  - **a solver for the desktop:**
    - joint limits;
    - contact with the current support surface (taskbar, window top or window edge);
    - simple gaze IK;
    - foot lock;
  - soft versions of these as training losses;
  - per-frame correction telemetry;
  - golden traces (state → corrected pose) for the C# conformance suite.
- **Gate:**
  - constrained 60 s rollouts stay stable;
  - corrections are small and don't persist (thresholds from the M1 control's statistics);
  - fixtures generated.

### M3: Speech and gesture (medium; needs a corpus)

- **Purpose:** body, head and gesture timing that follows her speech. Lip-sync stays with the
  existing system.
- **Data:** a speech-and-gesture corpus with audio. The candidate is **BEAT2**, listed as
  Apache-2.0 on Hugging Face with audio and text (the owner confirms its terms at download), or
  BEAT, whose recordings carry emotion labels that M5 can reuse.
- **Builds:** a causal audio encoder over `MotionSignal.audio` (her own TTS output, which Core
  already produces), trained in with on/off ablations so the effect is shown to come from the
  audio.
- **Gate:**
  - on held-out clips, the audio-on model shows speech-correlated body and head timing that the
    audio-off model doesn't (metric fixed in the M3 plan);
  - the 60 s battery passes; no regression.

### M4: Attention and desktop context (medium)

- **Purpose:**
  - natural look-at: eyes, head, neck and torso participation is learned, with deterministic
    gaze correction on top;
  - motion that suits where she is: standing on the taskbar, standing on a window top, or
    sitting on an edge.
- **Inputs:** `MotionSignal.attention` and `context` (monitor, support surface). The motion
  layer computes geometric features (direction, distance, visibility) from the resolved target;
  the network never rediscovers geometry.
- **Builds:**
  - **attention:** synthetic attention targets sampled along the observed gaze ray, for motion
    capture that has none;
  - **support-surface conditioning:** standing, sitting on an edge, the surface's height;
  - an onset/offset test.

  Other environment flags are used only if they can be derived from contract fields (for
  example "seated" from `intent = sit`) or are added by a contract bump.
- **Gate:**
  - look-at onsets and offsets within the dataset's measured timing;
  - support-surface poses valid in the M2 solver (no penetration, feet or seat on the surface);
  - no regression.

### M5: Emotion, and the desktop data factory (medium to large)

- **Purpose:**
  - emotion conditioning;
  - the motions SORA needs that no dataset has.
- **Emotion:**
  - the contract's dimensions are **valence and arousal**, plus a label only if the owner
    adopts a label set (decision 7);
  - training data comes from the speech corpus's emotion labels where it has them, mapped to
    valence and arousal, plus heuristic pre-labels (for example energy from velocity) checked by
    agents.
- **The desktop data factory:**
  - **tools:** a clip scrubber and segmenter;
  - **sources:**
    - the existing deterministic Unity animations as seed clips;
    - hand-keyframed clips;
    - the M8-prerequisite traces of what SORA actually does on the owner's desktop;
  - **targets:** leaning on a window, sitting on a window edge, and climbing up onto a window
    (which no dataset contains: BABEL's climbing is stairs, and LAFAN1's "obstacles" are
    vaults);
  - export to the training format, with label coverage documented.
- **Gate:**
  - the same intent under different valence and arousal gives measurably different motion
    statistics, stable over 60 s;
  - the desktop skills have enough clips to train M7 (count fixed in the M5 plan), or a recorded
    decision to keep that skill deterministic;
  - no regression.

### M6: SORA's own intents and conversation states (medium)

- **Purpose:** what SORA does that ordinary motion capture doesn't know about:
  - `present`;
  - looking at and pointing at a desktop target (`intent_target`);
  - the listening, thinking, speaking and waiting-for-agent states as their own idle
    behaviours;
  - transitions between all of them.
- **Builds:**
  - **intent embedding:** extended beyond M1's mocap intents;
  - **conversation:** a separate input;
  - **hysteresis:** kept upstream, so intent doesn't flicker;
  - **a transition test set.**

  Gestures that aren't in the vocabulary (nodding, shrugging, explaining) should emerge from
  conversation state, audio and attention, or need a contract bump.
- **Gate:**
  - every `MotionSignal.intent` and conversation state produces distinguishable dynamics on
    held-out data;
  - transitions don't pop (the M1 measure);
  - the 60 s battery passes.

### M7: Skill experts (medium; optional)

- **Purpose:** a soft-routed mixture of experts. VISION says "possibly", so it ships only if it
  beats the single model.
- **When it is built (owner decision, 2026-10-11):** considered only after core v1 is trained,
  and built only if the evidence asks for it.
  - **What it fixes:** a single network averaging very different movement regimes (getting up
    blurred into walking), or rare skills drowned out by common ones. Gated experts are a known
    remedy in character animation (for example mode-adaptive networks and motion VAEs).
  - **The decision point:** the per-skill report at the M1 gate, repeated after M5 and M6
    (leaning and climbing on windows have no data before M5, and they are the skills experts
    would exist for).
  - **Cheap fixes first,** in this order, re-running the per-skill report after each:
    1. a somewhat larger single model (the next size in the sweep);
    2. oversampling the lagging skills in training;
    3. stronger intent conditioning.
  - **Build M7** only if a skill still fails its gate after all three while the common skills
    pass. If every skill passes, M7 is skipped and the decision recorded; one well-trained GRU
    is simpler to train, export and debug.
  - **Costs, which the gate must justify:**
    - every expert runs every tick, so compute multiplies (still cheap at this size);
    - the router can flicker or leave experts unused;
    - training gets a stage harder.
  - Nothing earlier changes for this. The pure-function interface and separate output stage
    already let experts be added without touching the contract.
- **Experts (decision 3, default):**
  - general;
  - **getting up** (LAFAN1's fall-and-get-up and ground clips, starting from wherever MA's
    physics body came to rest);
  - **leaning**;
  - **climbing** (M5 data).
- **Builds:**
  - soft routing, with all experts updated every tick;
  - router stickiness;
  - a supervised routing bootstrap that is gradually relaxed;
  - load-balance and entropy terms.

  Blending follows M1's output head: velocities are blended before integration; 6D rotations are
  blended and then re-orthonormalised (never by averaging rotation matrices).
- **Gate:**
  - at least equal to the M1 control on every earlier gate;
  - no dead experts;
  - smoother regime switches;
  - each skill completes from its start state (proposed: ≥ 90% of test starts).

### M8 prerequisite: `MotionSignal` and trace logging in SORA (small; right after V1 closes)

- **Why early:**
  - VISION requires the interface to be fixed before the model is built;
  - SORA-specific data (her real desktop situations and transitions) only exists if it is
    logged, so logging should start months before M8;
  - it also enables the body-state line (B1 in
    [BODY_SELF_AWARENESS](BODY_SELF_AWARENESS_2026-10-09.md)).
- **Builds:**
  - **the contract** and its schema export;
  - **emission** from a focused module in Core;
  - **the deterministic Unity layer** reading only `MotionSignal`;
  - **opt-in logging** of `MotionSignal` plus the realised poses, kept in the profile and used
    for M5 and M8.
- **Gate:**
  - V1 step 5 behaviours (sit, walk or run to a window, look, point) unchanged;
  - schema exported; logging verified in an isolated profile.

### M8: SORA integration (medium)

- **Purpose:** the learned core runs in the real app. **Owner decision (2026-10-25):** it
  doesn't replace the deterministic layer outright. A setting in SORA's GUI swaps between the
  trained model versions (`motion-lab/versions/vN`) and the current algorithmic system, which
  stays the default and the fallback. The work starts once a model version looks usable
  (v2 or later).
- **Builds:**
  - ONNX in Unity on the runtime chosen by the spike, behind the pose-ownership arbiter. The
    learned core is the base layer, driving MA's physics body; gaze, reach and grab are
    overrides;
  - a C# constraint twin that passes the M2 golden traces;
  - the deterministic root;
  - the ragdoll-to-getting-up handover;
  - a fine-tune on the logged traces;
  - an A/B test against the deterministic layer.
- **Gate:**
  - **the frame budget holds** alongside llama.cpp, the memory embedder and a running game
    (budget set in the M8 plan from the spike's measurements);
  - **the C# twin passes the golden traces;**
  - **V1 step 5 behaviours don't regress;**
  - **the trace fine-tune improves;**
  - **owner acceptance.**

**After M8:** the body self-awareness observer (B4 in
[BODY_SELF_AWARENESS](BODY_SELF_AWARENESS_2026-10-09.md)), which reads the rig and the GRU's
hidden state and is trained on motion the core generates.

## 5. Changes from the 28 September roadmap, and from Grok's draft

| Item | 28 September | Grok's draft (2026-10-11) | This plan |
|---|---|---|---|
| Who builds, and when | Owner, after A Levels | Agents, now | Agents, now (rank 1) |
| Output | Angular velocity only | Rotation head, ω arm compared | Same as Grok's draft |
| Input order | Unconditioned prior; intent last (M6) | All encoders from M1, neutral; intent still waits for M5 labels (M6) | All encoders from M1; **intent trained in M1** from BABEL and LAFAN1 labels. M6 becomes SORA's own intents and conversation states |
| Experts | General, locomotion, recovery, contact | General, getting up, leaning, climbing | Same, with data sources named (getting up: LAFAN1; leaning and climbing: M5) |
| Model size | About 0.5M target | Measured | Measured, starting at 1×256 |
| Unity spike | Gates M0 | Early, non-gating | Same |
| Viewer | Browser, M1 | Browser, M1 | Same |
| Emotion | Five dimensions | Valence and arousal | Valence and arousal, trained from corpus emotion labels where available |
| Audio | Log-mel | `rms` and `voiced` only; log-mel as a later v2 | Decided **before** the contract is built (decision 8): `rms` and `voiced` are thin for gesture timing |
| Annotation factory | Emotion and intent labels | Emotion and intent labels | The **desktop data factory**: leaning on, sitting on and climbing onto windows, which no dataset has |
| `MotionSignal` in SORA | Rides the presentation contract at M8 | Built at M8 (after V1) | Built **right after V1**, with trace logging, so SORA-specific data builds up before M8 |
| The desktop setting | Screen-plane root only | Not discussed | Rule 9; M2, M4 and M5 cover support surfaces and screen scale |
| Datasets | "Licences to confirm" | Unverified coverage | Checked 2026-10-11: LAFAN1 CC BY-NC-ND 4.0 with fall and get up; BABEL labels; BEAT2 Apache-2.0 on Hugging Face |
| Training hardware | "Which GPU?" | Named | Checked: PyTorch 2.12 with ROCm 7.14 sees the GPU |
| Avatars and physics | Retarget to a canonical skeleton; ragdoll deterministic | Not covered | **MA (2026-10-15):** fitting any VRM; a physics body with a help dial defaulting to zero; physical falls; hair, clothing and accessories with their own physics |

## 6. Defaults the owner can change

1. **Output head:** joint rotations as VISION says, with an ω head compared in M1; the measured
   winner is adopted.
2. **Inputs:** all encoders exist from M1; intent is trained in M1, and the others are trained
   in by later stages.
3. **Experts (decided 2026-10-11):** considered after core v1 is trained, and built only if
   the per-skill report still shows a skill failing after the cheap fixes (M7). If built, the
   experts are general, getting up, leaning and climbing.
4. **Size (decided 2026-10-11):** the M1 sizing sweep picks the smallest model within noise of
   the best, with 10× runtime headroom; no fixed target.
5. **Timing:** motion-lab work starts now; the M8 prerequisite starts right after V1 closes; M8
   follows research acceptance.
6. **Runtime spike:** during M0 or M1, in a scratch Unity project.
7. **Emotion labels:** valence and arousal only until persona writing needs labels.
8. **Audio fields (decide before M0 freezes the contract):** default `rms`, `voiced`, pitch and
   onset strength, computed from her TTS output. Hearing the owner's speech stays out of v1.
9. **Labelling:** agents label; the owner reviews only if they want to.
10. **Physics help (decided 2026-10-15):** a dial defaulting to zero. Help is added only where
    the physics ladder shows it is needed, and the goal is a model subject only to physics.
    Physics-in-training is optional and started only on the ladder's evidence.

**Owner actions:**
- register for AMASS and accept its licence (BABEL builds on it);
- accept LAFAN1's licence;
- confirm the speech corpus's terms;
- give GPU time while SORA is idle;
- judge M1 idle motion and the M8 A/B test.

## 7. Documents kept in step

- Updated with this plan:
  - VISION.md, the motion paragraph and roadmap item 3;
  - V1.md's scope table;
  - the body self-awareness plan's link;
  - a dated note in the motion interface design;
  - the docs index and the archive README.
- **motion-lab** (the owner's folder, git-tracked) still holds the 28 September README and
  stage briefs. To keep one definition of each stage, they should become short pointers to this
  plan. This waits for the owner's go-ahead to edit that folder.
- The phase number in `SORA_IMPLEMENTATION_PLAN.md` is still open.
