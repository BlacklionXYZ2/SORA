# Motion core: how the model's size is set, and when experts are built

Model name: **Opus 5.5**. Checkpoint **2026-10-11 22:30:00 +01:00**, Europe/London. Status:
**plan only; nothing implemented.**

The owner asked how the model's size is defined and whether a mixture of experts is worth
pursuing ("I think it might be worth considering after core v1 is trained"), then said: "write
it into the roadmap".

## Changes to `docs/plans/MOTION-CORE-ROADMAP_2026-10-11.md`

- **Rule 8:** the size is set by the M1 sizing sweep (owner decision, 2026-10-11).
- **M1, new "Model size" section:**
  - why runtime isn't the limit at this scale (about 0.4M multiply-adds per tick for 1×256)
    while data is (about 10M highly correlated frames);
  - the sweep: widths 128, 256 and 512, with one and two layers;
  - the rule: adopt the smallest model within noise of the best on every gate metric (proposed
    within 5%), with 10× headroom under the spike's measured budget; the expected range is 256
    to 512 units;
  - growing it later only on evidence of too little capacity.
- **M1 gate:** adds the **per-skill report** (gate metrics broken down by movement type).
- **M7:** a new "When it is built" section:
  - considered only after core v1 is trained;
  - a decision point at the M1 per-skill report, repeated after M5 and M6;
  - cheap fixes first (the next model size, oversampling the lagging skill, stronger intent
    conditioning);
  - built only if a skill still fails while the common ones pass; otherwise skipped, with the
    decision recorded;
  - its costs listed.
- **§6 defaults 3 and 4** marked as decided on 2026-10-11.

## Verification

Documentation only; no tests run for this change.
