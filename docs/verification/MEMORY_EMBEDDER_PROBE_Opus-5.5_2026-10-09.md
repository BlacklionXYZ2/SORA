# Memory embedder probe: EmbeddingGemma 2 (Q4_K_XL) on the owner's machine

**Opus 5.5, 2026-10-09 08:17 +01:00.** This is step 1 of
[MEMORY_MANAGER_2026-10-08](../plans/MEMORY_MANAGER_2026-10-08.md), which the owner asked for
ahead of building anything. Evidence kind: **live model, local hardware** (RX 9070 XT, Vulkan),
one run.

- **Probe:** `scripts/memory/probe_embedder.py`
- **Data:** `training/memory/embedder_probe.json`
- **Raw report:** `.local/memory-probe/report-20261009-081709.json`

## Setup

- **Model:** [unsloth/embeddinggemma-2-GGUF](https://huggingface.co/unsloth/embeddinggemma-2-GGUF)
  - `embeddinggemma-2-UD-Q4_K_XL.gguf`, 167.5 MB, as the owner chose;
  - `mmproj-Q8_0.gguf`, 529.1 MB: the vision and audio encoders.

  Both match their published SHA-256 hashes and are in `.local/models/embeddinggemma-2/`.
- **Runtime:** the owner's `C:\llama.cpp` (HIP build, commit e85caa8) **cannot load it**:
  `unknown model architecture: 'gemma-embedding2'`. Support arrived in llama.cpp PR #30054
  (merged 2026-10-06). The probe used the official nightly `b11516`, Windows Vulkan x64
  (SHA-256 verified), from `.local/llama.cpp-b11516/`. The owner's folder was not changed.
- **Server:** `llama-server --embeddings --pooling mean -c 8192 -b 8192 -ub 8192 --mmproj …`.
  - Text goes to `/embeddings` or `/v1/embeddings`.
  - Images and audio go to `/embeddings` as `{"content": [{"prompt_string": <media_marker>,
    "multimodal_data": [<base64>]}]}`. `media_marker` is random per server run, so read it from
    `/props`.
  - The server reports vision, video and audio support.
- **Numerics:** GPU (`-ngl 99`) and CPU (`-ngl 0`) gave identical text similarities, with no NaNs
  and unit-length vectors. The model card's float16 warning did not apply on this runtime.

## Results

| Test | Result |
|---|---|
| A. Text recall: 30 memories (4 are the owner's real ones), 30 reworded questions | **30/30 at rank 1**, MRR 1.0, at 768, 512 and 256 dims, with or without task prefixes. Owner memories: ranks 1, 1, 1, 1 |
| B. Relation bands (sentence-similarity prefix) | same fact 0.894–0.979; **updated fact 0.882–0.946**; related 0.771–0.841; unrelated 0.716–0.748 |
| C. Caption → image, 9 images | 8/9 rank 1, 9/9 top 3 (05-settings concept at rank 3) |
| C. Image → caption | 7/9 rank 1, 9/9 top 3. Matched pairs averaged 0.747, unmatched 0.606 |
| D. Spoken memory (Windows TTS) → written memory, 6 clips | **6/6 rank 1** |
| E. Speed, warm, GPU | text 29 ms, audio 23 ms, **image 387 ms** |

## What this means for the memory design

1. **Retrieval by meaning works.** It works for text and cross-modally (audio, images), and 256
   dimensions lost nothing on this set. Store 512, which gives headroom for images, which are
   weaker.
2. **Similarity cannot tell "same fact" from "updated fact".** The bands overlap (0.882–0.946
   inside 0.894–0.979). The plan's `same_fact` / `superseded` rule therefore cannot be
   similarity bands alone. A high-similarity pair is a *candidate*; whether it repeats or
   replaces the old memory needs the comparison layer, with features beyond similarity (numbers,
   dates or colours that differ, "now", "moved", "changed"), or a brain call.
3. **Related and unrelated are separable here, but narrowly** (0.748 vs 0.771). Everything sits
   above about 0.7, so thresholds must be measured relative to this model's baseline, never set
   as absolute "high similarity" values.
4. **Image embedding is slow (about 0.4 s) but fine for the idle-time manager.** Don't embed
   images on the reply path.
5. **A separate runtime is needed.** EmbeddingGemma 2 needs llama.cpp b11516 or later. Either
   SORA runs the embedder with its own (nightly) llama-server, or the owner's HIP llama.cpp is
   updated. Note that nightlies currently ship Vulkan, not HIP, for Windows.

## Limits

- **The text set is easy:** 30 distinct facts, with only a few near-misses (Ada and Adam, tea and
  coffee). Hundreds of real memories, with many on similar topics, will be harder. Re-run the
  probe on real memories once there are more.
- **Captions:** I wrote them after viewing 7 of the 9 images. 02-chat and 05-settings were
  captioned from their names and the other concept images, which may explain 05-settings at
  rank 3.
- **One run, one quantisation (Q4_K_XL).** Not compared with Q8_0 or F16, and GPU memory was not
  measured.
- **Speech:** the spoken clips are synthetic (Windows SAPI), not the owner's voice.

## Addendum, 08:44: multimodal memories (text + image + audio)

- **Probe:** `scripts/memory/probe_multimodal.py`; **data:**
  `training/memory/multimodal_probe.json`.
- **Memories:** 8 fabricated memories, each with text, an image and a spoken note that adds new
  information. Two of them share an image.
- **Questions:** each aims at one part: the text, something only visible in the image, or
  something only said in the note.
- **Distractors:** the 30 text memories above.
- **Raw report:** `.local/memory-probe/multimodal-20261009-084413.json`.

Rank-1 share, with the top-3 share in brackets:

| Storage | Text questions | Image-only questions (7) | Audio-only questions (8) |
|---|---|---|---|
| text only (what SORA stores today) | 1.00 | **0.14** (0.57) | 0.38 (0.88) |
| fused: one embedding of text + image + audio | 1.00 | 0.71 (0.71) | 0.88 (1.00) |
| max-part: a vector per part, closest part wins | 1.00 | **0.71 (0.86)** | **0.88 (1.00)** |
| mean of part vectors | 1.00 | 0.43 (0.86) | 0.88 (1.00) |

**Misses:**
- "a weekend trip plan to Lake Kawaguchi with a packing list" (small text in the memory-graph
  image): fused ranked it 19th and max-part 2nd. The text distractor "weekend trip to the Lake
  District" competes for it.
- "big letters spelling SORA" (partly hidden behind the avatar): ranks 5–6.

**Speed:** a fused embedding of text, image and audio costs about the same as an image alone,
0.27–0.39 s.

**Conclusions:**
1. Media must be embedded. Text-only memories lose most of what the image or audio held.
2. Store **per-part vectors as well as the fused one**. At recall, score a memory by its best
   part (or the best of fused and parts). Per-part vectors are also what plan stage B (choosing
   parts) needs.
3. Small or partly hidden text inside images is weak. Have the brain write a short caption,
   including any readable text, when an image is kept, and store it as a text part.
