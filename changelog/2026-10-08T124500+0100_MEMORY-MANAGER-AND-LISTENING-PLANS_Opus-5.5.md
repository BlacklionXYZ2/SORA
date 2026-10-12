# Plans: memory manager (multimodal memories, trained keeper, network) and always-on listening

Model name: **Opus 5.5**. Checkpoint **2026-10-08 12:45:00 +01:00**, Europe/London. Status:
**documentation only**: two new plans, nothing implemented. Both are scheduled after the V1
acceptance run.

## Changes

- New [docs/plans/MEMORY_MANAGER_2026-10-08.md](../docs/plans/MEMORY_MANAGER_2026-10-08.md):
  - pending entries holding the whole turn with images and audio, plus a provisional memory;
  - an idle-time manager that embeds every part with EmbeddingGemma 2, then accepts the memory,
    chooses parts (abstracting, never rewriting the owner's words), stores it and links it;
  - three small trained layers, with labels from Memory window corrections and recall use, and a
    training script with reports;
  - stored vectors with all-against-all comparison, a 2D/3D map (PCA, UMAP optional) and fixed
    nodes for apps, agents and projects;
  - a recall-strength forgetting score;
  - JPEG and Opus media;
  - swappable model slots;
  - the owner's EmbeddingGemma 2 test as step one.
- New [docs/plans/ALWAYS_ON_LISTENING_2026-10-08.md](../docs/plans/ALWAYS_ON_LISTENING_2026-10-08.md):
  - the chain: echo cancellation → voice activity detection → rolling RAM buffer → addressed to
    SORA? (wake word, then a follow-on window, then a System-1 addressee classifier);
  - **native audio for Gemma 4 E2B/E4B**, which bypasses speech-to-text through an `audio_input`
    capability flag. Speech-to-text remains for brains without audio and, off the critical path,
    for transcripts;
  - verification of llama.cpp and projector audio support comes first.
- `docs/README.md` lists both plans.

## Verification

- Documentation only; no code or tests changed.
- The EmbeddingGemma 2 facts come from launch coverage (6 October 2026): 740M parameters, a
  768-dimensional shared space with Matryoshka truncation, 8,192 tokens, and stated llama.cpp
  support. They were not verified against Google's model card or run locally; the plan's step 1
  is the owner's test.
- Native Gemma 4 audio in llama.cpp is unverified; the plan's step 1 checks it.

HOW_TO_USE.md: no change to usage.
