# SORA motion core: rationalised roadmap

Prepared **2026-10-11** by Grok Bot. It completes the rationalisation that the owner's Claude Code
session started ("Recent developments take precedence over older decisions. Could you rationalise
the roadmap and define each stage for me?") and could not finish because it hit its usage limit.
Intended location: `docs/plans/MOTION-CORE-ROADMAP_2026-10-11.md`. Links below are written for that
folder.

**Status: proposed, not signed off. Nothing is implemented, and no SORA source or motion-lab file
has been changed.** This document is meant to supersede the
[28 Sep roadmap](MOTION-CORE-ROADMAP_2026-09-28.md) once the owner accepts it. Stage IDs M0 to M8
are kept, so nothing is renumbered.

## 1. Precedence

Where sources disagree, the newer one wins:

| Rank | Source | Date |
|---|---|---|
| 1 | The owner's decision in the Claude session: he will **not** build or train the motion core himself, and he does not want to wait until after A Levels. Agents build and train it. The owner supplies dataset sign-ups and licences, training-hardware time and naturalness judgements | 2026-10-11 |
| 2 | [VISION.md](../../../VISION.md) (agreed 5 Oct) and the owner's ChatGPT "Embodied Semantic Observer" brief (sent 9 Oct) | 2026-10-05 / 09 |
| 3 | [Motion interface design](../MOTION_INTERFACE_DESIGN_2026-10-05.md) (`MotionSignal`) | 2026-10-05 |
| 4 | [28 Sep roadmap](MOTION-CORE-ROADMAP_2026-09-28.md) (DeepSeek Flash, never signed off), then the `motion-lab` README and stage briefs (file times show they were written 26 minutes after it) | 2026-09-28 |

VISION.md stays the top authority, and only the owner changes it. Where rank 1 contradicts VISION's
wording, this document follows rank 1 and lists the VISION edit for the owner to approve (§7).

Some engineering choices in rank 4 conflict with wishes the owner stated in rank 2. In those cases
this document takes the owner's version as the default, gives the engineering reason in a sentence
or two, and lists the choice in §6. Nothing is silently overruled.

## 2. Rules for every stage

**Architecture**

1. Language models never drive joints. Core publishes semantic state, and the motion core turns it
   into movement (VISION).
2. The motion core's only input from SORA is **`MotionSignal` v1** as designed on 5 Oct: `intent`,
   `intent_target`, `conversation`, `emotion {valence, arousal, label?}`, `attention {target,
   salience}`, `audio {rms, voiced}` and `context {monitor_id, support_surface_id}`. A new input
   needs a contract version bump agreed with the owner. The roadmap's draft `CognitiveMotionState`
   is retired in favour of `MotionSignal`. `CanonicalState`, `CanonicalPose` and the adapter stay
   internal to motion-lab until M8.
3. Output, outside Core: **joint rotations** for the avatar. Nothing returns to Core except
   `EmbodimentFeedbackEvent`. The learned core replaces the deterministic layer wholesale, with no
   changes upstream.
4. The canonical skeleton is the **VRM Humanoid bone set**: about 20 joints, no fingers in v1, and
   every dataset retargeted onto it. Rotations are relative to the rest pose and expressed in the
   parent's local frame. These conventions are written once in the M0 spec, with tests. Never Euler
   angles, and never delta-6D outputs.
5. Any velocity fed back as input is computed from the **realised pose (after constraints)**, never
   from the model's own raw output.
6. The network is a pure function `f(state, h) → (output, h')` and exports cleanly to ONNX from day
   one (no exotic operations).
7. The root trajectory stays deterministic: on the screen plane, owned by the existing coordinate
   authority. Fall, drag and ragdoll physics stay deterministic systems. A learned getting-up motion
   (decision 3) takes over only once the ragdoll hands back control.
8. Model size is set by measurement, within the runtime budget (decision 4). Capacity grows only
   when evaluation shows a deficiency that more capacity could plausibly fix (ChatGPT brief).

**Process**

9. Research lives in the separate `~/Desktop/motion-lab` project. SORA receives nothing until M8.
10. Every stage after M1 is compared against the **M1 control** and must not regress the 60-second
    stability battery.
11. Gates are measurable thresholds with recorded evidence, labelled by kind (fixture, component,
    native, live model, hardware), following AGENTS.md. A gate is not ticked until it has passed.
    Thresholds marked "proposed" are this document's suggestion. The sources do not specify them,
    and they are confirmed in each stage's task-level plan.
12. Agents do the building, training, evaluation and write-ups. Agents cannot accept licences or
    create accounts. Training uses the owner's GPU only while SORA is idle or closed. The Claude
    session named an RX 9070 XT with the ROCm PyTorch environment at `.local\decision\train-env`.
    Agents leave the owner's running SORA alone.
13. AGENTS.md applies as usual: never delete files, write a changelog under your own model name, and
    don't commit, push or merge unless the owner asks in the current session.

## 3. Who does what

| Owner | Agents |
|---|---|
| Registers for datasets and accepts their licences (AMASS, LAFAN1, the M3 speech-and-gesture corpus) | Everything else: code, data pipelines, training, evaluation, tooling, reports, document updates |
| Gives training-hardware time (GPU while SORA is idle) and Unity time for the runtime spike and M8 | Schedules runs around that time and reports evidence |
| Judges naturalness: M1 idle motion, the M8 A/B test, and optional spot checks in M3 to M7 | Supplies everything else as measured metrics |
| Makes the decisions in §6 and approves the VISION.md edits | Proposes defaults and raises conflicts rather than assuming |

## 4. Stages

| Stage | Size | Depends on | Owner input |
|---|---|---|---|
| M0 Foundations and specs | Small | Nothing | None (Unity time for the optional spike) |
| M1 Motion prior and full-input architecture | Large, critical path | M0; AMASS and LAFAN1 licences | Licences, GPU time, idle-naturalness judgement |
| M2 Constraint layer | Medium | M1 | GPU time |
| M3 Audio / prosody | Medium | M1, M2; speech-and-gesture corpus licence | Corpus licence |
| M4 Attention and context | Medium | M1, M2 | GPU time |
| M5 Annotation factory and emotion | Medium to large | M1 (tooling can start earlier) | Optional label review |
| M6 Semantic intent | Medium | M5 intent labels | GPU time |
| M7 Skill experts (optional) | Medium | M1 to M6 | GPU time |
| M8 SORA integration | Medium | Research accepted; `MotionSignal` built in SORA; runtime spike | Unity/hardware time, A/B acceptance |

The sources give relative sizes only. No durations are specified.

### M0: Foundations and specs (small)

- **Purpose:** the maths, skeleton and data formats that every later stage uses. Nothing is trained.
- **Inputs:** VRM Humanoid bone set; the Seed-san VRM; `MotionSignal` v1.
- **Outputs:** a tested Python package and specs.
- **What gets built:**
  - a rotation library: 6D↔R conversion, SO(3) Exp/Log, integration `R' = R·Exp(Δt·[ω]×)` and
    finite-difference ω. It is needed for either output choice (decision 1), for feedback inputs
    and for evaluation;
  - a canonical skeleton table (joints, parents, rest offsets, per-joint limits, placeholder
    ω_max) as the single definition every module imports;
  - tensor and windowing formats (radians, metres, 60 Hz tick);
  - `MotionSignal` v1 frozen as the motion-lab input schema;
  - an ONNX export-and-reload smoke test in Python.
- **Runtime spike (does not gate M0, see decision 6):** a tiny GRU exported to ONNX and run in
  Unity 6.6 at 60 Hz on the VRM, with per-tick latency measured. It decides between Sentis, an ONNX
  Runtime plugin and a hand-written C# GRU.
- **Who:** agents. The owner reviews nothing unless he wants to. The skeleton table is checked line
  by line by a second agent.
- **Exit gate:**
  - all tests green: 6D→R→6D round trip, Exp/Log inverses, orthonormality kept over long
    integration chains, FK against a hand-computed fixture, mirror symmetry (proposed tolerances: round
    trip < 1e-5 and orthonormality error < 1e-4 after 100,000 integration steps, in float32);
  - the skeleton table reviewed line by line;
  - the ONNX model reloads and matches PyTorch output (proposed: max abs difference < 1e-5);
  - FK cross-checked against Unity golden poses **if** the spike has run. Otherwise this check moves
    to the spike.

### M1: Motion prior and full-input architecture (large; critical path)

- **Purpose:** a stable, natural recurrent motion model. Its neutral-input version is the
  **control** that every later stage is compared against.
- **Inputs:** AMASS and LAFAN1, pending licences, retargeted to the canonical skeleton.
- **Outputs:** a trained model, an evaluation harness and a viewer.
- **What gets built:**
  - **Data pipeline:** retargeting; 60 Hz resampling (SLERP); mirror augmentation;
    subject-disjoint splits; 1 to 2 s windows; contact flags from FK; normalisation statistics.
  - **Architecture (default per decision 2):** a pose encoder plus **encoders for intent, emotion,
    audio and context** (and attention), fused into a GRU (start 1×256; try 2 layers) and a
    decoder. Base mocap has none of these labels, so in M1 they are fed `MotionSignal`'s neutral
    values (for example emotion `{0, 0.3}`) and are trained in by later stages.
  - **Output head (default per decision 1):** joint rotations as normalised 6D per joint. An
    angular-velocity head (`ω = ω_max·tanh(raw)`, integrated) is trained as a comparison arm.
    There is an optional root planar velocity head, although the root stays deterministic at
    runtime.
  - **Training:** teacher forcing, then scheduled sampling, then a multi-step rollout loss
    (1→8→32 curriculum); input noise; hidden-state burn-in; joint limits from day one. Losses:
    geodesic, angular velocity, FK position and acceleration.
  - **Evaluation harness:** autoregressive rollouts of 60 s or more; drift-versus-horizon curves;
    saturation rate; foot slide; jitter; distribution comparison with the dataset.
  - **Viewer:** a browser (three.js) VRM viewer showing dataset clips and rollouts side by side
    (resolution of item 7 in §5).
- **Who:** agents build and train. The owner registers for AMASS, checks and accepts the LAFAN1
  licence, gives GPU time, and judges the idle motion in the viewer.
- **Exit gate:**
  - 60 s rollouts on the held-out set with no NaN, no divergence and no saturation pathology;
  - rollout statistics within the dataset distribution (thresholds proposed in the M1 task plan;
    the sources do not specify them);
  - the rotation-head versus ω-head comparison recorded on these metrics;
  - model size chosen from measured results and the spike's latency, if available;
  - **the owner judges the idle motion not stiff**, recorded in a dated note.

### M2: Constraint layer (medium)

- **Purpose:** a deterministic pass that makes predicted motion valid, built in Python as the
  reference that the future C# runtime must match.
- **Inputs:** M1 rollouts.
- **Outputs:** a constrained pose, correction telemetry and golden fixtures.
- **What gets built:**
  - a reference solver covering joint limits, floor contact against the work-area ground, simple
    gaze IK, and foot lock if it stays simple;
  - differentiable soft proxies (limit hinge, penetration, gaze error) added to training;
  - per-frame correction-magnitude telemetry;
  - golden traces (state → corrected pose) exported for the C# conformance suite.
- **Who:** agents.
- **Exit gate:** constrained 60 s rollouts stay stable; corrections are small and do not persist
  (proposed: thresholds derived from the M1 control's correction statistics, with no correction
  sustained beyond a set number of frames; numbers unspecified in the sources); fixtures generated.

### M3: Audio / prosody (medium; needs a dataset)

- **Purpose:** body, head and gesture timing that follows her speech. This is not lip-sync, which
  stays with the existing system.
- **Inputs:** `MotionSignal.audio`, which is **her own TTS envelope only** under v1 (decision 8),
  and a speech-and-gesture corpus (candidate: BEAT-class; several are research-only).
- **Outputs:** a trained causal audio encoder fused into the M1 model.
- **What gets built:** a causal audio encoder (TCN or GRU) with its own feature rate, where each
  tick reads the latest latent. It is trained on features the contract carries (`rms`, `voiced`),
  with log-mel features as an ablation. If log-mel clearly wins, agents propose `MotionSignal` v2
  rather than changing the contract quietly. Audio on/off ablations prove the effect comes from the
  audio.
- **Who:** agents. The owner chooses and licenses the corpus.
- **Exit gate:** on held-out clips, the audio-on model shows speech-correlated body and head timing
  that the audio-off model does not (the metric is fixed in the M3 plan); the 60 s battery passes;
  no regression versus the control.

### M4: Attention and context (medium)

- **Purpose:** natural look-at behaviour, with eyes, head, neck and torso participation learned and
  deterministic gaze correction on top.
- **Inputs:** `MotionSignal.attention` (target, salience) and `context` (monitor, support surface).
  Geometric features (direction, distance, visibility) are computed by the motion layer from the
  resolved target. The network never rediscovers geometry.
- **Outputs:** an attention- and context-conditioned model.
- **What gets built:** feature computation; synthetic attention targets sampled along the observed
  gaze ray for mocap that has none; training and an explicit onset/offset test. The roadmap's
  extra environment flags ("user present", "seated", "distance") are not in `MotionSignal` v1.
  They are used only if derivable from contract fields (for example `seated` from `intent = sit`),
  or added through a contract bump.
- **Who:** agents.
- **Exit gate:** look-at onsets and offsets on held-out clips fall within the dataset's measured
  timing range (the metric is fixed in the M4 plan); no stability regression.

### M5: Annotation factory and emotion (medium to large)

- **Purpose:** tooling and labels for what the base datasets lack, and emotion conditioning.
- **Inputs:** M1 data; style-labelled corpora where licensed.
- **Outputs:** labelled windows (intent segments for M6; emotion labels) and an emotion-conditioned
  model.
- **What gets built:**
  - a clip scrubber and segmenter;
  - heuristic pre-labels (for example energy from velocity statistics) reviewed by agents;
  - emotion labels in the **contract's dimensions: valence and arousal**, plus a label only if the
    owner adopts a label set (decision 7). The roadmap's extra dimensions (confidence, curiosity,
    energy) are dropped from the interface. Agents may use them as internal training aids only if
    they map onto valence and arousal at the input;
  - export to the training format.
- **Who:** agents label with tools and heuristics. Owner review is optional (decision 9).
- **Exit gate:** the same intent under different valence and arousal produces measurably different
  motion statistics, and stays stable over 60 s; label coverage is documented; no regression.

### M6: Semantic intent (medium)

- **Purpose:** intent drives the motion.
- **Inputs:** `MotionSignal.intent`, which is the vocabulary: `idle`, `wave`, `sit`, `lean`,
  `climb`, `stand`, `walk`, `point`, `look` and `present`. Also `conversation` (`idle`, `listening`,
  `thinking`, `speaking`, `waiting_for_agent`) as a separate input, plus M5 intent labels.
- **Outputs:** an intent-conditioned model.
- **What gets built:**
  - intent embedding and training;
  - a test of intent-to-intent transitions;
  - hysteresis kept upstream, so intent does not flicker.

  The M6 brief's gestures (NOD, EXPLAIN, SHRUG, TURN_TOWARD_TARGET) are not in the vocabulary.
  They should emerge from `conversation`, audio and attention, or need a contract bump. The
  roadmap's "intensity" and "progress" inputs are not in `MotionSignal` v1 either. Progress can be
  tracked inside the motion layer; intensity would need a contract bump. The sources leave this
  unspecified.
- **Who:** agents.
- **Exit gate:** each intent produces dynamics distinguishable from the others on held-out data;
  transitions do not pop (proposed: peak joint acceleration during transitions stays within the
  dataset's 99th percentile); the 60 s battery passes.

### M7: Skill experts (medium; optional)

- **Purpose:** a soft-routed mixture of experts. VISION calls it "possibly", so it ships only if it
  beats the single model.
- **Inputs:** M6 model and data.
- **Outputs:** a mixture-of-experts model, or a recorded decision not to use one.
- **What gets built:**
  - **experts per decision 3 (default: general, getting up, leaning, climbing)**;
  - soft routing, with **all experts updated every tick**;
  - router stickiness, a supervised routing bootstrap that is gradually relaxed, and
    load-balance and entropy terms;
  - experts blended in velocity space before integration if the ω head is used. With a rotation
    head, blending must happen in a valid rotation space (never by averaging matrices), which is
    one reason decision 1 matters here.

  Shared trunk versus independent experts stays an experiment.
- **Who:** agents.
- **Exit gate:** at least equal to the M1 control on every earlier gate; healthy expert utilisation
  (no dead experts); smoother transitions on a regime-switch test set.

### M8: SORA integration (medium; after research acceptance)

- **Purpose:** the learned core replaces the deterministic layer in the real app.
- **Inputs:** the accepted model; the M2 golden fixtures; the runtime spike's result.
- **Outputs:** the learned core running as the base layer in Unity.
- **What gets built:**
  - `MotionSignal` implemented in SORA (interface design steps 1 to 3: contract and schema export,
    emission from a focused module, and the deterministic Unity path reading only `MotionSignal`).
    This is a prerequisite and can happen earlier (decision 5);
  - ONNX into Unity on the chosen runtime, behind the pose-ownership arbiter. The learned core is
    the base layer; gaze, reach, grab and ragdoll are overrides;
  - a C# constraint twin that passes the M2 golden fixtures;
  - the root kept deterministic, and the ragdoll-to-getting-up handover defined;
  - optional early trace logging from the current client, with explicit owner go-ahead;
  - an A/B test against the deterministic layer.
- **Who:** agents. The owner gives Unity and hardware time and runs the A/B acceptance.
- **Exit gate:**
  - the frame budget holds alongside llama.cpp and a running game (measured per-tick cost; budget
    number unspecified in the sources, proposed in the M8 plan);
  - the C# twin passes the golden fixtures;
  - V1 step 5 behaviours (wave, sit, walk or run to a window, look and point) show no regression;
  - a trace fine-tune improves;
  - **owner acceptance**.

**After M8:** the body self-awareness observer (B4 in
[BODY_SELF_AWARENESS](../BODY_SELF_AWARENESS_2026-10-09.md)), trained on motion the core generates.

## 5. Changes from the 28 Sep roadmap

The 28 Sep roadmap and the motion-lab material are kept, never deleted.

| # | Item | 28 Sep roadmap / briefs | Now | Decided by |
|---|---|---|---|---|
| 1 | Who builds, and when | Owner makes and trains M0 to M7 "after A Levels"; a coding agent does M8; the GUI brief expects deterministic animation "for most of the next year" | Agents build and train every stage, starting now. The owner supplies licences, hardware time and naturalness judgements | 11 Oct decision (rank 1). Timing relative to V1: decision 5 |
| 2 | Network output | Angular velocities integrated to rotations; rotation output forbidden | Default: joint-rotation head (VISION's wording), with an ω arm compared in M1. The contract output is joint rotations either way | VISION (rank 2) over roadmap; **open, decision 1** |
| 3 | Input order | Unconditioned prior first; audio M3, attention M4, emotion M5, intent last at M6 | Default: encoders for intent, emotion, audio and context in the architecture from M1, fed neutral values until their data arrives; later stages train them in. The neutral-input model is the control | VISION and ChatGPT brief (rank 2); **open, decision 2** |
| 4 | Experts | General, locomotion, recovery, contact | Default: general, getting up, leaning, climbing. M7 stays optional | VISION (rank 2); **open, decision 3** |
| 5 | Model size | Target about 0.5M parameters (labelled "agreed with owner", which cannot be verified) | Sized empirically within the runtime budget, starting at 1×256 | ChatGPT brief's principle (rank 2); **open, decision 4** |
| 6 | Unity in M0 | Roadmap: Unity runtime spike in M0. M0 brief: Unity intake moves to M8 | M0 gate is Python-only (the newer brief). The spike runs early as a non-gating task, because the lane split that moved it no longer exists and its result constrains decisions 1 and 4 | Briefs (newer within rank 4); timing is **decision 6** |
| 7 | Viewer | Roadmap: browser three.js VRM viewer in M1. M1 brief: still open | Browser three.js viewer in M1. The owner's main role is now judging naturalness, so he needs a viewer from M1, and deferring to M8 would leave nothing to judge | Rank 1 (owner judges naturalness) settles it; no owner decision needed |
| 8 | Emotion dimensions | M5: valence, arousal, confidence, curiosity, energy | Valence and arousal plus an optional label, as in `MotionSignal` | Interface design (rank 3) over roadmap; label set is **decision 7** |
| 9 | Whose audio | Not answered | Her own TTS envelope only (`MotionSignal` v1). The owner's speech is a possible v2 | Interface design (rank 3); **open, decision 8** |
| 10 | Audio features | M3: streaming log-mel | Contract features (`rms`, `voiced`) by default; log-mel tested as an ablation and proposed as v2 if it helps | Interface design (rank 3); folded into decision 8 |
| 11 | Input contract | `CognitiveMotionState` riding the presentation contract | `MotionSignal` v1 | Interface design (rank 3) |
| 12 | Intent vocabulary | "Existing registered semantic actions"; M6 brief lists IDLE, LISTEN, NOD, WAVE, POINT, EXPLAIN, SHRUG, TURN_TOWARD_TARGET | `MotionSignal.intent` enum, with conversation state as a separate input | Interface design (rank 3) |
| 13 | Environment flags | User present, seated, contacts, distance | Only what `MotionSignal.context`, `attention` and `intent` carry, or a contract bump | Interface design (rank 3) |
| 14 | Getting up | Falls, drag and ragdoll stay deterministic; "recovery" expert | Ragdoll physics stays deterministic; getting up afterwards is a learned skill (default) | VISION (rank 2); part of decision 3 |
| 15 | Old open items | Project location, datasets, hardware, phase number | motion-lab exists at `~/Desktop/motion-lab` (Python). Datasets still need the owner's licences. Hardware is the owner's GPU while SORA is idle. The phase number in `SORA_IMPLEMENTATION_PLAN.md` is still open | Facts from the Claude session |

Engineering trade-offs behind the open items:

- **Decision 1 (output).** The roadmap predicts angular velocity because integrating with
  `Exp` keeps every rotation valid by construction, caps per-tick speed through `ω_max`, and lets
  experts blend safely before integration. It cites velocity-space prediction helping short-term
  behaviour and long-horizon drift. A direct rotation head is simpler and matches VISION, but
  gives up those guarantees.
- **Decision 2 (input order).** The roadmap trains an unconditioned prior first because base mocap
  has no intent, emotion or audio labels, and adding one input at a time shows which input caused
  which change. The default keeps that benefit by treating the neutral-input model as the control
  and training each input in with an on/off ablation.
- **Decision 3 (experts).** The roadmap groups experts by dynamics (locomotion, recovery, contact)
  so that each expert sees enough data. Named skills risk thin data per expert. Leaning and
  climbing are both contact-heavy, and getting up overlaps "recovery". Whether AMASS or LAFAN1
  cover getting up and climbing well is unverified.
- **Decision 4 (size).** A fixed small budget keeps the hand-written C# runtime option open and
  stops scope creep. Empirical sizing may find a better model, but needs the runtime spike's
  latency figures to bound it.

## 6. Owner decisions needed

1. **Network output.** Default: the GRU outputs joint rotations, as VISION says; M1 also trains
   an angular-velocity arm, and you confirm the winner from the M1 gate data.
2. **Input order.** Default: encoders for intent, emotion, audio and context are in the model from
   M1, fed neutral values until each one's data exists. The neutral-input model is kept as the
   control.
3. **Experts.** Default: general plus getting up, leaning and climbing, as VISION says. M7 stays
   optional. Ragdoll physics stays deterministic, and getting up afterwards is learned.
4. **Model size.** Default: sized by measurement within the runtime budget, starting at 1×256,
   with no fixed 0.5M target.
5. **Start now, or after V1?** Default: motion-lab work starts now, since it is a separate
   project. SORA-repo changes (building `MotionSignal`, M8) wait until V1's acceptance test is
   closed, unless you say otherwise.
6. **Unity runtime spike.** Default: run it during M1 in a scratch Unity project, not your SORA
   install, when you can give Unity time. It does not gate M0.
7. **Emotion label set.** Default: valence and arousal only, with no fixed labels until persona
   writing needs them.
8. **Whose audio.** Default: her own speech envelope only (`rms`, `voiced`). Hearing you, or
   richer log-mel features, become a `MotionSignal` v2 proposal only if M3 shows they help.
9. **Hand labelling in M5.** Default: agents and heuristics do the labelling; you review only
   if you want to.
10. **Paperwork.** Default: approve the VISION.md and V1.md edits in §7, and archive the 28 Sep
    roadmap as a superseded original.

**Owner actions (not decisions):** register for AMASS and accept its licence; check and accept the
LAFAN1 licence; choose and license the M3 speech-and-gesture corpus; give GPU time while SORA is
idle; judge M1 idle motion and the M8 A/B test.

## 7. Documents to update to match

These edits are proposals only; none has been made. VISION.md changes need the owner's approval.
Record documents are not rewritten; they get a dated note instead (docs/README.md roles).

| Document | Location | Suggested change |
|---|---|---|
| `VISION.md` | Lines 50 to 51, "The goal is a **learned motion model built by the owner**:" | → "The goal is a **learned motion model, built and trained by agents; the owner supplies dataset licences, training-hardware time and naturalness judgements** (decided 2026-10-11):". Lines 52 to 53 ("outputs joint rotations", "getting up, leaning and climbing") change only if decisions 1 or 3 depart from the default |
| `VISION.md` | Line 98, "3. **After A Levels:** the learned motion model." | → "3. **Started 2026-10-11, alongside V1 and after-V1 work:** the learned motion model, researched in motion-lab and integrated into SORA after V1 ([roadmap](docs/plans/MOTION-CORE-ROADMAP_2026-10-11.md))." Adjust "after V1" if decision 5 changes |
| `V1.md` | Line 22, "Learned motion model (after A Levels)" | → "Learned motion model (research under way in motion-lab since 2026-10-11; integration after V1)" |
| `motion-lab/README.md` | Line 5 (status) | → "**Status:** stage briefs only, no code yet. Governed by `../SORA/docs/plans/MOTION-CORE-ROADMAP_2026-10-11.md`. Nothing integrates with SORA until M8." |
| `motion-lab/README.md` | Lines 9 to 11 (division of labour) | → "- **Agents build and train every stage, M0 to M8** (decided 2026-10-11). - **Owner (Oscar):** dataset sign-ups and licences, training-hardware time, naturalness judgements (M1 idle motion, M8 A/B) and the open decisions." |
| `motion-lab/README.md` | Line 16 (roadmap link) | Point to `MOTION-CORE-ROADMAP_2026-10-11.md`, "same stage numbering" |
| `motion-lab/README.md` | Lines 20 to 24 (invariants) | Line 20: replace "outputs are **angular velocities ω**" with "outputs are joint rotations (head type per roadmap decision 1)". Add "the only input from SORA is `MotionSignal` v1" and "model size is set by measurement" |
| Stage briefs M0 to M7 | Line 4, "**Lane:** make/train (owner)." (M2: "… — the C# runtime twin is integration (M8), built later by a coding agent.") | → "**Lane:** agents build and train; owner supplies licences, GPU time and naturalness judgements." |
| `M0-foundations.md` | Line 14, "The Unity intake test belongs to integration (M8)." | → "A Unity runtime spike runs early, during M1, in a scratch Unity project; it does not gate M0." Add "freeze `MotionSignal` v1 as the input schema" to "What you build" |
| `M1-motion-prior.md` | Line 11 (model) | → "pose encoder plus intent, emotion, audio, context and attention encoders (neutral inputs in M1) → GRU (start 1×256; try 2 layers) → decoder; joint-rotation head with an ω comparison arm. Size set by measurement." |
| `M1-motion-prior.md` | Line 22 (viewer open decision) | → "Viewer: decided, a browser (three.js) VRM viewer in M1." Add the owner's judgement to the gate |
| `M3-audio-prosody.md` | Line 10 (encoder on log-mel) | → "encoder on `MotionSignal.audio` (`rms`, `voiced`, her own speech); log-mel as an ablation, proposed as contract v2 only if it helps." |
| `M4-attention-environment.md` | Line 12 (environment flags) | → "context from `MotionSignal.context` (monitor, support surface); other flags only if derivable from contract fields or added by a contract bump." |
| `M5-annotation-emotion-style.md` | Line 11 (emotion dimensions) | → "emotion labels as valence and arousal (the `MotionSignal` dimensions), plus a label only if the owner adopts a label set." |
| `M6-semantic-intent.md` | Lines 7 and 10 (vocabulary) | → "Vocabulary = `MotionSignal.intent` (idle, wave, sit, lean, climb, stand, walk, point, look, present), with `conversation` as a separate input." |
| `M7-recurrent-moe.md` | Line 10, "4 experts (general / locomotion / recovery / contact)" | → "experts: general, getting up, leaning, climbing (roadmap decision 3); blending rule follows the output head chosen in M1." Mark the stage optional |
| `M8-integration.md` | Line 3, "**not the owner's lane.** Performed later by a coding agent (e.g. GPT-6 Astra) with the owner." | → "Built by agents; owner gives Unity time and runs the A/B acceptance." Add "build `MotionSignal` in SORA (interface design steps 1 to 3)" as a prerequisite, and replace `CognitiveMotionState` (line 8) with `MotionSignal` |
| `MOTION_INTERFACE_DESIGN_2026-10-05.md` (a record by Opus 5.5) | Lines 6, 14, 54 to 56 and 68 to 73 | Don't rewrite. Add a dated note under the title: "2026-10-11: the learned model is now built by agents, starting now, not after A Levels ([roadmap](../MOTION-CORE-ROADMAP_2026-10-11.md)). The open questions on the emotion label set and whose audio are owner decisions 7 and 8 there." |
| `BODY_SELF_AWARENESS_2026-10-09.md` | Line 5, link to `MOTION-CORE-ROADMAP_2026-09-28.md` | Repoint to `MOTION-CORE-ROADMAP_2026-10-11.md` (a link-path fix is allowed on records) |
| `MOTION-CORE-ROADMAP_2026-09-28.md` | Whole file | Once accepted, move to `docs/plans/archive/` with its wording unchanged, list it in the archive README's table as superseded by this roadmap, and update every link in living documents |
| `docs/README.md` | `plans/` row | Add the motion-core roadmap (2026-10-11) to the list of focused plans |
| GUI design v0.1, §11 ("for most of the next year while A Levels take priority") | Record | Leave unchanged; VISION's new line supersedes it. The GUI still must not depend on the motion core, which remains true |
| `SORA_IMPLEMENTATION_PLAN.md` | Phase list | Motion-core phase number still to confirm (open item from 28 Sep) |
| `changelog/` | New file | A changelog under the contributing model's name for this roadmap and every edit above |
