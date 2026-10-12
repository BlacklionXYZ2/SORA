# Body self-awareness plan (parked until the motion core)

Model name: **Opus 5.5**. Checkpoint **2026-10-09 15:00:00 +01:00**, Europe/London. Status:
**plan only; no SORA code changed.** The owner asked to keep the review of the ChatGPT brief
"SORA Embodied Semantic Observer" in the plans for when the motion core is built.

## Changes

- New `docs/plans/BODY_SELF_AWARENESS_2026-10-09.md`:
  - why a learned observer waits (motion is commanded today, so Core already knows the action);
  - stages B1 to B4: a body-state line from known facts, rule-based geometry, looking at herself
    with the vision model, then the learned observer after motion core M1;
  - the B4 baseline, inputs, the intent-echo trap with its disagreement set, data and ablations;
  - measurable success criteria and the owner's open questions.
- `docs/README.md`: plans row links the new plan and the character-and-goals plan.

## Verification

Documentation only; no tests run for this change. Moves no V1 acceptance step (post-V1 work).
