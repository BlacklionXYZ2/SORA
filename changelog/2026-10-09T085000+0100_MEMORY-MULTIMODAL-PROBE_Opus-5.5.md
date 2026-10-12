# Memory probe: fabricated text + image + audio memories; importance vs relevance in the plan

Model name: **Opus 5.5**. Checkpoint **2026-10-09 08:50:00 +01:00**, Europe/London. Status:
**probe built and run; plan updated; no SORA code changed.** The owner asked: "How do we
determine the importance of a memory? Or should it be relative always to the current task …?
And could you test EmbeddingGemma with fully modal text + image + audio memories? Fabricated for
testing purposes".

## Changes

- New `scripts/memory/probe_multimodal.py` and `training/memory/multimodal_probe.json`:
  - 8 fabricated memories, each with text, an image and a spoken note (Windows voice);
  - questions aimed at the text, at image-only details or at audio-only details;
  - four storage strategies compared (text only, fused, max-part, mean-part) against 30 text
    distractors.
- Verification addendum in `docs/verification/MEMORY_EMBEDDER_PROBE_Opus-5.5_2026-10-09.md`.
- Memory plan:
  - §10a: store per-part vectors plus a fused one, and recall by the best part; images also get a
    brain-written caption;
  - §10b: importance (stored, slow) vs relevance (per moment, never stored), and the recall
    ranking `relevance + a·importance + b·recency`.

## Verification

- **Live, owner's GPU, one run.** Rank-1 shares:
  - image-only questions: text-only storage 0.14, fused 0.71, max-part 0.71 (top 3: 0.86 vs
    fused 0.71);
  - audio-only questions: text-only 0.38, fused and per-part 0.88;
  - text questions: 1.00 for every strategy.
- **Misses:** small text inside an image ("Lake Kawaguchi") and letters partly hidden behind the
  avatar.
- **Not run:** a larger or real dataset, and other quantisations. Fabricated data only, as the
  owner asked.

HOW_TO_USE.md: no change to usage.
