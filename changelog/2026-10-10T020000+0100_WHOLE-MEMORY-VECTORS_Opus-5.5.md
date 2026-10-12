# Whole-memory vectors for similarity and the map; irrelevant media deleted

Model name: **Opus 5.5**. Checkpoint **2026-10-10 02:00:00 +01:00**, Europe/London. Status:
**built, component-tested, checked live in an isolated profile.**

The owner confirmed the plan: one vector for the whole memory, used to find similar memories
and to place the memory on the map (a numerical high-level summary). Component vectors are for
relevance within the memory. An irrelevant image or audio clip isn't stored. Until now only
part vectors existed, memory-to-memory similarity used the description alone, voice was always
kept, and dropped images stayed on disk.

## Changes

- **`memory/manager.py`:**
  - processing order is now: parts and their relevance first, then the **whole** vector (one
    interleaved embedding of the description plus every kept part and medium, similarity
    form), then links and acceptance from the whole vectors;
  - irrelevant images and recordings are **deleted** from the entry and removed from its media
    list. Media the embedder can't judge yet is kept;
  - voice is now relevance-checked (≥ 0.68), and recall uses that floor for voice parts;
  - new `map_coordinates(dims)`: PCA of the whole vectors;
  - memories without a `whole` vector are processed again in the background. The
    `similarity` part is no longer written.
- **`memory/embedder.py`:** `embed_mixed(text, role, media)` on the `Embedder` slot.
- **`memory/features.py`:** `audio_relevance = 0.68`, calibrated live (14 clips: 0.692+ vs
  0.664 or less).
- **`memory/training.py`:** correction pairs use the stored `whole` vectors.
- **Tests:**
  - the fake embedder gained `embed_mixed`;
  - assertions for map coordinates, the `whole` part, and deleted near-duplicate image files.
- **Docs:**
  - memory plan §10e;
  - HOW_TO_USE (unrelated pictures and recordings are deleted rather than kept);
  - verification addendum.

## Verification

- **Fixture/component:** ruff clean; strict mypy over `src` and `tests`; pytest 1129 passed,
  26 skipped, 4 xfailed.
- **Live model, isolated profile:**
  - the unrelated screenshot (0.627) and voice clip (0.595) were deleted from disk;
  - whole vectors and map positions were produced;
  - recall was unchanged.
- **Not run:**
  - recalibrating the linking thresholds on whole vectors that include media;
  - the owner's SORA.
