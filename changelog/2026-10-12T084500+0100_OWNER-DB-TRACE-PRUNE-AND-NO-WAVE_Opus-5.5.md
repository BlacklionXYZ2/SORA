# The owner's database shrunk from 934 MB to 26 MB; the docs no longer promise a wave

Model name: **Opus 5.5**. Checkpoint **2026-10-12 08:45:00 +01:00**, Europe/London. Status:
**done** (the owner's data, with their approval; documentation).

Follows [the Alice change](2026-10-12T080000+0100_AVATAR-ALICE-DEFAULT_Opus-5.5.md), which
offered two things. The owner answered: "1. Go ahead 2. There is no wave, initially walk was
documented as wave for some reason so you're probably just seeing remnants of that."

## Changes

**The permission-check flood in the owner's database** (`.local\manual-test\data\sora.db`):

- **Done with SORA closed.** No SORA, Core, player or app processes were running.
- **The backup was taken first,** with SQLite's online backup, to
  `.local\manual-test\backups\sora-2026-10-12-before-trace-prune.db`:
  - 933,855,232 bytes, SHA-256 `52f29abb…`;
  - quick check ok, and every row count matches the original.

  It is the owner's to keep or delete.
- **Deleted:** the 2,154,370 `operation.owner_policy` traces (2026-10-04 20:24 to 2026-10-09
  20:46 UTC), the flood fixed in Core by the earlier change. The other 136 traces were kept,
  and so was everything else: 150 messages, 4 memories, 30,817 events and 13 tasks.
- **Compacted:** `VACUUM`, then a WAL checkpoint. The file went from 890.6 MiB to 24.6 MiB
  (25,829,376 bytes). `PRAGMA integrity_check` is ok.
- **Migrations untouched.** The database is still at 13 migrations; SORA upgrades it as usual
  the next time it starts.

**No wave:**

- **The owner confirmed she has no wave.** The arm-forward "waving" pose seen in the Alice
  check is a leftover from early work, so the earlier change's offer to "fix the wave" is
  withdrawn.
- **[HOW_TO_USE.md](../HOW_TO_USE.md):**
  - no longer says she waves on request;
  - the pose list drops "wave" and says asking her to wave only moves one arm forward;
  - the arrival example now sits.
- **[V1.md](../V1.md) step 5** asks her to sit, and to run to the other side and sit, instead of
  waving. It is otherwise unchanged. Earlier status rows that record the "wave" keyword are left
  as written.

## Verification

- **Owner data:**
  - before: the row counts from the backup's report;
  - after: the counts above, and `PRAGMA integrity_check` ok.

  SORA itself hasn't been started on the pruned database.
- **Docs:** CRLF line endings were preserved in both files.

## Limits and next

- **The code still offers the model a "wave" pose** (`contracts/motion.py`,
  `contracts/companion_call.py`, `runtime/move_intent.py`, the Unity "waving" profile). So "wave
  to me" still produces the leftover arm pose. Removing it changes a public contract and the
  player, so that is left to the owner.
- **The events and outbox tables hold 30,817 rows each.** Their contents were not inspected:
  reading further into the owner's data wasn't part of the approval.

HOW_TO_USE.md: updated.
