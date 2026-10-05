# Changelog

One file per change, written by the contributor who made it, in that contributor's own model
name. **Every change writes one:** code, configuration, schemas, scripts, or documentation that
changes status, structure or guidance. These files are **records**: never edit or rename another
contributor's entry. If something in one is wrong, write a new entry that says so.

## File name

```text
YYYY-MM-DDTHHMMSS+ZZZZ_<SCOPE>[-PROGRESS]_<Model-Name>.md
2026-10-04T134405+0100_GUI4-AUTOMATION-MANUAL-PROGRESS_GPT-6.1-Sol.md
```

- **Timestamp:** local Europe/London time, with its offset, when the checkpoint was reached.
- **Scope:** the plan or roadmap ID plus a short topic (`P05`, `P07-REPAIR`, `GUI3b-MEMORY-MANAGEMENT`,
  `W5-WINDOWS-VOICE-BRIDGE`, `DOCUMENTATION-RESTRUCTURE`). Add `-PROGRESS` when the stage is not
  closed by this entry.
- **Model name:** the model that did the work, with hyphens: `GPT-6.1-Sol`, `Gemini-3.8-Flash`,
  `Opus-5.5`.

## Contents

```markdown
# <What changed, in one line>

Model name: **<model>**. Checkpoint **YYYY-MM-DD HH:MM:SS +01:00**. Status: **<implemented /
in progress / documentation only>**, not stage completion unless the gate actually passed.

## Changes
- What changed and where (files, contracts, migrations).

## Verification
- Exact commands and results, each labelled fixture / component / native / live / hardware.
- Link the dated record in docs/verification/ when there is one.

## Limits and next
- What is not proven, what remains open and the next task.
```

State what you did *not* run as plainly as what passed. Link the living document you updated
(roadmap §4.0/§12 or plan §1/§5) and the matching verification record.

## Reading the history

The files sort chronologically. `P00`–`P15` entries cover the core runtime (2026-09-07 → 09-23),
`W1`–`W6` the vision-alignment slices (2026-10-01 → 10-03), and `GUI0`–`GUI4` the current GUI
roadmap (2026-10-03 onward). For which Gemini 3.8 Flash entries have been independently
verified, see the [verification ledger](../docs/verification/README.md#independent-verification-ledger).
