# Body self-awareness and the semantic observer

Prepared **2026-10-09**, Opus 5.5, from the owner's ChatGPT brief "SORA Embodied Semantic
Observer" and Opus 5.5's review of it. Status: **parked until after V1; nothing implemented.**
Revisit once the learned motion core ([MOTION-CORE-ROADMAP](MOTION-CORE-ROADMAP_2026-10-11.md),
stages M1 to M8) produces motion that Core did not name. Related: VISION.md, "Who she is";
[MOTION_INTERFACE_DESIGN](MOTION_INTERFACE_DESIGN_2026-10-05.md).

## The question

SORA should know what her body is doing ("I'm waving at you, about halfway through") and,
ideally, how she looks to the owner. The brief proposes a small learned **semantic observer**
that reads the rig state (and optionally the motion core's GRU hidden state) and outputs typed
labels: action, phase, per-limb intent, gaze, expression and posture.

## Why it waits

- **Today Core already knows.** Motion is commanded: she chooses `wave`, `walk`, `point` and so
  on, and Unity performs it procedurally. The action, its target and its progress are facts Core
  and Unity hold exactly. A learned observer would re-derive them with error. The brief agrees:
  "don't learn what the system already knows" (its §3A).
- **An observer needs a generative motion core.** Only when a learned core (audio, intent and
  emotion in, continuous motion out) produces movement no one labelled does "what is my arm
  doing?" become a real inference problem. Designing the observer before that core exists means
  designing against imagined data.
- **V1 has no step for it** (AGENTS.md: work that moves no acceptance step waits).

## Staged path

| Stage | What | Needs ML? | When |
|---|---|---|---|
| B1 | **Body-state line from known facts.** Unity reports the current action, phase (starting, ongoing, finishing), gaze target, expression and position; Core puts one line in her context, e.g. "I'm waving at you, about halfway through; looking at the Chat window." Also the stable typed interface every later stage fills. | No | Small; candidate V1.x item if the owner wants her to talk about what she's doing |
| B2 | **Rule-based geometric facts** from joint positions: "right hand above shoulder", "facing the left monitor", "leaning". | No | With B1 or when needed |
| B3 | **How she looks:** she captures her own avatar and looks with Gemma's vision ("how do I look right now?"). Appearance needs pixels; a small rig-only model can't judge "welcoming" or "awkward". | Uses the existing vision model | Any time; trigger rule to be designed |
| B4 | **Learned semantic observer** for motion the learned core generates. | Yes | After motion core M1, alongside M8 integration |

The B1 interface stays fixed; B4 only fills fields that B1 can no longer fill from commands.

## B4 design, when the motion core exists

**Baseline first.** An MLP (or 1D convolution) over a short window of hip-relative,
normalised joint features, with multi-task heads:
- softmax over action, including an explicit **"unclear/transition"** class;
- softmax per limb for intent;
- sigmoid for simultaneous attributes;
- regression for action progress.

Only if it falls short, try in order:
1. joint-level tokens with self-attention;
2. learned semantic query tokens;
3. a graph network.

Width 64 to 128 and two blocks are plenty. Even 128-wide is a few hundred thousand parameters,
well under 1 ms on CPU. Model size won't be the constraint; data diversity will.

**Inputs.** Rig state plus a short history window. The motion GRU's hidden state is an
optional, **read-only** extra input; the motion core's training is never changed for the
observer's sake. **Don't** feed the observer the motion core's intent or action metadata. With
them it learns to read the command back instead of interpreting the motion.

**The trap to test for.** The GRU hidden state also encodes the intent it was given, so "rig +
hidden state" can score well by echoing intent. Build a **disagreement set**: frames where intent
and actual motion differ (interrupted, blended, cancelled or physics-disturbed gestures). The
hidden state only counts as useful if it helps there.

**Data.** Generated from the motion core itself, labelled by its conditioning. Split by
**clip**, never by frame. Vary speed, mirroring, blends and interruptions, and add timing
noise on phase boundaries, since exact boundaries are arbitrary. Conditioning labels describe
what was *intended*, not what a person perceives; perceptual labels (B3 territory) need
separately labelled renders.

**Ablations, in order:**
1. rig only versus rig + hidden state versus rig + history;
2. concatenated versus feature-group versus joint tokens;
3. width 64 versus 128.

Activation choice (GELU or SiLU) only if there is evidence it matters.

## Success criteria for the first B4 experiment

- Action macro-F1 **≥ 0.85** on held-out clips.
- **≥ 0.70** on transition frames.
- Expected calibration error **< 0.05**; "unclear" is used rather than a confident wrong label.
- Beats rig-only on the disagreement set before the hidden state is kept as an input.
- CPU latency **< 2 ms** per update.
- **Behavioural check, the one that matters:** in paired conversations, she refers to and
  coordinates with her own body correctly more often *with* the body-state line than without.
  Run this check with B1 first, before training anything.

## Open questions for the owner

- Should B1 go in as a V1.x item now, or wait with the rest?
- For B3, when should she look at herself: on request only, or occasionally on her own
  (for example after a new outfit or pose)?
