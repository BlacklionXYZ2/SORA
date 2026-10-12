# Motion core roadmap rationalised; owner pronouns made neutral

Model name: **Opus 5.5**. Checkpoint **2026-10-11 21:30:00 +01:00**, Europe/London. Status:
**plan and documents only for the motion core; nothing implemented. A small wording fix in
SORA's prompts.**

The owner said: "Recent developments take precedence over older decisions. Could you rationalise
the roadmap and define each stage for me?" They then supplied a draft by Grok Bot and asked for a
comparison with what Opus 5.5 thinks the plan should be, then to continue. Earlier the same day,
the owner decided they will not build or train the motion core themselves, and won't wait until
after A Levels.

## Changes

- **New `docs/plans/MOTION-CORE-ROADMAP_2026-10-11.md`.** It keeps Grok's structure and the
  stage IDs M0 to M8. Main differences from Grok's draft:
  - intent is trained in M1 from BABEL and LAFAN1 labels;
  - M6 becomes SORA's own intents and conversation states;
  - M5 becomes emotion plus a "desktop data factory" for leaning on, sitting on and climbing
    onto windows, which no dataset has;
  - `MotionSignal` and trace logging move to right after V1, as the M8 prerequisite;
  - the audio fields are decided before the contract is built;
  - the desktop setting is a rule (rule 9);
  - dataset coverage and licences and the ROCm environment are checked facts.
- **Archive:**
  - the 28 September roadmap moved to `docs/plans/archive/` (wording unchanged);
  - Grok's draft added there as `MOTION-CORE-ROADMAP_2026-10-11_GROK-ORIGINAL.md`, with link
    paths adjusted only;
  - both listed in the archive README.
- **VISION.md:** the motion paragraph records that agents build and train the model, as the
  owner decided on 2026-10-11. Roadmap item 3 ("After A Levels") now reads "Started 2026-10-11",
  with integration after V1. The model's description is unchanged.
- **Other documents:**
  - V1.md scope row;
  - `docs/README.md` plans row;
  - the body self-awareness plan's link repointed;
  - a dated note in the motion interface design.
- **Not changed:** `~/Desktop/motion-lab` (the owner's folder). Its README and stage briefs
  still describe the 28 September plan, and making them point to the new roadmap waits for the
  owner's go-ahead.
- **Pronouns.** The owner has never stated pronouns. Grok's draft and some of Opus 5.5's earlier
  prompt text said "he/his", so these were made neutral:
  - the `remember` guidance in `contracts/companion_call.py`;
  - `REMEMBER_CHOICE_PROMPT` in `contracts/memory.py`, whose examples now say "The owner…";
  - the standing-instructions lines in `runtime/service.py` ("[HOW THE OWNER ASKED ME TO
    BEHAVE…]");
  - comments in `runtime/remember_turn.py`;
  - HOW_TO_USE's memory example;
  - the character template's example;
  - the matching test.

  The fabricated probe data, about a made-up person, is unchanged so its recorded results stay
  reproducible. `companion-call.schema.json` was re-exported.

## Verification

- **Checked 2026-10-11:**
  - the ROCm training environment (PyTorch 2.12.0 with ROCm 7.14; GPU visible);
  - LAFAN1's licence (CC BY-NC-ND 4.0), frame rate and categories, from its GitHub page;
  - BABEL's coverage and action labels, from its website;
  - BEAT2's listing (Apache-2.0; audio and text), from Hugging Face.
- **Tests and checks:** pytest 1138 passed, 26 skipped, 4 xfailed; ruff and strict mypy clean;
  contracts fresh.
- **Not run:** nothing of the motion core exists yet.
