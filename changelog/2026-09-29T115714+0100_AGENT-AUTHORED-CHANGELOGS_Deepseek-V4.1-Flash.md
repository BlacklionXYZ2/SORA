# Agent-authored changelogs — correcting who writes the entry

- Written: **2026-09-29 11:57 +01:00 (Europe/London)**
- Author: **Deepseek V4.1 Flash**
- Repo: `C:\Users\oscar\Desktop\SORA` — working tree, **nothing staged or committed** (`git log` still ends at `89f005f`)
- Supersedes the changelog-ownership half of
  `changelog/2026-09-29T113228+0100_MEMORY-CHOICE-AND-AGENT-WRITE-AUTHORITY_Deepseek-V4.1-Flash.md`
  (that entry now carries an amendment note pointing here)

## 1. What the owner said

> "The core does not write the changelog, the agent does. Again because the agents are of much higher
> reliability and capability than the 2B class core."

## 2. What was wrong with the version built earlier today

The morning build had **Core write the entry file** from an agent-supplied one-or-two-sentence
`changelog_note`, with two labelled provenance classes (*agent-authored* / *Core-derived*). Three
problems with that:

1. **Wrong author.** The agent did the work and carries the context; Core can only re-format the fields
   it was handed. A 2B-class core summarising a capable agent's work is a downgrade, not a record.
2. **Wrong incentive.** Because Core would fill the gaps, an agent could supply a thin note and still
   get a tidy entry — the note was not actually load-bearing.
3. **Two provenance classes were a symptom.** "Core-derived" only existed to describe a substitute for
   the thing that should have been written in the first place.

## 3. What changed

The rule now: **the agent authors its own entry; Core verifies and records, and invents nothing.**

| Layer | Before | Now |
|---|---|---|
| Result contract | `changelog_note` (a short note) | `changelog_path` (the entry the agent wrote) + `changelog_entry` (entry text for read-only runs) |
| Prompt | asked for a note | carries `CHANGELOG_INSTRUCTION`: write `changelog/<UTC timestamp>_<SLUG>_<YOUR-NAME>.md` in your working directory — what changed, why, which files, how it was checked — and return its path |
| Core | composed and wrote the file, two provenance classes | verifies the claimed file **inside the agent's working root and under `changelog/`**, hashes it, records a trace; or stores returned text **verbatim** with a provenance comment |
| Missing entry | Core-derived substitute written | `changelog.missing` trace + `changelog_missing` task-update token; **no substitute** |

Files:

| File | Change |
|---|---|
| `src/sora/contracts/changelog.py` | **new** — `CHANGELOG_DIRECTORY`, `CHANGELOG_INSTRUCTION` (one definition, carried by every agent prompt) |
| `src/sora/contracts/models.py` | `changelog_note` → `changelog_path` + `changelog_entry` on `NormalizedResult` |
| `src/sora/providers/hermes.py`, `codex.py` | prompts carry `CHANGELOG_INSTRUCTION`; parsers read the two new fields |
| `src/sora/runtime/agent_changelog.py` | **rewritten** — `VerifiedChangelog`, `verify_agent_changelog` (path/type/size/emptiness checks, sha256), `store_agent_entry` (verbatim storage). `render_agent_changelog` / `write_agent_changelog` deleted |
| `src/sora/runtime/service.py` | `_write_agent_changelog` replaced by `_record_agent_changelog` + `_agent_working_root`; traces `changelog.verified` / `changelog.stored` / `changelog.missing`; every accepted result now carries a `changelog:<path>` or `changelog_missing` task-update token |
| `tests/runtime/test_agent_changelog.py` | **new** — 8 tests on the pure functions (verification, traversal, absolutes, non-markdown, empty, oversize, verbatim storage) |
| `tests/runtime/test_agent_sessions_and_changelogs.py` | 3 old note-based tests replaced by 6: verified entry, missing entry, path escape refusal, nothing-at-all, read-only text stored verbatim, configurable root |
| `docs/plans/MEMORY-CHOICE-AND-AGENT-CHANGELOGS_2026-09-29.md` | §5.1–§5.4 rewritten for agent authorship; two risk rows updated |

What deliberately did **not** change: the path checks (working root + `changelog/` + `.md` + non-empty).
They are not provider distrust — the owner's trust in reputable providers is accepted — they are the
house rule that *a reported path is a claim, not evidence*, the same rule that stops Core reporting
success it has not seen.

## 4. Verification

- `pytest -q` → **461 passed, 13 skipped in 59.05 s** (was 450/13: −3 removed note-based tests, +14 new;
  all 13 skips remain the opt-in live fixtures)
- `ruff check src/sora tests` → clean
- `mypy src` (strict) → *Success: no issues found in 116 source files* (was 115; +`contracts/changelog.py`)
- `grep` confirms no reference to `changelog_note`, `write_agent_changelog` or `render_agent_changelog`
  survives anywhere in `src/` or `tests/`
- Nothing was run against the live Core; no agent CLI was invoked for this change

## 5. Owner-facing behaviour and the honest remainder

- A run whose agent wrote an entry: task update token `changelog:changelog/2026-..._..._CODEX.md`, with
  the path relative to the agent's working directory, plus a `changelog.verified` trace carrying sha256
  and size.
- A run whose agent could not write files: the agent's words stored untouched under
  `<state-root>/changelog/agents/` with a comment saying where they came from. This is the one case
  where Core writes a file, and it writes the agent's text, not its own. If the owner wants even that
  excluded, deleting `_record_agent_changelog`'s second branch is a two-line change.
- **Still open:** the `antigravity` adapter does not parse structured result fields, so its runs will
  report `changelog_missing` until that adapter is taught to return `changelog_entry`; and the
  `artifacts` table has no `task_id`/`run_id` column, so verification evidence is a trace rather than a
  first-class artifact row (unchanged from this morning's note).
