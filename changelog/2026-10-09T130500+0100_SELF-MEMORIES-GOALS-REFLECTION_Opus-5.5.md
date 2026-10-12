# Self-memories, dated memories, SORA's goals with history, reflection, and a character template

Model name: **Opus 5.5**. Checkpoint **2026-10-09 13:05:00 +01:00**, Europe/London. Status:
**implemented and component-tested.** Not run with the live model, and not run on the owner's
running SORA (its database migrates on its next start).

The owner asked: "Could you set up the path for self-memories? They shouldn't be categorised
separately … Then move on to refining the character and goals." They added: "goals and memories
should all be tagged with initialisation and edit dates. If she drops a goal, there should be a
start and end date attached. Also she (maybe) might be able to add information about things she
did towards her goals in reflection from memories."

## Changes

- **Migration 13:**
  - `memories.created_at` and `updated_at`, with triggers that date every insert and every
    content, supersede or delete change, on all write paths;
  - new `goals` and `goal_events` tables.

  Existing memories are dated at startup from their capture files (`capture_dates`, before
  compaction can prune them). On a copy of the owner's database, all 4 memories were dated
  29 September 2026.
- **Self-memories:**
  - a new companion call `remember_thought` (her words, 3–300 characters, one per turn, stored
    after the reply);
  - `runtime/self_memory.py`: an ordinary memory row with provenance "SORA's own thought…" plus a
    capture of the turn;
  - always offered, including under the decision layer's enforce mode. It is not tied to the
    Memory panel.
- **Recall labels:** every recalled memory is shown with whose it is and its date ("Owner-stated
  memory (29 Sep 2026)" or "My own earlier thought (…), an opinion, not a fact about the owner").
- **Goals** (`runtime/goals.py`):
  - add, revise, close (achieved or dropped, with a reason) and progress notes linked to memory
    IDs;
  - created, updated and closed dates, and full history in `goal_events` (also logged as `goal.*`
    events);
  - at most 12 active goals; her changes are capped at 10 a day, the owner's are not;
  - `<state>/self/goals.md` is regenerated after each change.
- **Reflection** (`runtime/reflection.py`, `SoraRuntime.reflect_now`):
  - she sees her character, her active goals (`g1`…) and the memories since her last reflection
    (`m1`…);
  - tools: `note_goal`, `add_goal`, `revise_goal`, `close_goal` and `remember_thought`;
  - invented references are refused; at most 8 steps; traced as `self.reflection`.
  - New contracts `AddGoal`, `ReviseGoal`, `CloseGoal`, `NoteGoal` and `RememberThought`; the
    `companion-call` schema was exported.
- **Routes** (`api/self_routes.py`, owner-local only): `GET /api/v1/self/goals` and
  `POST /api/v1/self/reflect`. `scripts/reflect.ps1` triggers a reflection and prints the result.
- **Character:**
  - `identity/character.md` is optional and loaded first; no tool writes `identity/`;
  - `identity/character.template.md` gives the owner a structure (who she is, temperament, what
    she cares about, how she talks, her interests, with you, boundaries). The template itself is
    never loaded.
- New plan [CHARACTER_AND_GOALS_2026-10-09](../docs/plans/CHARACTER_AND_GOALS_2026-10-09.md);
  HOW_TO_USE gains "Her character, goals and memories".

## Verification

- **Fixture/component:** pytest gave 1093 passed, 25 skipped, 4 xfailed; ruff and mypy pass on
  src and tests (336 files); the schemas are exported. New tests:
  - `test_memory_dates` (triggers on insert, correct and delete);
  - `test_self_memory` (stored as an ordinary memory by her, dated, with a capture, labelled on
    recall; labels);
  - `test_goals` (lifecycle, dates, history, the markdown copy, limits);
  - `test_reflection` (progress from memories, a new goal, a thought, two invented references
    refused, the next reflection seeing only newer memories);
  - `test_character_file`.
- **Live:** none. The owner's database migration and backfill were checked on a copy only.
- `verify.ps1` was not run in full (the owner's SORA holds `.venv`); each step was run with
  `--no-sync` except the PWA step.

HOW_TO_USE.md: updated.
