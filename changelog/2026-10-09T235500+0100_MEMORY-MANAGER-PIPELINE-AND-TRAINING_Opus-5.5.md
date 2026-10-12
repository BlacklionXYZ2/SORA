# Memory manager: EmbeddingGemma use cases, pipeline and training program

Model name: **Opus 5.5**. Checkpoint **2026-10-09 23:55:00 +01:00**, Europe/London. Status:
**built, probed live, component-tested; nothing trained on the owner's data; shadow by default.**

The owner asked: "Could we work on the memory system? Could you test the cases for which
embeddingGemma would be used and then set up the pipeline and training program? Don't train it
yet, but put everything in place to train it when I say (or have found the data to train it)."
This is post-V1 work done at the owner's request (VISION.md places deeper memory management
after V1). It moves no V1 acceptance step. In shadow mode her replies are unchanged, so step 9
behaves as before.

## Changes

- **Use-case probe:**
  - new `scripts/memory/probe_use_cases.py` and `training/memory/use_case_probe.json`;
  - eleven uses (U1–U11) through Core's own embedder and feature code;
  - evidence in `docs/verification/MEMORY_USE_CASES_Opus-5.5_2026-10-09.md`.
- **Core modules** (new, in `src/sora/memory/`):
  - `vectors.py`: standard-library vector maths (`math.sumprod`), float32 BLOBs and PCA, so
    Core needs no numpy;
  - `embedder.py`: the `Embedder` slot and `LlamaEmbedder` (EmbeddingGemma 2 on its own
    llama.cpp b11516 server, API key, task prefixes, text-only unless media is needed). It
    records its process for Quit;
  - `settings.py`: the `memory` settings section;
  - `features.py`: features for the four layers, and fixed thresholds calibrated on the probe;
  - `layers.py`: versioned logistic layers with an `active.json` pointer and rollback;
  - `store.py`: vectors, links and recalls;
  - `manager.py`: embed, compare, link, accept, reply relevance, decision log and recall;
  - `training.py`: owner, file and fabricated examples, held-out scoring against the fixed
    rule, adopt-only-if-better, export for labelling, reports;
  - `authors.py`: `OWN_THOUGHT` moved here to avoid an import cycle;
    `runtime/self_memory.py` re-exports it.
- **Core wiring:**
  - new `src/sora/runtime/memory_host.py` follows Settings live, runs the manager in the
    background after each remembered moment and at owner launch, and chooses the memories for
    a turn: shadow records, on uses meaning first then recency;
  - `service.py`: the host, `_memory_trace`, `start_memory_manager`, a nudge after each turn's
    remembering, and `select` in `_direct_dialogue_context` with the turn's correlation ID;
  - `__main__.py`: the host starts on owner launches only.
- **Migration 14:** `memory_vectors`, `memory_links`, `memory_recalls`. Three schema-version
  test assertions were updated from 13 to 14.
- **Settings:**
  - Settings → Memory → **Memory manager**: mode (shadow default, on, off), device, server and
    model path;
  - the category test now expects the four Memory keys (144 fields);
  - `app-settings.schema.json` re-exported.
- **Quit:** `HelperCleanup.cs` also stops the recorded `embedder` (a `llama-server`).
- **Scripts:**
  - `scripts/setup-memory-embedder.ps1` (checked downloads, `-WithMedia` for the projector);
  - `scripts/memory/train_layers.py` (checks by default; `--train`, `--adopt`, `--list`,
    `--rollback`, `--export-unlabelled`);
  - `scripts/memory/make_fabricated_labels.py`, which wrote
    `training/memory/labels/fabricated/probe_labels.jsonl` (103 rows; used only with
    `--include-fabricated`).
- **Docs:**
  - `docs/runbooks/TRAINING_MEMORY_LAYERS.md` (new);
  - memory plan status line and §10c;
  - `docs/README.md` runbooks row;
  - HOW_TO_USE.md: a memory manager paragraph, the "Not built yet" list (the decision layer
    was built on 2026-10-08, so it was removed from the list) and the "Last updated" line.
- **Tests:** `tests/memory/test_memory_manager.py`, 7 tests with a deterministic fake embedder.

## Verification

- **Live model (fabricated data, one run each):**
  - recall by meaning found 30/30 at rank 1, against 10/30 for today's recency recall;
  - thresholds re-calibrated: recall floor 0.74, reply relevance 0.79, same subject 0.85;
  - the trained same_subject layer beat its rule (1.00 vs 0.88, leave-one-out), while the
    update rule beat its trained layer (0.91 vs 0.83);
  - full results are in the verification file.
- **Pipeline, live, isolated profile** (`.local/memory-pipeline-qa-2026-10-09/`):
  - 32 memories processed in 3.0 s;
  - the update pair was linked correctly;
  - `on` recall took 19–26 ms with the right memory first;
  - shadow left her context unchanged;
  - the embedder stopped on close.
- **Training program:**
  - check mode on the owner's profile, read-only: 0 examples;
  - a full `--train --adopt` on an isolated profile with fabricated labels worked: two layers
    adopted, two kept as candidates. Held-out sets were tiny.
- **Fixture/component:**
  - ruff clean;
  - strict mypy over `src`, `tests` and the export script;
  - contracts freshness check passes;
  - pytest 1126 passed, 26 skipped, 4 xfailed;
  - C# 407 passed;
  - desktop shell built with 0 warnings and 0 errors (into `.local/quit-qa-2026-10-09/build`).
- **Not run:**
  - the owner's SORA with the manager (it starts at the next owner launch, after migration
    14);
  - images and audio as parts (pending entries, plan step 2, don't exist yet);
  - training on owner labels;
  - EmbeddingGemma fine-tuning.
