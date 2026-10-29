# Memory layers: public datasets downloaded for bootstrap training

Model name: **Opus 5.5**. Checkpoint **2026-10-23 14:35:00 +01:00**, Europe/London. Status:
**downloaded and checked; not yet converted to labels, nothing trained**.

The owner: "Git ignore all the datasets because there is no reason for them to be in the project,
leave a note in the directory that says what datasets were used for what. Go ahead with the
downloads."

## Changes

- `.gitignore` ignores `training/memory/datasets/*`, except its `README.md`.
- `training/memory/datasets/README.md` lists each dataset with what it's used for, where it came
  from, and its licence.
- Downloaded into `training/memory/datasets/`, 783 MB in total:
  - PAWS;
  - Dialogue NLI;
  - Synthetic-Persona-Chat;
  - Multi-Session Chat v0.1;
  - LongMemEval (oracle and short versions; for testing only).

## Checks

- **Dialogue NLI:** its official Google Drive link now returns 404. The zip comes from a
  Hugging Face mirror, and its SHA-256 matches the checksum ParlAI publishes for the original.
- **PAWS:** Google's Cloud Storage links returned 403, so it comes from Google's own Hugging Face
  copy.
- **Every file opens as real data:**
  - LongMemEval: 500 questions in each version, 78 of them knowledge-update;
  - Synthetic-Persona-Chat: 8,938 training conversations;
  - PAWS: valid Parquet files;
  - MSC: the archive lists its persona summaries.

Nothing committed.
