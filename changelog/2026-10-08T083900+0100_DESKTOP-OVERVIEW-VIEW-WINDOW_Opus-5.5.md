# SORA sees the whole desktop (every monitor) by default and can look closer at one window

Model name: **Opus 5.5**. Checkpoint **2026-10-08 08:39:00 +01:00**, Europe/London. Status:
**implemented and component-tested; overview read live by E4B; full GUI path not run live.** The
owner decided: "The desktop should be the default, including both monitors and then if she decides
to look closer, she can specify a window or the default will return the currently or last used
window." This moves V1 acceptance step 4 (screen awareness) forward.

Before this change, image-on-prompt attached only the most recent non-SORA window, and the model
was told "This is not the entire desktop".

## Changes

1. **Capture helper** (`clients/windows_capture/Program.cs`): a region request may set
   `output_max_edge` (256–4096).
   - The source rectangle may then span several monitors (up to 64 Mpx).
   - The helper scales the image (bicubic) so its longest edge fits, and reports `image_width` and
     `image_height`.
   - `max_pixels` limits the scaled image. Window captures cannot be scaled.
2. **Capture contract** (`src/sora/desktop/capture.py`): `WindowsCaptureRequest.output_max_edge`
   (region only), and `WindowsCaptureReply.image_width` and `image_height`.
3. **`capture_desktop_overview`** (`src/sora/runtime/perception.py`).
   - It takes one capture of the bounding box of all monitors, with the longest edge at 1920 px.
   - It validates the region, size, timestamp and PNG dimensions.
   - It returns the image and a layout line for the model, for example "2 monitors, left to
     right: secondary monitor 1280x1024 (0-25% of the width), primary monitor 3840x2160 (25-100%
     of the width); black areas are outside every monitor".
4. **New companion call `view_window`** (`contracts/companion_call.py`, exported schema
   `companion-call.schema.json`).
   - Its optional `target` is an issued `list_windows` reference. With no target, Core uses the
     window the owner is using or used last before SORA.
   - The prompt tells the model that every reply sees a reduced view of the whole desktop, and
     to use `view_window` to read details.
   - It is a terminal call in the read turn (`runtime/read_turn.py`). A stale reference becomes an
     honest "unavailable" note.
5. **New module `src/sora/runtime/prompt_images.py`** decides what each reply sees, and
   `service.py` calls it in place of the old window-only block.
   - It attaches the desktop overview in image-on-prompt or adaptive mode. Adaptive mode skips
     it when a background summary is in use.
   - On `view_window` it adds a full-resolution window image after the overview. This works in
     every mode, because it is SORA's explicit choice.
   - The overview needs `desktop_capture`; a closer look also needs `desktop_observe`. Pause
     stops both.
   - The new footers are "Automatic desktop image: …" and "Closer window image: …", or their
     "unavailable" forms.
   - `SoraRuntime._current_monitors()` reads the live monitor layout and keeps the avatar's
     topology in step.
6. **Chat chips** (`clients/panels/chat/chat-model.js`): "Looked at the desktop", "Couldn't see
   the desktop", "Looked closer at a window" and "Couldn't look closer". The old window footers
   keep their chips for saved replies.
7. **Settings help text** for perception mode now describes the desktop overview.
8. **HOW_TO_USE.md** (setup step 2) and the **V1.md** "Screen with every prompt" row are updated.

## Verification

- **Fixture/component:**
  - `.\scripts\verify.ps1` ran ruff, mypy (311 files), pytest (1024 passed, 25 skipped, 4
    xfailed) and the panel tests (8 and 32 passed), exit 0.
  - New tests: `test_desktop_overview_covers_every_monitor_scaled`, and
    `test_looking_closer_adds_one_window_to_the_desktop_overview` for both the recent window and a
    stale reference.
  - `test_prompt_mode_and_pause_are_functional` now expects the overview.
  - A new chip test is in `clients/panels/tests/chat-format.test.mjs`.
- **Native:** the rebuilt helper on the owner's machine captured both monitors (5120×2973
  bounding box, from a 3840×2160 primary and a 1280×1024 secondary) as one 2048×1189 image. Only
  sizes were printed; no pixels were saved.
- **Live model:** a temporary llama-server on port 18879 ran E4B
  (`gemma-4-E4B-it-Q4_K_M` with `mmproj-F16`) and was stopped afterwards.
  - Asked about the overview plus its layout line, E4B named the content of each monitor
    correctly.
  - Capture took 0.3 s and the answer 7.8 s, with 365 prompt tokens.
  - This was a single run. The image was not stored, and the answer is not reproduced here
    because it describes the owner's screen.
- **Not run:** the full GUI path (Chat → Core → `view_window` chosen by E4B) in an isolated
  profile, voice turns, and the opt-in native and hardware suites. The owner's running SORA was
  not touched.

## Limits and next

- Whether E4B chooses `view_window` at the right times has not been tested live.
- The overview is about 2 MB of PNG per message. If latency suffers, JPEG or a smaller edge is
  the next step.
- SORA's own Chat window and avatar can appear in the overview. The model is told they are not
  the owner's content. Excluding them from capture would also hide them from the owner's own
  screen recordings, so I did not do that.
- The explicit "what's on my screen" path, `choose_screen_view` with the cursor's monitor only,
  is unchanged. It only runs when no automatic images were attached.

HOW_TO_USE.md: updated.
