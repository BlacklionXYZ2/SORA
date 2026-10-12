# Memory manager: multimodal memories, a trained keeper and a memory network

Prepared **2026-10-08**, Opus 5.5, from a planning conversation with the owner. Status
(2026-10-09): **steps 1, 3 (text parts), 4 (shadow by default) and 6 built**, see §10c; steps 2,
5, 7 and 8 open. The owner asked for this work before the V1 acceptance run; VISION.md places
"the memory graph and deeper memory management" after V1. Companion plan:
[always-on listening](ALWAYS_ON_LISTENING_2026-10-08.md), which supplies the audio this plan
stores.

This plan builds on the capture tier in
[MEMORY-CHOICE-AND-AGENT-CHANGELOGS](MEMORY-CHOICE-AND-AGENT-CHANGELOGS_2026-09-29.md) §3.6 and
replaces only its compaction step.

## 1. Owner decisions

- When SORA decides to remember, the **whole turn is stored as an entry, with any images** (and
  audio), not only the owner's words.
- Later a **memory manager** enters it into SQL memory. It decides whether the memory is kept and
  which parts are relevant. It then stores it, and compares it with other memories to build the
  network.
- The manager uses **EmbeddingGemma 2** (multimodal embeddings) with **small trained layers on
  top**. Laya (System-1) stays for tool decisions.
- "Compress" means **abstract**: drop unnecessary detail. The owner's words are always kept
  verbatim, and no model rewrites them.
- **Separate small layers** for acceptance, part relevance and memory comparison.
- **Vectors are stored with memories.** All-against-all comparison is affordable, and a 2D/3D
  projection gives every memory a position in a map.
- A **forgetting score** built from recalls over time.
- **Audio is a first-class part.** The microphone will eventually be always on (see the companion
  plan).
- **Every model is swappable** (§9).
- Sensitive content is **out of scope for now**. EmbeddingGemma 2 will be **tested by the owner**
  later; it can be swapped for another embedder.

## 2. Today (verified in source, 2026-10-08)

- `_maybe_remember` (`runtime/service.py`): E4B answers `{"memory":"remember"}` or `none`. Core
  then writes a capture file (`memory/captures.py`: owner text, reply, stated reason, optional
  reasoning) **and** the canonical `memories` row (the owner's words) at once.
- Since 2026-10-08, turns with automatic screen images may remember too; turns with owner
  attachments may not.
- `compact_captures` is deterministic: it marks captures as folded and deletes them after
  retention. No model reads them.
- Images are never stored. Recall is literal text matching (`find_memory`, `memory_context`).
- The `artifacts` table exists, unused, for file-backed objects.

## 3. Pipeline

```
turn → [E4B: remember?] → pending entry (+ provisional memory) → … idle …
     → manager: embed parts → accept? → which parts? → store → link → (recall later)
```

### 3.1 Pending entry, written when she chooses to remember

| Part | Source | Notes |
|---|---|---|
| Owner message | the turn | Anchor. Always kept, verbatim |
| Her reply | the turn | |
| Read results | the read turn | Window text, file excerpts, agent results; bounded |
| Images | automatic desktop overview, closer window, owner attachments | JPEG at the size the model used (§6) |
| Audio | voice turn clip; later a slice of the rolling buffer | Compressed (Opus or similar); see the companion plan |
| Context | Core | Time, foreground app, agent, project, conversation and turn IDs, model IDs |

- **A provisional memory is written immediately**: the owner's words, marked `pending`, so
  "remember X" followed by "what's X?" works before the manager runs. The manager later confirms,
  completes or withdraws it.
- Entries live under `<state>/memory/pending/<id>/` as `entry.json` plus the media files. They
  are written atomically and never sent to a prompt, a status file or a social payload.

### 3.2 Manager runs

- **When:** in idle time, at shutdown, or when pending entries exceed a cap. It yields to the
  conversation as adaptive perception does (preempted, never queued in front of a reply).
- **On failure:** the entry stays pending and is retried. A memory is never half-written.

### 3.3 Embedding

- Each part is embedded separately, and the **whole entry** is also embedded as one mixed input
  (EmbeddingGemma 2 accepts mixed text, image and audio up to 8,192 tokens; an image is about 280
  tokens, audio about 25 tokens a second).
- Vectors are normalised and cut to 512 dimensions (Matryoshka; to be confirmed in the owner's
  test).

### 3.4 Stage A: accept the memory

- **Inputs (features):** owner message vector; entry vector; nearest existing memory similarity;
  the count of similar memories in the last 7 days; message length; statement or question; and
  E4B's nomination.
- **Output:** P(keep). Below the threshold the entry and its provisional memory are withdrawn.
- **Until trained:** keep everything E4B nominated, which is today's behaviour.

### 3.5 Stage B: choose parts (abstract)

- The owner message is always kept. Each other part is scored **against the owner message**,
  because the owner's words define what the memory is about.
- **Inputs per part:**
  - its similarity to the owner message and to the whole entry;
  - its maximum similarity to the other parts of the same type;
  - its type (reply, read result, desktop image, window image, owner image, audio);
  - its size or duration.
- **Output:** P(relevant).
- Among near-duplicate images (for example the desktop and its own close-up), only the best is
  kept. Read results are kept as bounded excerpts. No model writes summaries.

### 3.6 Stage C: store

1. Write the canonical `memories` row: `content` = the owner's words. A part list and scores go
   in `evidence_json`; provenance carries the turn, the model IDs and the manager version.
2. Move kept media to `<state>/memory/media/`. Record each in `artifacts` (sha256, bytes) linked
   to the memory.
3. Write the vectors in a new `memory_vectors` table: memory or part ID, embedder ID and version,
   dimensions, and the vector as a float32 BLOB.
4. Delete the pending entry and any dropped media.

### 3.7 Stage D: link (the network)

- **Comparison:** the new memory is compared with **all** stored memory vectors (a matrix
  product; 5,000 × 512 is instant with numpy, which becomes a Core dependency). A full
  all-against-all rebuild runs only after an embedder change.
- **Edges, from the comparison layer or bands:**
  - `same_fact`: very high similarity plus text overlap. The old memory is marked
    `superseded_by` the new one ("my favourite colour is now green").
  - `related`: weighted by similarity; only the top few per memory, to keep the graph sparse.
  - none.
- **Fixed nodes that need no model:**
  - apps (the foreground process at capture);
  - agents (task provider);
  - projects (task project);
  - sessions (conversation day).

  Edges to these are certain, so the graph can be browsed by thing as well as by topic.

### 3.8 Map coordinates

- 2D and 3D positions are projected from the stored vectors for the Memory window's graph view
  (the shell already has `GraphPanel`/`GraphLayout`).
- **PCA** is the default: stable and repeatable. **UMAP** is optional: fitted occasionally, with
  new points placed into the fitted layout. Refitting rearranges the map, so it is shown as a
  deliberate action.
- Neighbours and edges always come from the full vectors, never from the projection.

## 4. Training the three small layers

| Layer | Learns | Labels from |
|---|---|---|
| Acceptance | keep this memory? | owner deletes (no); owner pins or edits (yes); later recall used in an answer (yes); never recalled in months (weak no) |
| Part relevance | keep this part? | owner restores a dropped part (yes) or removes a kept one (no) in the Memory window |
| Comparison | same fact / related / unrelated | owner merges, unlinks or links memories |

- **Model:** each is a logistic regression or small two-layer network on about 10–20 features.
  They are kilobytes in size and train on the CPU in seconds.
- **Logging:** every manager decision is logged as a JSONL training example (features, decision,
  versions). Labels are joined later. Day one already produces data.
- **Bootstrap:** a stronger model (E4B or an agent) may label a few hundred past entries, marked
  `bootstrap`, with lower weight than owner labels.
- **Procedure:** a script `scripts/train-memory-layers.py`, run by hand or nightly:
  1. Split into train and held-out sets.
  2. Train each layer and pick its threshold for the wanted precision.
  3. Write a report: agreement before and after, and examples of mistakes.
  4. Adopt only if it is better on the held-out set.
- **Versions:** every layer version is kept, and rollback is a setting.
- **Before enough labels:** fixed thresholds tuned on a few dozen of the owner's real moments.
- **Fine-tuning EmbeddingGemma itself** is optional and later. It happens only if reports show
  the layers have plateaued because similarity is wrong for the owner's content. It needs a GPU,
  thousands of pairs, and re-embedding all memories.

## 5. Forgetting score (recall strength)

- **Strength:** the sum of recall boosts, each decaying with time since that recall (an ACT-R-style
  activation): `strength = base + Σ_i w_i · decay(now − t_i)`.
  - `base` is the acceptance layer's confidence.
  - `w_i` is larger when the recall was **used** in an answer than when it was only retrieved.
- **Fixed cases:**
  - pinned memories never decay;
  - owner-edited ones get a boost;
  - superseded ones decay fast.
- **Computation:** recall events (`memory_recalls`: memory, time, used or not) are stored and the
  score is computed when needed, with no background job. The decay shape and weights are settings,
  and can later be learned from the same labels.
- **Low strength** drops a memory out of automatic recall and archives it. Nothing is deleted
  automatically; deletion is the owner's.

## 6. Media storage

- **Images:** JPEG at quality 85–90, at the size the brain actually used (the vision-detail token
  budget × about 2,304 pixels per token). That is roughly 0.4–0.8 MB instead of 3–6 MB of PNG.
  - JPEG, not WebP, because llama.cpp decodes JPEG.
  - The capture helper encodes it, since Core has no image library.
  - Test first that brain and embedder accuracy holds at that quality.
- **Audio:** Opus or similar mono 16 kHz, as clips of seconds (the embedder accepts up to about 5½
  minutes).
- **Recall:** images and audio are shown or played to the owner in the Memory window. They are
  attached to the brain only when the owner asks about that moment, at most one image per reply.

## 7. Privacy wording to change when built

Settings, HOW_TO_USE.md and the perception help currently say screen images are never saved.
They become: saved only when she chooses to remember, on this PC, and kept or deleted by the
memory manager. Visible and deletable in the Memory window; Pause stops it. (Filtering sensitive
content is out of scope for now, by owner decision.)

## 8. Interfaces (sketch)

- `Embedder`: `modalities() -> set`; `embed(parts) -> vectors`; `id/version`; `dimensions`.
- `MemoryLayer` (×3): `score(features) -> probability`; `id/version`.
- `MemoryManager.run(budget)` → processes pending entries; returns counts; emits
  `memory.created`, `memory.superseded`, `memory.linked` and `memory.withdrawn` events.
- Recall: `recall(query parts, k) -> memories` (vector nearest plus one hop through strong
  edges), with each recall recorded in `memory_recalls`.

## 9. Swappable models

Every model fills a named slot with a declared interface; Core owns data and decisions.

| Slot | Initial | Swap rule |
|---|---|---|
| Remember? | E4B one-word choice | any brain |
| Embedder | EmbeddingGemma 2 | any multimodal embedder; triggers a re-embed job; modalities it lacks fall back (for example audio via its transcript) |
| Acceptance / relevance / comparison | thresholds → trained layers | any classifier with the same features |
| Map projection | PCA | UMAP or others |

## 10. Steps

1. **Owner test of EmbeddingGemma 2** (owner): speed and memory on this PC; whether llama.cpp
   really serves image and audio embeddings; image↔text similarity on real screenshots.
2. **Entries:** pending entries with JPEG images and voice clips; provisional memory; the
   privacy wording (§7).
3. **Manager with fixed thresholds:** embed, accept, choose parts, store, link, the `memory_vectors`
   table, numpy, and decision logging.
4. **Recall by meaning:** replaces literal matching, with recall events.
5. **Memory window:** the map, parts, restore and remove, merge and unlink, which also capture
   labels.
6. **Training script** for the three layers, with reports and versions.
7. **Forgetting score** and archive.
8. **Audio from the rolling buffer** once always-on listening exists.

## 10a. Step 1 results (2026-10-09)

[Probe evidence](../verification/MEMORY_EMBEDDER_PROBE_Opus-5.5_2026-10-09.md), EmbeddingGemma 2
Q4_K_XL on llama.cpp b11516 (Vulkan):

- **Retrieval:** text, audio→text and image↔text retrieval work. 256–512 dims are enough on this
  set. Image embedding takes about 0.4 s, so it belongs to the idle manager only.
- **§3.7 changes:** "same fact" and "updated fact" have overlapping similarity (0.88–0.98), so
  high similarity only nominates a pair. The comparison layer decides between repeat and
  superseded, with features beyond similarity or a brain call.
- **Thresholds:** related vs unrelated separate narrowly (unrelated ≤ 0.75, related ≥ 0.77, all
  above about 0.7). Thresholds must be relative to this model's baseline.
- **Runtime:** this needs a newer llama.cpp than the owner's HIP build, so the embedder runs as
  its own server process.

- **Multimodal memories** (8 fabricated text + image + audio memories): storing text only
  finds image-only details 1/7 times and audio-only details 3/8 times. Per-part vectors (closest
  part wins) find them 5/7 and 7/8, slightly better than one fused vector (top-3 0.86 vs 0.71 for
  images). So store **per-part vectors plus the fused one**, and recall by the best part. Small
  or partly hidden text in images is weak, so a kept image also gets a brain-written caption,
  including any readable text, as a text part.

## 10b. Importance vs relevance (owner question, 2026-10-09)

- **Importance** belongs to the memory, is stored and changes slowly: acceptance confidence,
  pinned or edited, and the recall-strength forgetting score (§5). It decides keep, archive or
  forget, not what is recalled now.
- **Relevance** belongs to the moment and is never stored: similarity between the memory (best
  part) and the current context (the owner's message, optionally the screen and active app).
- **Recall:** candidates above a relevance floor, ranked by
  `relevance + a·importance + b·recency`, with small `a` and `b`. Relevance leads, and importance
  and recency break near-ties. `a` and `b` can later be learned from which recalled memories the
  brain actually used.

## 10c. Pipeline and training program (2026-10-09)

Built by Opus 5.5 at the owner's request ("put everything in place to train it when I say").
Evidence: [use cases and pipeline](../verification/MEMORY_USE_CASES_Opus-5.5_2026-10-09.md);
training guide: [TRAINING_MEMORY_LAYERS](../runbooks/TRAINING_MEMORY_LAYERS.md).

| Piece | Where | State |
|---|---|---|
| Embedder slot | `sora/memory/embedder.py` (EmbeddingGemma 2 on its own llama.cpp b11516 server, text-only unless media is needed; Quit closes it) | Built; `scripts/setup-memory-embedder.ps1` installs it |
| Vectors, links, recalls | migration 14: `memory_vectors`, `memory_links`, `memory_recalls`; `sora/memory/store.py` | Built |
| Manager (step 3) | `sora/memory/manager.py`: owner's words and, while the capture exists, her reply; same_subject / update / up to 5 related links; acceptance and reply relevance; every decision logged as a training example (IDs and features only) | Built for **text parts**. Withdrawal and superseding are recorded, not applied, until the step 5 review exists |
| Recall by meaning (step 4) | `MemoryManager.recall` and `runtime/memory_host.py`: floor 0.74, ranked by relevance + 0.05·importance + 0.05·recency; Settings → Memory → Memory manager: **shadow** (default; records beside recency recall), **on**, off | Built. Shadow is the default until the owner compares the records |
| Features and fixed thresholds | `sora/memory/features.py`, calibrated on the use-case probe | Built |
| Layers and training (step 6) | `sora/memory/layers.py` (logistic, versioned, rollback), `sora/memory/training.py`, `scripts/memory/train_layers.py` | Built; **not trained** on the owner's data (none exists yet) |

Changes from §3–§5 found while building:

- **§3.7:** a corrected memory is superseded, so the manager never compares it with its
  correction. Training builds those update pairs from stored vectors instead.
- **§3.4:** "keep everything E4B nominated" stays the acceptance rule. The repeat signal (≥ 0.93
  to an existing memory) and the facts-versus-chatter prototype margin are its features.
- **§3.5:** reply relevance uses similarity ≥ 0.79, not a low floor. Images will use 0.63
  (query form) and near-duplicates 0.91.
- **§5:** importance is a constant 0.5 until acceptance confidence is stored per memory.

## 10d. The remember tool and stored media (2026-10-10, step 2)

Owner decision: SORA decides to remember with a JSON tool that takes a **title and a
description**, and Core stores the memory from those plus all the turn data.

- **`remember {title, description}`** is a companion call in the read loop, beside
  `remember_thought`. It doesn't end the turn, the first one in a turn wins, and the decision
  layer never hides it. It replaces the after-every-turn yes/no call for brains that use
  companion calls. That call remains for other brains.
  - The description is her lasting fact in third person ("His favourite colour is now green,
    not teal.") and becomes the memory's content. The title goes in `memories.title`
    (migration 15). Recall labels show the title.
  - The owner's exact words are still kept verbatim, in the entry, as the always-kept `words`
    part. This keeps §1's rule while giving recall a clean, complete fact.
  - The owner's attached images no longer rule a turn out.
- **Entries** (`sora/memory/entries.py`): `<state>/memory/entries/<memory_id>/` holds
  `entry.json` and the media:
  - `entry.json`: title, description, the owner's words, her reply, the read observations, the
    app and model, and the manager's verdict per part;
  - images: as the brain received them (PNG today; JPEG at quality 85 tested equivalent for the
    embedder, encoding waits for the capture helper);
  - `voice.wav`: when the brain heard the owner's recording; Opus compression is later.
  - The folder is written atomically. Forgetting the memory deletes it.
- **Manager:**
  - each part is embedded; `words` is always kept;
  - `reply` and `read` are scored like text parts (0.79);
  - images are kept when relevant to the description (0.63) and not a near-copy of a kept
    image (0.91);
  - the voice clip is kept;
  - verdicts go to `entry.json` and the decision log;
  - media is never deleted by the manager, only marked;
  - the embedder loads the image/audio projector when it is installed (about 0.75 GB of VRAM
    in total), and stays text-only otherwise;
  - recall searches text parts above 0.74 and image and voice parts above 0.63.
- **Not yet:** a read result's own images, a slice of the always-on rolling buffer (step 8), a
  brain-written caption for each kept image (§10a), and showing or playing media in the Memory
  window (step 5).

## 10e. Whole-memory vectors and part relevance (2026-10-10, owner clarification)

- **The whole memory** is one embedding of her description with every **kept** part (the
  owner's words, a relevant reply or read result, kept images and voice), interleaved in one
  input with the similarity prefix. It is a numerical high-level summary, and it alone decides:
  - which memories are alike: links, repeats and updates (stage D), and the acceptance
    layer's "nearest memory";
  - the memory's place on the map: `MemoryManager.map_coordinates()`, PCA 2D or 3D of the
    whole vectors.
- **Part vectors** decide each part's relevance to the memory: a dot product of unit vectors,
  so the cosine, with her description. They also let recall match a single detail.
  Memory-to-memory similarity never uses parts, because a part lacks the context of the rest.
- **Irrelevant images and recordings are deleted, not stored.**
  - Images below 0.63, or a near-copy (0.91 or more) of a kept image.
  - Voice below **0.68**: calibrated live on 14 spoken clips, where matching text scored
    0.692+ and other texts 0.664 or less.
  - Text parts below 0.79 are not embedded; the text stays in `entry.json`.
  - Media the embedder can't judge (no projector) is kept until it can.
- **Order:** parts and relevance, then the whole, then links. The `similarity` part from
  2026-10-09 is replaced by `whole`. Memories without a `whole` vector are processed again
  in the background.
- **To check:** the linking thresholds (related 0.77, same subject 0.85) were calibrated on
  description-only vectors. Whole vectors that include media may sit on a different scale;
  recalibrate with real memories, or let the trained layers replace them.

## 11. Open questions

- Thresholds and the number of `related` edges per memory: decided by measurement in step 3.
- Retraining cadence (nightly or by hand) and the minimum labels before a layer replaces its
  thresholds.
- Whether the Memory window shows pending entries (proposal: yes, marked pending).
