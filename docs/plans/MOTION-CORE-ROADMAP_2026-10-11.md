# SORA motion core: rationalised roadmap

Prepared **2026-10-11** by **Opus 5.5**. It builds on a draft by Grok Bot, kept unchanged at
[archive/MOTION-CORE-ROADMAP_2026-10-11_GROK-ORIGINAL.md](archive/MOTION-CORE-ROADMAP_2026-10-11_GROK-ORIGINAL.md).
It replaces the [28 September roadmap](archive/MOTION-CORE-ROADMAP_2026-09-28.md).

The owner asked: "Recent developments take precedence over older decisions. Could you
rationalise the roadmap and define each stage for me?"

**Status: current plan. M0 is in progress** (see M0 below). Stage IDs M0 to M8 are kept, so
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
   - falling, being dragged and ragdoll physics.

   Getting up afterwards becomes a learned skill (M7) once the ragdoll hands back control.
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
([evidence](../verification/MOTION_M0_Opus-5.5_2026-10-11.md)); 33 tests pass, including the
avatar adapter. Two items are still open:
- the skeleton table's line-by-line review by a second agent;
- the non-gating Unity runtime spike.

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

### M1: Data, motion prior and intent (large; critical path)

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
  - a **browser (three.js) VRM viewer** showing dataset clips beside rollouts. The owner judges
    from it.
- **Model size (owner decision, 2026-10-11).** The size is a measured result, not a choice made
  up front.
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
  the reference the C# runtime must later match.
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
  - **getting up** (LAFAN1's fall-and-get-up and ground clips, starting from the ragdoll's end
    pose);
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
  - V1 step 5 behaviours (wave, sit, walk or run to a window, look, point) unchanged;
  - schema exported; logging verified in an isolated profile.

### M8: SORA integration (medium)

- **Purpose:** the learned core replaces the deterministic layer in the real app.
- **Builds:**
  - ONNX in Unity on the runtime chosen by the spike, behind the pose-ownership arbiter. The
    learned core is the base layer; gaze, reach, grab and ragdoll are overrides;
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
