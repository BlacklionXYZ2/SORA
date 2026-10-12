# Character, goals, self-memories and reflection

Prepared **2026-10-09**, Opus 5.5, from a planning conversation with the owner. Status:
**stage 1 implemented** (storage, tools, reflection, the character template); see the
[changelog](../../changelog/2026-10-09T130500+0100_SELF-MEMORIES-GOALS-REFLECTION_Opus-5.5.md).
Related: [MEMORY_MANAGER](MEMORY_MANAGER_2026-10-08.md),
[DECISION_LAYER](DECISION_LAYER_2026-10-08.md), and VISION.md, "Who she is".

## Owner decisions

- **Character:** a file written by the owner, read-only for SORA: `identity/character.md`.
- **Goals and ideas:** hers, changeable at will, but not a hand-edited text file; she works with
  them through tools.
- **Goals end rather than disappear.** A dropped or achieved goal keeps its start and end dates.
- **Dates:** goals and memories all carry creation and edit dates.
- **Progress notes:** in reflection she may record what she did towards her goals, drawn from
  memories.
- **Self-memories are not a separate category.** They are memories whose author is SORA.
- **Training:** staying true to her character in these choices needs training eventually.

## What exists (stage 1)

| Piece | Where | Notes |
|---|---|---|
| Memory dates | migration 13 (`created_at`, `updated_at` + triggers) | Every write path is dated by the database. Older rows are dated from their capture files at startup; with no capture they stay "date unknown" |
| Self-memories | `remember_thought` companion call → `runtime/self_memory.py` | An ordinary `memories` row with provenance "SORA's own thought…", plus a capture of the turn. Always offered, never narrowed away by the decision layer |
| Recall labels | `memory_label` | "Owner-stated memory (29 Sep 2026)" or "My own earlier thought (…), an opinion, not a fact about the owner" |
| Goals | `goals` + `goal_events` tables, `runtime/goals.py` | Active, achieved or dropped, with created, updated and closed dates and a reason. Full history (added, revised, progress with memory IDs, closed). At most 12 active; her changes are capped at 10 a day (the owner's are not). Events `goal.*` |
| Readable copy | `<state>/self/goals.md` | Regenerated after each change; edits there are not read back yet |
| Reflection | `runtime/reflection.py`, `SoraRuntime.reflect_now()` | Shows her character, active goals (`g1`…) and memories since the last reflection (`m1`…). Tools: `note_goal`, `add_goal`, `revise_goal`, `close_goal` and `remember_thought`. Invented references are refused. At most 8 steps, traced as `self.reflection` |
| Routes | `GET /api/v1/self/goals`, `POST /api/v1/self/reflect` | Owner-local only; `scripts/reflect.ps1` calls the latter |
| Character | `identity/character.md` (optional, loaded first); `identity/character.template.md` | Template sections: who she is, temperament, what she cares about, how she talks, interests, with you, boundaries |

## Why these shapes

- **References, not text:** she never retypes a goal or memory to name it, and cannot name one
  she wasn't shown.
- **Close with an outcome instead of "remove":** a small model handles "g2, dropped, because…"
  reliably, and the history keeps her continuity.
- **Goal tools only in reflection (for now):** one message can't knock her goals around. Her
  character and the evidence (memories) are in front of her when goals change.
- **Character stays the owner's:** no tool writes `identity/`. Her goals grow from it; she can't
  rewrite it.

## Next stages

1. **The owner writes `identity/character.md`** from the template. Until then she reflects with
   only the policy files as her "character".
2. **Scheduled reflection:** once a day when idle, or at shutdown (now: `scripts/reflect.ps1`).
3. **Goals in conversation:** show active goals briefly in her context, and the decision layer's
   "self" family. Decide whether conversation may add goals or only reflection.
4. **Goal-aware remembering** (the memory plan's keep decision): one question per goal, "does this
   matter to *\<goal\>*?", alongside "is this worth remembering about the owner?".
5. **Owner review:** a GUI view of goals, history and self-memories, with undo, lock and edit.
   Import edits made to `goals.md`.
6. **Training:** the owner's approvals and undos of her goal changes and self-memories train the
   decision layer, and later a LoRA for her reflective voice (see
   [TRAINING_LAYA](../runbooks/TRAINING_LAYA.md) for the method).
