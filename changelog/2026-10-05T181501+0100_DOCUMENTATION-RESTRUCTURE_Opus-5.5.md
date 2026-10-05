# Documentation restructure for maintainability

Model name: **Opus 5.5**. Checkpoint **2026-10-05 18:15:01 +01:00**, Europe/London. Status:
**documentation only**. No product code, configuration, schema, test, stage status, checkbox,
completion timestamp, evidence figure or attribution was changed. No file was deleted.

## Changes

**Living documents now state the current position once; dated history moved out verbatim.**

- `SORA_GUI_IMPLEMENTATION_ROADMAP.md` → v1.33 (about 200 KB → 88 KB). The dated checkpoints
  §4.3–§4.33 moved to `docs/gui/ROADMAP_CHECKPOINTS.md`, keeping their original section numbers
  so existing "§4.n" references resolve. The §15 revision history v1.0–v1.32 moved to
  `docs/gui/ROADMAP_REVISION_HISTORY.md`. Added the **§4.0 current-status table**, compiled from
  §4.26–§4.33 and §12 without changing any status, and a rule in §1 to update §4.0 in place and
  append future checkpoints to the log.
- `SORA_IMPLEMENTATION_PLAN.md`: added a "Start here" banner pointing to the GUI roadmap and
  listing the plan's remaining open items (P15.2, P15.7, P15.8 follow-up, P15.9–P15.12). The §11
  "Dated progress" list and the trailing "Local frontend alignment progress" section moved to
  `docs/history/IMPLEMENTATION_PLAN_PROGRESS_LOG.md`.
- `README.md` rewritten as a short front page: what SORA is, current state, quick start, layout
  and a documentation map. The previous phase-by-phase README is preserved in full at
  `docs/history/README_PHASE_HISTORY_2026-10-03.md`.
- Seven historical plan snapshots and updates moved from the repository root to
  `docs/plans/archive/`. The tracked handoff file was moved with `git mv`, so git shows a rename.
  The old→new path table is in `docs/plans/archive/README.md`.
- New guides: `AGENTS.md` (contributor rules for every model), `CLAUDE.md` (imports AGENTS.md),
  `docs/README.md` (documentation map with living/record/history roles), `changelog/README.md`
  (naming and contents) and `docs/verification/README.md` (evidence labels and the
  **independent-verification ledger for Gemini 3.8 Flash work**).

**Links.** Relative link paths in moved text were adjusted for the new folders. 25 links were
already broken before this change: they pointed to `…_GPT-6-Astra.md` changelogs whose files are
named `…_GPT-6.1-Sol.md`. These were repointed to the existing files, and 14 links inside the
archived files and one in `changelog/2026-09-09T182545+0100_P09_GPT-6-Astra.md` were repaired the
same way. No other contributor's wording was edited.

## Verification

- **Moves are verbatim.** A script compared each moved block with the original files, ignoring
  only the link-prefix change: all four blocks matched. Every non-blank line of the original plan
  and roadmap is present in the new living document or its history file (0 missing).
- **Links:** relative Markdown links across the repository, excluding `.local/` and `.venv/`,
  went from 25 broken before to **0 broken** after.
- **Fresh regression on the unchanged source**, before any documentation edit:
  `uv run --locked pytest` 904 passed / 25 opt-in skipped in 111.90 s; `ruff check src tests`
  clean; `mypy` strict clean (284 source files). C#, PWA, native, live-model and hardware checks
  were **not** run.

## Limits and next

- The ledger records that **P03A** (capability resolver scope containment, attention, desktop
  objects, social boundary, companion UX) has **no independent verification**, and that **P06**
  (Antigravity adapter, routing, privacy filtering, fallback) is only partially verified. Neither
  was audited in this change.
- Owner decision needed: ten W1–W6 changelogs (2026-10-02/03) are named `GPT-6.1-Sol` but their
  text and the plan credit GPT-6 Astra or "GPT-6.1 Astra". Nothing was renamed.
- Most of the remaining plan size is the completed P00–P15 checklist (§5). It was left in place
  because it is still the plan's authoritative checklist.
