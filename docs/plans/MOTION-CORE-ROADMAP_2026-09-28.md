# SORA motion core — development roadmap

Prepared: **2026-09-28 12:24 +01:00 (Europe/London)**
Prepared for: **owner**
Status: **roadmap for review — nothing implemented, no SORA source changed**
Author: DeepSeek Flash (planning only; read-only survey)

Purpose: agree the stage structure, gates and scope for a learned motion core before task-level planning starts.
Fleshing-out follows owner sign-off; the research lives in a secondary project until it is integration-ready.

---

## 1. Goal and constraints (agreed with owner)

- Replace stiff procedural avatar motion with a learned, continuously-running motion core whose product is **naturalness**: idle behaviour, conversational motion, gesture quality, and — most importantly — transitions between them.
- The cognitive layer publishes semantics (semantic intent, emotion/style, attention target, speaking/listening state, environment flags). The language model never emits joint angles. The motion core converts state → continuous motion at 30–60 Hz.
- **Environment: desktop as 3D scene** — full 3D skeletal motion, root constrained to the screen plane (x/y + yaw, z fixed), explicit motion layers. Falls, drag and ragdoll remain the existing deterministic systems.
- Budget: ~0.5M-parameter single prior; a handful of small experts later. Negligible beside the local LLM and a running game.
- Research lives in a **secondary project** (proposed: `~/Desktop/motion-lab`); SORA receives specs, contracts and the Unity adapter at integration time.

## 2. Current state (verified read-only, 2026-09-28)

- Avatar motion today is entirely procedural, Unity-side: screen-plane locomotion, idle pose, weighted gaze, two-bone reach IK, grab, SpringBone, simple falling, screen-plane ragdoll recovery (P12.2/.3), semantic presentation profiles (P11.1, P15.5), one pose-ownership lease arbitrating between them.
- Target rig: **VRM via UniVRM** in Unity 6.6 (P09). Live2D does not exist in the project.
- No training code, no motion module in Core, no mocap data anywhere in the repo — greenfield.
- SORA is at P15 (85/91 items); the motion core is a future phase (numbering to confirm; P16 is pencilled for the settings editor).

## 3. Interfaces and invariants (from the brief; conventions to be pinned in M0)

- Inputs: 6D rotations (first two columns of R) per joint. Outputs: **angular velocities ω**, optionally root planar velocity. Never Euler; never delta-6D output.
- Integration: `R(t+1) = R_t · Exp(Δt·[ω]×)` — stays on SO(3) by construction.
- **ω is in the parent-relative local frame; rotations are rest-pose-relative.** Written once in the spec, with tests.
- Input ω is finite-differenced from the **realised (post-constraint) pose** — never recycled from the model's own raw output.
- MoE: blend ω before integration; never blend rotation matrices.
- **Canonical skeleton = VRM Humanoid bone set** (~20 joints, hips → head, arms, legs, feet, optional toes/eyes; no fingers in v1). Adapter = canonical → VRM Humanoid, near-free by construction.
- Interface drafts: `CanonicalState`, `CognitiveMotionState`, `MotionCommand`, `CanonicalPose`, `AvatarAdapter`. Promoted to `contracts/schema/v1` at integration.

## 4. Stages

### M0 — Foundations and specs (small)

- Rotation library: 6D↔R conversions, SO(3) exp/log, velocity integration; round-trip and numeric tests. Forward kinematics for the canonical skeleton.
- Canonical skeleton spec: joint list and hierarchy, rest pose, per-joint limits, ω_max from dataset velocity percentiles.
- Interface drafts written as versioned JSON ready for promotion to SORA contracts later.
- Secondary research repo stood up: Python package layout (math / data / model / train / eval), tests, configs.
- **Runtime spike ("hello world")**: tiny GRU exported to ONNX, running in Unity 6.6 (Sentis) at 60 Hz driving the Seed-san VRM through the canonical→Humanoid adapter, with measured per-tick latency.

**Gate:** math tests green; FK cross-checked against Unity golden poses; spike note answers "where does the net live at runtime" with numbers.

### M1 — Motion prior (large; critical path, the experimental control)

- Dataset pipeline: AMASS + LAFAN1 (pending licence confirmation) → retarget to canonical skeleton; 60 Hz resample (SLERP + ω recompute); mirror augmentation; subject-disjoint splits; 1–2 s windows; contact flags from FK; dataset statistics.
- Model: pose encoder MLP → single GRU (start 1×256, trial 2 layers) → decoder; `ω = ω_max · tanh(raw)`; optional root planar velocity head.
- Training: teacher forcing → scheduled sampling → multi-step rollout loss (1→8→32 curriculum); input-pose noise; hidden-state burn-in for cold starts; joint limits enforced from day one; losses = geodesic + angular velocity + FK position + acceleration (grow as needed).
- Eval harness: ≥60 s autoregressive rollouts; drift-vs-horizon curves; velocity-saturation rate; foot slide; jitter; dataset-distribution comparison.
- **VRM viewer** (browser, three.js): dataset clips and model rollouts side by side. Naturalness must be visible to be iterated on.

**Gate:** 60 s+ stable rollouts; statistics in-distribution; owner judges the idle motion not stiff.

### M2 — Deterministic constraint layer (medium)

- Python reference implementation: joint limits, floor/contact against the work-area ground, gaze IK, foot lock. Hard pass for evaluation; **differentiable soft proxies** (limit hinge, ground penetration, gaze error) for training losses.
- Correction-magnitude telemetry as a health metric; **golden traces exported** as the conformance fixture suite the future C# runtime must match.

**Gate:** constrained rollouts stable; corrections small and non-persistent.

### M3 — Audio / prosody (medium; needs a new dataset)

- Causal audio encoder (TCN or GRU) on streaming log-mel; feature rate vs tick rate handled; requires a speech+gesture corpus (candidate: BEAT-class; **license check — several are research-only**).
- Body/head/gesture timing relative to speech. Not lip-sync (that stays the existing specialist system).

**Gate:** speech-correlated timing on held-out clips; no stability regression.

### M4 — Attention and environment (medium)

- Deterministic attention features (direction, distance, visibility/confidence) fed as inputs — the net never rediscovers geometry; eyes→head→neck→torso participation is learned; deterministic gaze correction on top.
- Environment flags (user present, seated, contacts, distance) as compact inputs.
- Practical note: where datasets lack attention targets, sample plausible targets along the observed gaze ray — enables basic attention conditioning before hand-labelled data exists.

**Gate:** natural look-at onset/offset; no regression.

### M5 — Conditioning data factory + emotion/style (medium–large)

- **This is where the owner's dataset editing happens**: annotation tooling (clip scrubber/segmenter) for intent segments; emotion/style vectors (valence, arousal, confidence, curiosity, energy…) semi-automatic (heuristics + manual review); owner-edited labels for categories the base datasets lack.
- Emotion conditioning trained; the same intent under different emotion differs measurably and stays stable.

**Gate:** style modulation demonstrable; no regression.

### M6 — Semantic intent (medium)

- **Intent vocabulary = SORA's existing registered semantic actions** — one vocabulary, two consumers (Unity presentation and motion core).
- Conditioning: intent + intensity + progress; upstream hysteresis so intent does not flicker.

**Gate:** intent produces intent-appropriate dynamics; intent-to-intent transitions do not pop.

### M7 — Recurrent MoE (medium)

- Soft routing; **all experts updated every tick** (dormant-state fix); router stickiness (previous-α input or low-pass); supervised routing bootstrap → gradually relaxed; load-balance/entropy losses.
- Experts: general / locomotion / recovery / contact.
- Compare against the M1 control on every earlier gate plus a regime-switch test set.

**Gate:** ≥ M1 control on all metrics; healthy expert utilisation; smoother regime transitions. Shared-trunk vs independent experts stays an experiment, not a decision.

### M8 — SORA integration (medium; after research acceptance)

- ONNX → Unity at the runtime path decided by the M0 spike, behind the existing pose-ownership arbiter: **learned core = base layer; gaze/reach/grab/ragdoll = overrides.** `CognitiveMotionState` rides the existing presentation/state contract (schema bump), not a parallel channel.
- Root trajectory stays deterministic (existing CoordinateTransformer authority); learned root velocity optional.
- Optional early accrual (needs explicit owner go-ahead — small client change): log realised poses + semantic state from the current Unity client so fine-tune traces accumulate before integration.
- A/B in the real app against the procedural baseline.

**Gate:** frame budget held alongside llama.cpp + a game; no regressions in existing behaviour gates; trace fine-tune improves; owner acceptance.

## 5. Changes from the brief, and why

1. **M0 exists.** Frame conventions (parent-local ω, rest-relative rotations, realised-state ω) are the top silent-bug source in this kind of system; spec + tests precede model code.
2. **Canonical skeleton = VRM Humanoid bone set.** The project targets VRM via UniVRM; defining the canonical skeleton as the Humanoid set makes SMPL/AMASS retargeting standard and the Unity adapter near-free.
3. **Stability is the M1 gate.** Velocity-space prediction is known to help short-term behaviour and drift over long horizons (QuaterNet); input noise, burn-in and multi-step rollout are day-one ingredients, and ≥60 s rollouts are the acceptance test.
4. **Constraint losses as differentiable soft proxies** plus a Python reference layer with golden fixtures, so training and the future C# runtime constraint layer are conformance-tested rather than assumed equal.
5. **Reuse, don't duplicate**: one intent vocabulary (existing action registry), one state contract (schema bump), and the "explicit layers" model maps onto the existing pose-lease system; root motion stays with the existing coordinate authority.
6. **The runtime question is answered by evidence, not guessed.** The M0 spike decides Unity-Sentis vs fallbacks (ONNX Runtime plugin, or a hand-rolled GRU in C# — trivial at this size). The net stays a pure function `f(state, h) → (ω, h')` either way, so Python and Unity can conformance-test against each other.
7. **The data-editing need is a first-class deliverable** (M5 annotation factory), not an implied chore.
8. **Naturalness is the product**: the VRM viewer and owner judgement ship in M1; the procedural stack is the control condition in the M8 A/B. Gates are metric thresholds with recorded evidence — the repo's binary acceptance style does not transfer to learned behaviour.

## 6. Open items for the owner

1. Secondary project name and location (proposed `~/Desktop/motion-lab`); language — Python proposed.
2. Confirm base datasets (AMASS + LAFAN1) and licence acceptance; name any already held locally.
3. Training hardware: which GPU, and can training runs share it while the companion stack is idle?
4. Phase numbering in `SORA_IMPLEMENTATION_PLAN.md` once research is accepted (P16 is pencilled for the settings editor — motion core takes the next free slot; to confirm).

## 7. Next steps

1. Owner reviews this roadmap; adjust stages, gates or scope.
2. Fleshing out: task-level M0 plan in the secondary project (exact skeleton table, math API, repo skeleton, spike procedure).
3. Start: repo stand-up + M0 specs + spike; M1 data pipeline begins.
