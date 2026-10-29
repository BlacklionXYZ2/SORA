# Memory layers: first training round on public-dataset labels

Model name: **Opus 5.5**. Checkpoint **2026-10-23 15:05:00 +01:00**, Europe/London. Status:
**trained and scored in an isolated QA folder; nothing adopted**.

The owner, after the datasets were downloaded: "Go ahead" (convert, train, test).

Evidence: [MEMORY_LAYERS_BOOTSTRAP_Opus-5.5_2026-10-23](../docs/verification/MEMORY_LAYERS_BOOTSTRAP_Opus-5.5_2026-10-23.md).

## Changes

- **`scripts/memory/convert_datasets.py`:** turns the datasets in `training/memory/datasets/`
  into bootstrap label files (weight 0.5, grouped for the held-out split). It also writes
  LongMemEval test files that are never trained on. It runs with `uv run --with pyarrow`, so
  pyarrow is not added to SORA's dependencies.
- **`scripts/memory/evaluate_layers.py`:** scores each layer's newest saved version against its
  fixed rule on test label files. Nothing is trained or activated.
- **`training/memory/labels/written/update_pairs.jsonl`:** 80 owner-style "same" and "updated"
  pairs. They're in a subfolder, so `train_layers.py` doesn't read them by default.
- **`docs/runbooks/TRAINING_MEMORY_LAYERS.md`:** a section on bootstrap examples.

## Result

No layer beat its fixed rule well enough to adopt:
- `same_subject` and `relevance` lose to their rules where it matters;
- `acceptance` and `update` are better than their rules, but not convincingly.

Details are in the evidence. The run's files are in `.local/memory-bootstrap-qa-2026-10-23/`, and
the owner's profile was only read.

Checks: ruff passes on both new scripts. They have no unit tests, and mypy's configured scope
doesn't include `scripts/memory/`.

Nothing committed.
