# Memory plan step 1: EmbeddingGemma 2 probed on the owner's machine (text, image, audio)

Model name: **Opus 5.5**. Checkpoint **2026-10-09 08:20:00 +01:00**, Europe/London. Status:
**probe built and run; nothing in SORA changed.** The owner asked: "should we work on the memory
system? Would it be more wise to set up some tests for EmbeddingGemma actually to confirm how it
works … download the Q4_K_XL".

## Changes

- New `scripts/memory/probe_embedder.py`. It starts llama-server with the embedder and measures:
  - text recall (with and without task prefixes, at 768, 512 and 256 dims);
  - the relation bands;
  - image↔caption matching;
  - spoken→written memory matching;
  - speed.

  It writes a JSON report to `.local/memory-probe/`.
- New `training/memory/embedder_probe.json`: 30 memories (4 are the owner's real ones), 30
  reworded questions, 19 labelled pairs, 9 captioned images and 6 spoken memories.
- Downloaded, with SHA-256 checks:
  - `embeddinggemma-2-UD-Q4_K_XL.gguf` and `mmproj-Q8_0.gguf` to
    `.local/models/embeddinggemma-2/`;
  - llama.cpp nightly b11516 (Windows Vulkan) to `.local/llama.cpp-b11516/`. The owner's
    `C:\llama.cpp` is too old for this model and was not changed.
- Evidence: [MEMORY_EMBEDDER_PROBE_Opus-5.5_2026-10-09](../docs/verification/MEMORY_EMBEDDER_PROBE_Opus-5.5_2026-10-09.md).
  The plan gains §10a with the design consequences.

## Verification

- **Live, owner's GPU (Vulkan), one run:**
  - text recall 30/30 at rank 1 at every size;
  - spoken→written 6/6;
  - caption→image 8/9 (9/9 in the top 3);
  - speed: text 29 ms, audio 23 ms, image 387 ms.
  - GPU and CPU gave identical results, with no NaNs.
- **Key finding:** same-fact (0.894–0.979) and updated-fact (0.882–0.946) similarities overlap, so
  superseding cannot be decided by similarity alone. Related and unrelated separate narrowly
  around 0.75–0.77.
- **Not run:**
  - pytest (no SORA code changed);
  - a harder set with hundreds of real memories;
  - other quantisations;
  - a GPU memory measurement.

HOW_TO_USE.md: no change to usage.
