# Memory manager: EmbeddingGemma 2 in each use, and the pipeline end to end

Observed by **Opus 5.5**, 2026-10-09, on the owner's PC (RX 9070 XT). Evidence kinds are kept
apart below. All memories here are **fabricated**; nothing is about the real owner, and the
owner's profile was not touched (the owner's SORA was not running).

- Probe: `scripts/memory/probe_use_cases.py`, data `training/memory/use_case_probe.json` plus
  `embedder_probe.json`. Raw report: `.local/memory-probe/use-cases-20261009-232205.json`.
- Model: EmbeddingGemma 2 UD-Q4_K_XL with mmproj-Q8_0, llama.cpp b11516 Vulkan, 512 dimensions,
  through Core's own `sora.memory.embedder.LlamaEmbedder` and `sora.memory.features`.
- One run of each. Small fabricated sets: these calibrate starting thresholds, not acceptance.

## Live model results (one run)

| Use | Result | Consequence |
|---|---|---|
| U1 recall by meaning | 30/30 questions found their memory at rank 1. Today's recall (the 10 most recent) contained it 10/30 times. Target similarity 0.745–0.907; off-topic messages' best match 0.622–0.796 (AUC 0.98) | Recall floor **0.74** (the old placeholder, 0.55, let all 15 off-topic messages through) |
| U2 follow-ups ("what does she hate?") | 8/8 at rank 1 alone and with the previous message | The message alone is enough on this set |
| U3 repeats vs new facts | Repeats' nearest memory 0.933–0.987 (8/8 found their own); new facts 0.753–0.857 | A clear repeat signal for acceptance |
| U4 worth keeping vs chatter | Prototype margin separated all 24 (AUC 1.0; 23/24 at zero) | Useful acceptance feature |
| U5 reply / read-result relevance | Relevant 0.80–0.94; unrelated 0.667–0.784 (AUC 1.0) | Threshold **0.79**; the old 0.55 scored 0.5 |
| U6 image relevance | Owner message about the image 0.686–0.748; unrelated message 0.505–0.584 | Image threshold **0.63** (stored for when images are kept) |
| U6 near-duplicate images | JPEG q85 0.985–1.0 of the original; half size 0.858–0.992; 70% crop 0.927–0.981; different images 0.602–0.921 | JPEG q85 storage keeps the embedding (plan §6); duplicate cut **0.91** (95% balanced) |
| U7 comparison | Bands on 41 pairs: same 0.893+, updated 0.831–0.948, related 0.766–0.841, unrelated ≤ 0.765. Leave-one-out: trained same_subject **1.00** vs similarity rule 0.88; trained update **0.83** vs word rule **0.91** | same_subject threshold **0.85**; the update rule stays until there is more data |
| U8 goals → memories | Mean AUC 0.78 (0.69–0.89 per goal) | Similarity alone is a weak goal signal; goal-aware remembering needs a trained layer or the brain |
| U9 her own thoughts | Owner facts outranked her similar thoughts 6/6, with and without author titles | No author prefix needed for ranking; recall labels still name the author |
| U10 map | PCA keeps 50% (2D) and 58% (3D) of each memory's 5 nearest neighbours | Rough map only; links and recall use full vectors (plan §3.8) |
| U11 speed | Query 8 ms, stored text 9.4 ms, image 149 ms (GPU); comparing with 5,000 memories in Python 26.5 ms | Per-message recall by meaning is affordable; images belong to the idle manager |

## Pipeline, end to end (live model, isolated profile)

`.local/memory-pipeline-qa-2026-10-09/`, through `SoraRuntime.memory_host` with the real
embedder (scratch script, not committed):

- 32 memories (the 30 probe memories, an update and one of her own thoughts) embedded, compared
  and linked in **3.0 s**:
  - 67 links: 65 related, plus `same_subject` and `update` from "My favourite colour is now
    green" to "My favourite colour is teal." (0.927);
  - 102 decisions logged.
- `on` mode, 10 places:
  - "Where did I hide the workshop key?", "What colour do I like?" and "How old is our cat?"
    each put the right memory first, in 19–26 ms;
  - "Tell me a joke" matched nothing above the floor, so recent memories filled the context.
- `shadow` mode returned the recency choice unchanged and recorded both lists.
- The embedding server stopped when Core closed.

## Training program (fixtures and fabricated data)

- `scripts/memory/train_layers.py` (check mode) on the owner's profile, read-only: 0 examples.
  The manager hasn't run there yet.
- On an isolated profile (`.local/memory-training-qa-2026-10-09/`) with `--include-fabricated
  --min 20 --min-per-class 8 --train --adopt`, all four layers trained:
  - acceptance (0.83 vs 0.50) and update (1.00 vs 0.83) were adopted;
  - relevance and same_subject were kept as candidates, because they didn't beat their rules;
  - the held-out sets are very small (a handful each), so the numbers only show the program
    works.
- Component tests: `tests/memory/test_memory_manager.py` (fake embedder).

## Not run

- The owner's SORA with the manager. It starts at the next owner launch: migration 14, then
  shadow mode.
- Images and audio as memory parts: pending entries (plan step 2) don't exist yet, so the
  manager embeds text only. The image thresholds above wait for that.
- Any training on the owner's own labels (there are none yet), and EmbeddingGemma fine-tuning.

## Addendum, 2026-10-10: remembered turns with pictures and voice (live model, isolated profile)

`.local/memory-entries-qa-2026-10-10/`, scratch script (not committed). Two memories were
made with `remember_turn`, then processed by the memory manager through
`SoraRuntime.memory_host` with the image/audio projector:

- **First memory:** a memory-map screenshot, an unrelated chat screenshot and a spoken clip.
- **Second memory:** a settings screenshot.
- **Embedder:** it found and loaded the projector (modalities text, image, audio).
- **Verdicts:**

  | Part | Score | Kept? |
  |---|---|---|
  | Memory-map screenshot | 0.688 | kept |
  | Chat screenshot | 0.627 | dropped (just under 0.63) |
  | A generic "Got it" reply on the settings memory | 0.759 | dropped |
  | Voice clip | 0.595 | kept (voice is always kept by the fixed rule) |

- **Recall by meaning:** "an anime girl pointing at a graph" found the memory-map memory
  (0.812) through its image. "A sidebar with categories" found the settings memory.
- **Not run:** a full turn on the owner's SORA with E4B choosing `remember`. Whether E4B calls
  the tool at the right moments is the open question; the `companion.read_turn` traces will
  show it.

## Addendum, 2026-10-10 (later): whole-memory vectors and deleting irrelevant media

- **Voice relevance calibration** (live model, one run, scratch script): 14 spoken probe clips
  against their own text scored 0.692–0.924 (query form vs audio). Against other memories'
  text they scored 0.498–0.664. The threshold is set to 0.68, which kept 14/14 and dropped
  182/182 on this set.
- **The same isolated check, re-run** (`.local/memory-entries-qa-2026-10-10/`, fresh):
  - the unrelated chat screenshot (0.627) and the unrelated voice clip (0.595) were deleted
    from the entry folder;
  - each folder holds `entry.json` and its relevant image only;
  - stored parts: `owner`, `words`, `reply`, `image-1`, `whole`;
  - `map_coordinates()` returned 2D positions from the whole vectors;
  - recall results were unchanged from the first run.
- **Not checked:** how far whole vectors that include media move the linking thresholds.
  Only text-only links were calibrated.
