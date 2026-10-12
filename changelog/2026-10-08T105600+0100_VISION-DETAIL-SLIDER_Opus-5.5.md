# Vision detail slider: Low, Medium and High set llama.cpp's image token budget; hand edits show Custom

Model name: **Opus 5.5**. Checkpoint **2026-10-08 10:56:00 +01:00**, Europe/London. Status:
**implemented, component-tested, page rendered headless, levels checked live on E4B.** This
moves V1 acceptance step 4 (screen awareness) forward.

The owner asked: "There should be a vision detail slider at the high level, then users can choose
to override the llama.cpp arguments which will automatically swap to 'custom' instead of low,
medium or high. There should also be a disclaimer that higher detail levels will increase
response times and context usage, but will increase reliability."

## Why

SORA's managed llama-server never passed `--image-max-tokens`. Every image, whatever its size,
was therefore cut to about 1200×480 pixels (about 250 image tokens) before Gemma's encoder saw
it.

The owner's DeepSeek reports (2026-10-05, E2B and E4B, one desktop scene, manual scoring) found:

- The token budget, not the capture size, decides what the model can read.
- E4B at the default budget invents convincing apps and readings.
- E4B at 2,048 tokens read Task Manager values and sentences on the second monitor.

My own run on 2026-10-08 confirmed the cut: 365 prompt tokens for a 1920-px overview.

## Changes

1. **New `src/sora/providers/vision_detail.py`.**
   - Levels, each setting image tokens / physical batch / context:
     - low: 280 / 512 / 8,192;
     - medium: 1,024 / 1,024 / 12,288;
     - high: 2,048 / 2,048 / 16,384.
   - `fill_missing` upgrades older saved options:
     - untouched old defaults (512 / 8,192) move to medium;
     - hand-tuned values stay and become custom, with a budget their batch can hold.
   - `expand_choice` turns a level choice into its three arguments, and raises the logical batch
     if needed. An argument edit without a level becomes custom.
2. **`LlamaOptions`** (`providers/llama_server.py`).
   - New fields: `vision_detail` (default medium) and `image_max_tokens` (70–4096).
   - The defaults for `context_size` (12,288) and `ubatch_size` (1,024) are now the medium level.
   - A validator requires the physical batch to be at least the image budget, which llama.cpp
     needs to encode an image.
   - A level whose arguments no longer match becomes custom.
   - `--image-max-tokens` is passed at launch and accepted by the public argument preview.
3. **Settings** (`runtime/app_settings.py`).
   - "Vision detail" is in the Vision category and applies on model reload. "Image token budget
     (per image)" is in Performance.
   - The save path applies `expand_choice`.
   - The help text carries the disclaimer: "Higher detail increases response times and context
     usage, but SORA reads your screen more reliably and guesses less."
   - The exported `app-settings.schema.json` is refreshed. There is no settings version bump:
     older files load through `fill_missing`.
4. **Desktop overview size follows the budget** (`perception.overview_edge`, used by
   `prompt_images`).
   - The overview's longest edge is chosen so the image just fills the model's token budget,
     at about 2,304 source pixels per token.
   - A larger capture would only be shrunk again by llama.cpp.
   - External model servers keep the fixed 1920 px edge, since their budget is unknown.
5. **Settings page** (`clients/panels/settings/`).
   - A Vision detail card sits at the top of Vision: a Low/Medium/High slider, a level badge,
     the resulting budget and context, and the disclaimer.
   - Moving the slider drafts all three arguments.
   - Editing the image budget, physical batch or context length elsewhere drafts Custom.
   - In Custom the slider shows no handle, so it never looks like a level.

## Verification

- **Fixture/component:**
  - `.\scripts\verify.ps1` ran ruff, mypy (313 files), pytest (1033 passed, 25 skipped, 4
    xfailed) and the panel tests (8 and 33 passed), exit 0.
  - New tests are in `tests/providers/test_vision_detail.py` (8): defaults and argv, loading
    older settings (4 cases), custom detection and the batch rule, level expansion, and a
    controller save cycle.
  - Also new: `test_overview_edge_fills_the_image_token_budget`, and a slider test in
    `clients/panels/tests/settings.test.mjs`.
  - `test_app_settings.py` expectations moved to the new defaults: 131 fields, and a 12,288
    context.
  - The panel fixture `clients/panels/tests/fixtures/settings-projection.json` was regenerated
    from `AppSettingsController(AppSettings()).projection()`.
- **Rendered page:** headless Edge rendered Settings → Vision against the fixture, in the medium
  and custom states. I looked at both screenshots; they are scratch only.
- **Live model:** SORA's own `llama_arguments` were run for each level with E4B
  (`gemma-4-E4B-it-Q4_K_M` with `mmproj-F16`) on port 18879, one desktop overview per level,
  thinking off.

  | Level | Overview | Prompt tokens | Image read time | Reply time | GPU memory |
  |---|---|---|---|---|---|
  | Low | 1236 px, 1.0 MB | 274 | 2.8 s | 3.6 s | +4.5 GB |
  | Medium | 2364 px, 3.1 MB | 1004 | 3.5 s | 4.1 s | +5.2 GB |
  | High | 3344 px, 5.8 MB | 2054 | 5.6 s | 6.5 s | +5.3 GB |

  - The budget was honoured at every level.
  - These are single runs. Reply quality was not scored, because the answers describe the
    owner's screen. Only sizes and timings were printed, and each server was stopped.
- **Not run:**
  - a reload through the real Settings window and Core;
  - an accuracy comparison across levels on a controlled scene;
  - voice turns;
  - hardware and opt-in suites.

  The owner's running SORA and saved settings were not touched.

## Limits and next

- The levels are a first estimate built from one scene. The DeepSeek E4B data puts the
  legibility threshold somewhere between about 300 and 680 tokens, so Medium (1,024) should
  clear it. That needs a scored test on a controlled scene, run several times.
- The high level's context (16,384) holds two 2,048-token images plus conversation. Very long
  conversations with both images may still need more.
- The owner's saved settings move to Medium the next time Core loads them. The model's memory
  use rises with it (measured above at about 0.7 GB more than Low).

HOW_TO_USE.md: updated.
