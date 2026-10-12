# Making screen-per-prompt replies faster

Written by **Opus 5.5**, 2026-10-06, at the owner's request ("look into ways to reduce TTFT with
image inputs… just a bit of research"). **Status (2026-10-07): recommendations 1 and 2 are implemented**; see
[the changelog](../../changelog/2026-10-07T081500+0100_VOICE-REPLY-LATENCY_Opus-5.5.md). The
1,024-token calls in recommendation 2 turned out to be Gemma opening a thought channel inside
constrained companion calls. Recommendations 3 to 6 are not started. The
recommendations are ranked by expected gain for the effort. Claims marked *measured* come from logs
on this PC; everything else is from documentation or reports and still needs measuring here.

## What the delay actually is (measured)

Seven screen-on-prompt turns from the 2026-10-06 QA run (E2B IQ4_XS, `mmproj-F16`, managed
llama.cpp build `e85caa8`, from `scratchpad/shell-port/logs/llama-server.log`):

| Part | Time |
|---|---|
| Reading the prompt with the screen (3,400–4,200 tokens) | 0.6–1.2 s warm, 3.2 s on the first turn |
| Writing the reply (370–1,024 tokens at 100–145 tokens/s) | 2.6–9.9 s |
| Text-only turns for comparison (320–550 tokens) | 0.1–0.25 s to read |

So the image costs roughly **0.5–1 s** of reading time per turn, while **writing the reply costs
3–10 s**. Two turns hit the 1,024-token output cap. Voice adds speech synthesis on top, which
[the voice change](../../changelog/2026-10-06T224500+0100_VOICE-STREAMING-LIPSYNC_Opus-5.5.md)
cut from about 20 s to 0.25 s before first audio.

The biggest wins are therefore in *what she writes and when she starts speaking*, and only then
in the image.

## Recommendations

### 1. Speak while the reply is still being written (largest gain, SORA-side)

Today Core waits for the whole constrained-JSON companion call, then speaks. If the `speech`
field comes first in the schema and Core streams the response, a small incremental JSON reader
can hand each finished sentence of `speech` to TTS while the model is still writing the rest
(actions, gestures). First audio then comes after the first sentence of output, not after
the whole reply: about **0.3–0.5 s of writing instead of 3–10 s**. This needs `stream: true` with
the grammar (llama-server supports streaming with `json_schema`), and a check that the motion
fields arriving later still pass validation before they are acted on.

### 2. Keep replies short, and find out why some hit 1,024 tokens

A spoken companion line is rarely more than 60–100 tokens. Two of seven turns reached the output
cap, which suggests reasoning text or a runaway field inside the JSON. Capping `speech` length in
the schema, lowering `max_tokens` for companion turns, and checking whether Gemma's thinking mode
is on would cut the 3–10 s directly. Measure first: log the token count per field.

### 3. Pre-read the screen while the owner is talking (hides the image cost)

Voice already gives a natural head start: press-to-talk plus Whisper takes over a second. When
the owner **presses** talk, Core can capture the screen and send a warm-up request containing
`[system + context + screen]` with `n_predict: 0`. With `cache_prompt` (on by default), the real
request, which has the same prefix plus the transcript, then only reads the new text tokens,
so the image cost (0.5–3 s) disappears behind the speaking time. Requirements and risks:
- The image must come **before** anything that changes per turn. Today the screen note and
  images follow the prompt text, so the order in `_build_messages` would need to change.
- Gemma uses sliding-window attention; llama.cpp may re-read the whole prompt instead of reusing
  it unless context checkpoints (`--ctx-checkpoints`, present in the installed build) or
  `--swa-full` are set. **Test this first**, because it decides whether the idea works at all.
- The screen is a little older (captured at press, not release). For a live companion that is
  probably fine. Typed messages could do the same on the first keystroke.

### 4. Send a smaller screen image

SORA sends a full-resolution PNG. Gemma 4 resizes every image to its token budget anyway (70,
140, 280, 560 or 1,120 tokens, up to 9 patches per token), so the extra pixels only cost
PNG encoding in the shell, base64, transfer, decoding in llama-server and resizing. Downscaling
to about 1,024–1,280 px on the long edge as JPEG at quality 85 before sending should save
a few hundred milliseconds. Keep full resolution for an explicit "read this text" request.

### 5. Choose the image token budget deliberately

llama-server has `--image-min-tokens` and `--image-max-tokens` (both present in the installed
build). A smaller budget (280) reads faster; a larger one (1,120) is needed for small text. Two
cautions:
- Reported crash: on Gemma 4, setting `--image-max-tokens` aborts with "non-causal attention
  requires n_ubatch >= n_tokens" unless `--ubatch-size` is at least the image's token count.
  SORA's default ubatch is 512, so budgets over 512 need ubatch raised to match.
- The measured 3,400–4,200 prompt tokens are larger than one image plus the text-only context
  (~500) would explain. Log the image's token count (llama-server's debug log shows the image
  chunk) before tuning, because something may be sending more image tokens than expected.

### 6. Check where the vision encoder runs

`--mmproj-offload` (on by default) keeps the vision encoder on the GPU. Make sure it is on: one
report shows encoding taking tens of seconds when it falls back to CPU. `--mtmd-batch-max-tokens`
also exists in this build and may matter for large images. The projector is F16 (about 150M
parameters for E2B/E4B); a Q8 projector would be smaller but untested here.

### 7. Alternatives to llama.cpp (lower priority)

- **vLLM / SGLang:** strongest multimodal prefix caching (hash-based image reuse), but they are
  Linux/CUDA first, and this PC runs Windows with an AMD GPU. Not practical now.
- **Ollama / LM Studio:** both wrap llama.cpp, so the same limits apply. No gain.
- **ONNX Runtime GenAI with DirectML:** runs on AMD under Windows and has Gemma support, but
  multimodal support for Gemma 4 is unverified.
- **Conclusion:** stay on llama.cpp. The ideas above are all available there, and the server
  binary is already managed by SORA.

## Suggested order

1. Measure: per-field output tokens, image token count, and whether prompt reuse works with SWA
   (a short QA script against an isolated llama-server; no change to the owner's setup).
2. Short replies (2) and streaming speech from the JSON (1): the most perceived latency.
3. Pre-reading the screen on press-to-talk (3), if step 1 shows the cache is reused.
4. Image size and budget (4, 5) as tuning.

## Sources

- llama.cpp issue: [Gemma 4 crashes with `--image-max-tokens`](https://github.com/ggml-org/llama.cpp/issues/21461)
- [Gemma vision understanding (token budgets)](https://ai.google.dev/gemma/docs/capabilities/vision)
- [Gemma 4 for computer-vision engineers](https://datature.io/blog/gemma-4-what-computer-vision-engineers-actually-need-to-know)
- [llama-server README (`cache_prompt`, `--cache-reuse`)](https://fossies.org/linux/llama.cpp/tools/server/README.md)
- [Full prompt re-processing on SWA models](https://particula.tech/blog/prompt-reprocessing-swa-hybrid-models-kv-cache)
- [Images breaking llama.cpp prompt cache in another client](https://github.com/can1357/oh-my-pi/issues/9145)
- [Slow vision encoding in llama-server](https://github.com/ggml-org/llama.cpp/issues/22582)
- [Multimodal KV caching (LMCache)](https://blog.lmcache.ai/2025-07-03-multimodal-models/) and [MPIC](https://arxiv.org/html/2502.01960v2)
- Local: `llama-server --help` for build `e85caa8`, and the QA log above.
