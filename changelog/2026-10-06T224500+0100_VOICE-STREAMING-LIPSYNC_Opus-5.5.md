# Faster speech, five-vowel lip sync, model port, screen wording

Model name: **Opus 5.5**. Checkpoint **2026-10-06 22:45:00 +01:00**, Europe/London. Status:
**implemented. Component tests and real local TTS/STT checks were run; nothing was run end to end
with the owner's SORA.** This moves [V1](../V1.md) step 3 (voice) forward, and step 2 (screen per
prompt) in a small way.

## Changes

1. **She starts speaking much sooner** (`src/sora/voice/windows_audio.py`).
   - **Before:** Kokoro synthesised up to 350 characters before any sound played, and only
     synthesised the next part after that one was consumed.
   - **Now:** `speech_segments` splits at sentence ends. The first segment is one sentence
     (cut at a clause if over 160 characters), and later segments group sentences, growing
     from 120 to 350 characters.
   - A prefetch task synthesises the next segment while the current one plays, and audio stays
     strictly in order.
   - The voice client now closes the stream when she is interrupted, so no further sentences
     are synthesised (`client.py`).
2. **Fast voice model.** Measured on the owner's PC (i5-14600K, CPU):

   | Model | "Hi there!" takes | Sentence speed |
   |---|---|---|
   | int8 (in use until now) | 2.74 s | 0.46× real time |
   | fp32 `kokoro-v1.0.onnx` | 0.24 s | 5.5× real time |

   - So the int8 model could never keep up with her own speech.
   - `setup-local-voice.ps1` now downloads the fp32 model once (325 MB, SHA-256 checked) next to
     the existing int8 file. `-NoFastVoiceModel` skips the download.
   - `resolve_assets` prefers fp32 when it is present. The owner's settings leave the TTS path
     blank, so it is picked up with no settings change.
3. **Five-vowel lip sync** (new `src/sora/voice/vowels.py`, an idea from Project AIRI; no code
   was copied).
   - For each 100 ms audio chunk, linear prediction gives the first two formants, and their
     distance to typical A/E/I/O/U formants gives five shares that sum to 1. It is pure Python,
     at about 1 ms per chunk.
   - Frames carry `vowels`, and the relay packet validates them (each 0–1, exactly five).
   - The Unity avatar drives VRM `aa/ee/ih/oh/ou`: the strongest vowel opens fully with the
     audio, and the others blend in.
   - Older players ignore the field and keep using `aa` alone.
4. **Model port.** The W0 changelog said a QA profile "shared the owner's model server".
   - **That was wrong.** The QA profile's own log
     (`scratchpad/shell-port/logs/llama-server.log`) shows it started its own llama-server on
     18771, because the owner's SORA had no model running at the time.
   - The real fault was the opposite case: with two profiles running, the second model failed
     to load with an OSError, because both are fixed to 18771.
   - Managed llama.cpp now moves this run to the next free port (up to 20 above the saved one,
     `free_local_port`). It still never attaches to a server it did not start.
5. **Screen wording.**
   - With screen-on-prompt, the automatic screenshot is now labelled for the model as her own
     live view of the screen, which the owner did not send.
   - She calls it the screen or the desktop, never "the image you provided".
   - Owner-attached images are unchanged (`SCREEN_IMAGE_NOTE`, `source="screen"` in
     `dialogue.py`, and the three screen call sites in `service.py`).

## Verification

| Kind | What | Result |
|---|---|---|
| Fixture | `tests/voice/test_streaming_speech.py`. Covers segmenting; first audio before later segments are synthesised; closing stops synthesis; a failed later segment raises after earlier audio; synthetic vowels at two pitches; relay validation | 18 passed |
| Fixture | `tests/voice` | 77 passed, 6 opt-in skipped |
| Fixture | Port tests in `test_managed_llama_server.py`; `test_app_settings.py`; `test_screen_image_label.py` | 32 passed, 2 opt-in skipped |
| Component (real local models) | `SORA_TEST_LOCAL_VOICE=1` real Whisper and Kokoro adapter test, run in `.local/voice-runtime` | 1 passed |
| Component (real Kokoro, fp32) | Simulated real-time playback of a 4-sentence, 13.4 s reply | Repeat runs: first audio 0.23 s and 0.24 s, no gaps. The first, cold run: first audio 1.02 s, 3.9 s of gaps |
| Component (real Kokoro, int8) | Same reply | First audio 0.86 s (it was 19.8 s before this change), but 19.9 s of gaps |
| Component (real Kokoro) | Per-chunk vowels on single words | Tracks the sound: "Oh" glides a→o→u, and "Eee" reads i. American fronted "oo" often reads as e |
| Native (Unity 6000.6 batch mode) | `P14VoicePresentationTests`, including a new five-vowel test | 9 passed |
| Static | ruff and strict mypy (303 files) | Clean |
| Fixture (full) | `scripts/verify.ps1`: ruff, mypy on 306 files, schema check, pytest, compileall, PWA | 1006 passed, 25 skipped, 4 xfailed |

`dotnet test` was not rerun this round; no shell C# changed after the W0 round's 397 passed.

## Also added

`docs/plans/IMAGE_TTFT_RESEARCH_2026-10-06.md`. This is research on faster screen-per-prompt
replies, including measured timings from the QA log. Nothing in it is implemented.

## Not done or not verified

- **Not checked on screen:** the avatar's new mouth shapes. The player was not rebuilt, and the
  owner must run `scripts/build-embodiment.ps1` once.
- **Not checked on the owner's SORA:** the fast model was benchmarked from a scratch copy. The
  owner's folders were not changed, and the download happens when the owner runs setup.
- Her reply still waits for the whole model turn before speaking starts. The companion call is
  constrained JSON, so the speech field cannot be streamed without a parser for partial JSON.
  That is the next latency step.
- When interrupted mid-sentence, the sentence already being synthesised (at most about 4 s of
  CPU with fp32) finishes in its thread before the lock frees.

HOW_TO_USE.md: updated (fast voice model, rebuilding the avatar for mouth shapes, speech starting
sooner, screen wording, the model-port troubleshooting row).
