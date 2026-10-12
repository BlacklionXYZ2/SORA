# Decision layer training: data format, general (description-based) training, export, evaluate, train, compile, guide

Model name: **Opus 5.5**. Checkpoint **2026-10-08 20:18:00 +01:00**, Europe/London. Status:
**pipeline implemented and proven end to end with a smoke run; no real training yet (by
recommendation).** The owner asked: "Does laya need to be trained now, or would it be better for
now to just refine the pipeline? Also could you start setting up training, leaving a guide so I
can learn how to do it." While this was running, the owner added: "general tool training would be
preferred so that an extension or plugin can just add tools to the json schema or add whole new
families and laya should still be able to accurately pick up on them."

## Recommendation given

- **Don't train yet.** There is no real data: shadow mode started today. Training on seed examples
  would teach my phrasing, and the smoke run shows small-data training makes Laya worse.
- **Collect shadow traces, review them, then train.**
- **Axolotl is for LoRA and full post-training of generative LLMs.** Laya is a 421M encoder with
  its own model class and loss, so it uses Laya's own trainer (`laya.train.finetune`). A full
  fine-tune fits the GPU.

## Changes

- **`src/sora/decision/dataset.py`:**
  - compact rows `{message, families, source}`, with sources owner, trace or seed;
  - a family **catalogue** (SORA's 7 plus `training/decision/extension_families.json`), with
    **held-out families** (calendar, smart_home) that are never trained on;
  - `laya_rows` for **general training**: each row asks about its own families plus random
    others, in random order, with randomly swapped yes/no letters;
  - `families_from_operations` for trace labels.
- **Decision trace:** `decision.families` now records the message (bounded, in the local
  database) so traces can become training data.
- **`training/decision/`** (in git):
  - `seed_train.jsonl` (123 rows);
  - `seed_eval.jsonl` (35);
  - `seed_eval_unseen.jsonl` (15, the held-out families);
  - `extension_families.json`.
- **`scripts/decision/`:**
  - `setup-training.ps1`: a venv over the owner's system ROCm torch plus `laya==0.4.1` and the
    ggmlc v0.9.7 cp312 wheel, both without dependencies; ggmlc's `compile_laya.py` and
    `laya_trunk.py` pinned at v0.9.7; and the base checkpoint;
  - `export_traces.py`: shadow-mode turns only, written to `.local/decision/data/` for review;
  - `evaluate.py`: recall, precision, complete and offered per threshold, through SORA's own
    runner client;
  - `train.py`: wraps `laya.train.finetune` with soft-ce, option shuffling and an eval file;
  - `compile.py`: ggmlc's compiler pointed at a local checkpoint.
- **Guide:** [docs/runbooks/TRAINING_LAYA.md](../docs/runbooks/TRAINING_LAYA.md) covers the
  concepts (encoder vs decoder, decision head, loss, gradients, learning rate, epochs and batches,
  freezing, LoRA/axolotl, generalisation and held-out families, splits and overfitting, reading
  the metrics, label trust) and then the step-by-step workflow.
- Links from HOW_TO_USE.md, the decision-layer plan and `docs/README.md`.

## Verification

- **Fixture/component:**
  - pytest: 1086 passed, 25 skipped, 4 xfailed;
  - ruff passes, mypy on src and tests passes (327 files), and `export-contracts --check` passes;
  - new `tests/decision/test_dataset.py` (seed sets valid and disjoint, held-out never trained,
    row expansion and letter swapping, trace labels in 7 cases, exporter pairing with a synthetic
    trace database). It caught a seed row I had reused between train and held-out eval, now
    fixed.
  - The scripts' remaining mypy messages are only "module not found", for packages that exist in
    the other environments.
  - `verify.ps1` itself was not run: `uv run` would reinstall into `.venv`, which the owner's
    running SORA holds.
- **Live, owner's GPU:**
  - the training environment reports torch 2.12.0+rocm7.14.0 on the RX 9070 XT;
  - the smoke run (`--freeze-encoder`, 1 epoch, 30 messages) trained on the GPU, compiled to a
    451 MB Q8_0 GGUF, and loaded and ran in SORA's Vulkan runner.
- **Native baselines at 0.25:**
  - `seed_eval`: 32/35 complete, recall 0.89;
  - held-out families: 14/15 complete, recall 0.93.

  The smoke model was **worse** on `seed_eval` (29/35) and overconfident: the expected effect of
  tiny data, documented in the guide as a lesson.
- **Not run:** a real fine-tune (no data yet), and `export_traces.py` on real traces (none exist
  yet; tested with a synthetic database).

HOW_TO_USE.md: updated.
