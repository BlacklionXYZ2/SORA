# Spoken replies start while she is still thinking; companion calls stop running away

Model name: **Opus 5.5**. Checkpoint **2026-10-07 08:15:00 +01:00**, Europe/London. Status:
**implemented, and measured against real models in isolated QA. The owner's running SORA was not
touched.** This moves [V1](../V1.md) step 3 (voice) forward. It follows recommendations 1 and 2
of [the TTFT research](../docs/plans/IMAGE_TTFT_RESEARCH_2026-10-06.md), at the owner's
request ("go ahead").

## What changed

1. **Companion calls no longer run to 1,024 tokens** (`providers/dialogue.py`).
   - **Cause, measured on E2B:** Gemma 4 sometimes opens a thought channel on its own, even with
     thinking off. llama.cpp holds the JSON grammar back until that channel closes, and the model
     often writes a malformed closing tag (`</|channel>`). So the grammar never starts, and the call
     runs to its cap with no JSON.
   - Per-request `reasoning_format`, `reasoning_budget`, `thinking_budget_tokens`, server-wide
     `--reasoning off` and banning the channel token did not help.
   - **Fix:** on SORA's own managed llama.cpp server (`llama_native=True`, set in
     `app_settings._launch`), schema-constrained calls render the same messages with the model's
     template (`/apply-template`, thinking off) and send them to `/completion` with `json_schema`.
     The grammar then applies from the first token.
   - External servers such as LM Studio keep Chat Completions.
2. **Voice replies are spoken while they are written.**
   - Core streams the free-text reply (`stream_reply`, SSE) and splits it into sentences
     (`voice/speech_stream.py`).
   - The session coordinator opens the playback at the first sentence (`speech_sentence`,
     `finish_speech`, `wait_speech` in `voice/sessions.py`).
   - The voice worker long-polls the new `GET /api/v1/voice/sessions/{id}/speech?utterance_id=…&after=N`
     (new public contract `voice-speech-preview`, exported). It feeds sentences into Kokoro's
     prefetching pipeline under the same playback, so playback events, lip sync, echo suppression
     and interruption work as before.
   - When the turn finishes, Core returns that same playback, so nothing is spoken twice.
   - An interrupted reply offers no more sentences and is not spoken again at the end.
   - Turns that are not model text (motion receipts, voice controls) are spoken as before.
3. **Spoken replies are short.**
   - Voice turns add `VOICE_REPLY_NOTE` to the reply context: one to three short sentences of
     plain speech, with no markdown or lists.
   - With E4B and the full screen attached, replies went from 224–2,069 characters (2.3–5.2 s) to
     133–166 characters (1.3–1.5 s).
   - Since only the model's own text is streamed to speech, Core's evidence footers ("Automatic
     window image: …") are no longer read aloud on these turns.
4. **Windows power throttling.**
   - Windows 11 moves the windowless voice worker to efficiency cores. Kokoro then took 2.3–2.9 s
     per sentence from the third request onward, instead of 0.7 s.
   - The worker now opts out at start (`keep_full_cpu_speed`).
   - llama-server was measured and is not affected (it runs on the GPU).
5. **The first spoken piece is cut at a clause near 90 characters** (it was 160), because
   synthesis time grows faster than linearly with length. Later sentences stay whole.

## Measurements (isolated QA in `.local/latency-qa-20261007/`, own llama-server on port 18871)

**Companion calls, through SORA's provider, 16 prompts each:**

| Model | Path | Valid | Median | Worst | Total |
|---|---|---|---|---|---|
| E2B | before | 12/16 | 1.18 s | 10.86 s | 51.6 s |
| E2B | after | 16/16 | 0.38 s | 0.47 s | 6.3 s |
| E4B | before | 16/16 | 0.81 s | 3.10 s | 16.3 s |
| E4B | after | 16/16 | 0.45 s | 0.53 s | 7.3 s |

The choices were the same on both paths (on E2B, the same answer for "What did I say about my exam
yesterday?" was wrong both times).

**End to end (component):**
- **Setup:** real Core HTTP server, real E4B (warm), the real `HttpVoiceTransport`, and real
  Kokoro fp32 with the opt-out. The speaker was a recording fake that plays in real time.
- **Measured:** time from the final transcript to the first audio.

| Question | First audio | Core's turn finished |
|---|---|---|
| "How's your day going? Tell me something fun." | 1.58 s | 3.75 s |
| "Can you explain what a black hole is?" | 2.23 s | 2.85 s |
| "What should I cook for dinner tonight?" | 1.74 s | 2.12 s |

The first request after a model loads is about 3 s slower: llama-server warm-up, not SORA.

## Verification

| Kind | What | Result |
|---|---|---|
| Fixture | `tests/providers/test_constrained_completion.py` (4) and `tests/voice/test_streamed_reply_speech.py` (9). The second covers: speaking before commit; same playback kept; interruption; a different utterance; sentence splitting; SSE parsing | All passed |
| Fixture | `tests/voice` | 86 passed, 6 opt-in skipped |
| Component (real models) | The tables above | As shown |
| Static | ruff, strict mypy (307 files); contracts exported | Clean |
| Fixture (full) | `scripts/verify.ps1` | 1019 passed, 25 skipped, 4 xfailed; PWA 10/10 |

## Not done or not verified

- **Not run:** with a real microphone and speaker, in the owner's SORA, or with the installed
  voice worker process.
- **Not run on a real model:** the screen-on-prompt image path through the new streaming reply.
  It is covered by fixtures only; the image streaming request itself was measured in the
  latency script.
- When the read turn (companion call) runs first, its time comes before the first sentence.
  These QA turns used a runtime without companion settings, so they had no read turn. With
  the fix in item 1, a read turn adds about 0.4–0.5 s per call.

HOW_TO_USE.md: updated (talking section: when she starts speaking, short spoken answers).
