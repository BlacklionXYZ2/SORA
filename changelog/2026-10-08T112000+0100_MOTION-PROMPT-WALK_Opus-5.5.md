# Motion prompt now lists walk, matching the motion schema

Model name: **Opus 5.5**. Checkpoint **2026-10-08 11:20:00 +01:00**, Europe/London. Status:
**implemented and component-tested.** The owner asked to fix the JSON schema, which "used to say
'wave' instead of 'walk'". This moves V1 acceptance step 5 (move and indicate) forward.

## Finding

The exported schemas were already correct:

- `motion-choice.schema.json` lists `none, wave, sit, lean, climb, stand, walk`.
- `companion-call.schema.json` lists poses for `pose` and `move.then`. Walking is the `move`
  call, not a pose.

The mismatch was in the prompt text sent with the schema. `MOTION_PROMPT`
(`src/sora/contracts/motion.py`) told the model to return
`{"motion":"none|wave|sit|lean|climb|stand"}`, without `walk`. That pushed a small model toward
another keyword, such as wave, for "come here".

## Changes

- `MOTION_PROMPT` now gives `{"motion":"none|wave|sit|lean|climb|stand|walk"}`.
- New test `test_motion_prompt_offers_every_keyword_the_schema_accepts`
  (`tests/providers/test_motion_dialogue.py`) builds the expected line from `MotionKeyword`, so
  the prompt cannot drift from the schema again.

## Verification

- **Fixture/component:** `tests/providers/test_motion_dialogue.py` gave 18 passed and 1 skipped
  (the opt-in real-model test). ruff is clean. `scripts/export-contracts.py` produced no schema
  change from this edit.
- **Not run:** the opt-in real-model motion test, and a live "come here" on the GUI.

HOW_TO_USE.md: no change to usage.
