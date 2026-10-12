# The remember tool, and memories that keep the turn's pictures and voice

Model name: **Opus 5.5**. Checkpoint **2026-10-10 01:00:00 +01:00**, Europe/London. Status:
**built, component-tested, checked live in an isolated profile; not yet tried with E4B on the
owner's SORA.**

The owner asked: "How does SORA decide to remember something? It should be a JSON tool that takes
a title and description and then creates the memory from those as well as all the turn data. I'm
open to other methods though if the one you've already made is better. Could you also set up the
pipeline for storing other modalities with memories?"

## What changed and why

- **Before:** after every reply, a separate call asked E4B "remember or none?" about the owner's
  message alone. The memory was the owner's raw words, and turns with attached images were
  never remembered.
- **Now, the `remember {title, description}` companion call** (owner's design, adopted):
  - she decides inside the turn, seeing the full context, and there is no extra call on turns
    worth nothing;
  - the description is a complete, recallable fact, and the title names it;
  - the owner's words are kept verbatim beside it, as the always-kept `words` part, so nothing
    the owner said is rewritten away;
  - the old yes/no call stays for brains without companion calls.
- **Turn entries** (`src/sora/memory/entries.py`): the turn's text, images and voice clip are
  stored with the memory under `<state>/memory/entries/<memory_id>/`, written atomically.
  Forgetting the memory deletes the folder.
- **The memory manager scores every part:**
  - words are always kept; the reply and read results go through text relevance;
  - images go through image relevance, and near-duplicates are dropped;
  - voice is kept;
  - verdicts go into the entry and the decision log, and media is never deleted by the manager;
  - the embedder loads its image/audio projector when installed;
  - recall searches text and media parts.

## Files

- **Contracts:** `contracts/companion_call.py` (`Remember` and its prompt text), and the
  re-exported `companion-call.schema.json`.
- **Read loop and decision layer:**
  - `runtime/read_turn.py`: `remember` offered with self-memory, non-terminal,
    `ReadTurn.remember`, plus the abilities text;
  - `decision/families.py` and `dataset.py`: always allowed, with no family.
- **New modules:** `runtime/remember_turn.py` and `memory/entries.py`.
- **`runtime/service.py`:**
  - `_remember_moment` and `memory_entries_root`;
  - the reply is captured before evidence notes are appended;
  - the old selector is skipped when the tool decides.
- **Persistence:** migration 15 (`memories.title`); `StoredMemory.title`;
  `add_memory(title=…)`, which only touches the column when a title is given, so older schemas
  still accept inserts; `memory_label` shows the title.
- **Manager, embedder and host:**
  - `memory/manager.py`: entry parts, verdicts, media recall;
  - `memory/embedder.py`: `modalities`;
  - `runtime/memory_host.py`: the projector when present, plus the entries root.
- **Forgetting:** `api/routes.py` deletes the entry when a memory is forgotten.
- **Privacy wording:** the listening help in `app_settings.py`, HOW_TO_USE (pictures and
  recordings are saved only with a remembered moment), and the panel test fixture text.
- **Docs:**
  - memory plan §10d;
  - HOW_TO_USE "How she remembers" and the memory manager VRAM; "Last updated" line;
  - verification addendum.
- **Tests:**
  - new `tests/memory/test_remember_tool.py`;
  - the fake embedder gained media;
  - schema version assertions updated to 15;
  - decision-layer allowed sets updated.

## Verification

- **Fixture/component:**
  - ruff clean;
  - strict mypy over `src` and `tests`;
  - contracts freshness check passes;
  - pytest 1129 passed, 26 skipped, 4 xfailed;
  - panel tests 33 passed.
- **Live model, isolated profile:**
  - a relevant screenshot was kept (0.688), an unrelated one dropped (0.627) and a generic
    reply dropped (0.759);
  - the voice clip was kept;
  - an image-only detail recalled the right memory.
- **Not run:**
  - E4B choosing `remember` on real turns;
  - C# tests (no C# change);
  - media display in the Memory window (not built).
