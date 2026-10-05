# P14.1 measured voice defaults — GPT-5.6 Sol

Status: **complete 2026-09-18 18:49:20 +01:00**.

P14.1 measures local voice candidates on the actual SORA reference desktop before P14.2 commits the
runtime to a streaming design. The benchmark is repeatable, keeps optional inference dependencies and
model downloads outside the normal Core environment, and does not require LiveKit or a cloud speech
service.

## Reference environment

- Windows 11 Pro 10.0.26200, 64-bit.
- Intel Core i5-14600K: 14 physical cores and 20 logical processors.
- 31.723 GiB physical memory.
- AMD Radeon RX 9070 XT plus Intel UHD Graphics 770. The measured faster-whisper Windows GPU path is
  CUDA/NVIDIA-specific, so this run uses CPU int8 and makes no AMD acceleration claim.
- Python 3.12.10. Each component runs in a fresh worker process.

## Method

- Windows SAPI generates three fixed clean English control utterances. They are used only as a
  deterministic quality fixture and are not retained in versioned source.
- Cold latency starts before model construction and ends after the first complete operation. Model
  downloads happen before the worker starts and are excluded.
- Warm latency is five subsequent identical operations. Reported p50/p95 values use linear
  interpolation. Real-time factor is warm p95 divided by audio duration.
- Resident memory is sampled every 5 ms in the fresh worker. Values are absolute worker RSS, not a
  claimed model-only allocation.
- VAD adds one second of zero-valued audio before and after a 5.633-second control utterance. The
  conservative reference interval includes natural SAPI pauses.
- STT quality is normalized word error rate across all three controls. TTS quality includes clipping,
  sample rate, peak amplitude and a faster-whisper loop-back transcription.
- The strict `VoiceBenchmarkReport` rejects missing components, unmeasured defaults, inconsistent
  percentile/real-time summaries, duplicate metrics, naive timestamps and undeclared fields.

## Measured results

| Component | Candidate and execution | Model files | Cold | Warm p50 / p95 | Warm p95 RTF | Worker loaded / peak RSS | Quality |
|---|---|---:|---:|---:|---:|---:|---|
| VAD | Silero VAD 6.2.2 ONNX, CPUExecutionProvider | 2.22 MiB | 75.047 ms | 28.802 / 30.738 ms | 0.0040 | 248.359 / 248.359 MiB | 0.8166 conservative interval recall; 0 ms speech in the two padded silence regions; 2 detected segments |
| STT | `Systran/faster-whisper-base.en@3d3d5dee26484f91867d81cb899cfcf72b96be6c`, CTranslate2 CPU int8, 6 threads | 140.93 MiB | 1,438.404 ms | 328.233 / 350.339 ms | 0.0622 | 252.348 / 344.574 MiB | 0.000 normalized WER; all 3/3 transcripts exact after normalization |
| TTS | Kokoro-82M v1.0 int8, `af_heart`, ONNX CPUExecutionProvider | 114.99 MiB | 3,706.714 ms | 2,930.936 / 2,975.212 ms | 0.7791 | 304.148 / 383.535 MiB | 0.000 loop-back WER; 24 kHz; 0 clipped samples; 0.4874 peak amplitude |

The TTS figure is whole-utterance synthesis for 3.819 seconds of audio, not time to first playable
audio. P14.2 must measure sentence/chunk streaming before assessing the provisional two-second
first-audio target.

## Model and licence record

- **VAD default:** `silero-vad-6.2.2-onnx-cpu`. The measured ONNX file is 2,327,524 bytes with
  SHA-256 `1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3`. Silero VAD code and model are
  recorded as MIT. P14.2 should prefer a direct ONNX adapter and remeasure memory rather than retain
  PyTorch solely for model loading.
- **STT default:** `faster-whisper-base-en-cpu-int8`. The pinned model snapshot contains six recorded
  files; `model.bin` is 145,216,508 bytes with SHA-256
  `2a166925539a16005f14ff328359f9b9adb9dc4fb631bb3b227526862e93e2ef`. faster-whisper and the
  converted OpenAI Whisper distribution are recorded as MIT.
- **TTS default:** `kokoro-v1.0-onnx-int8`, voice `af_heart`. The model is 92,361,271 bytes with
  SHA-256 `6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb`; the voice archive is
  28,214,398 bytes with SHA-256
  `bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d`. The wrapper is MIT and the
  Kokoro model is Apache-2.0.

The executable benchmark pins the two directly downloaded Kokoro digests and fails closed if an
existing or newly downloaded file differs. The faster-whisper report pins the resolved repository
revision and every snapshot file digest. The complete file list, sources, hashes and licence labels
are retained in [`p14-voice/benchmark.json`](p14-voice/benchmark.json).

## Decision and P14.2 boundary

Measured defaults are:

1. Silero VAD 6.2 ONNX on CPU for streaming speech detection.
2. faster-whisper `base.en` using CPU int8 and six threads for the initial English local STT path.
3. Kokoro v1.0 ONNX int8 with `af_heart` for the initial local English TTS path.

These are local defaults, not universal compatibility promises. P14.2 must keep model selection
configurable, add real microphone/device-loss/echo fixtures, avoid persisting partial transcripts or
raw microphone streams by default, and remeasure end-of-utterance to first-audio latency. A future
multilingual model, AMD-capable backend or alternative voice must pass the same evidence contract.
LiveKit remains deferred until measured transport needs justify it.

## Limitations

- Synthetic clean English speech does not establish microphone, accent, background-noise, far-field,
  overlapping-speaker or echo-cancellation quality.
- Zero loop-back WER establishes intelligibility on the fixed phrase, not subjective naturalness.
- Only one VAD model family, one English STT size and one TTS voice/precision were selected for this
  foundational benchmark. The report does not claim an exhaustive vendor comparison.
- The benchmark did not open a microphone, play audio through speakers, contact a speech cloud, run a
  live dialogue provider or exercise lip sync. Those are later P14 gates.

## Verification

| Gate | Result |
|---|---|
| Isolated measured benchmark | Complete VAD/STT/TTS report and 183,340-byte PCM TTS sample |
| Voice acceptance/models | 5 passed |
| Repository | 307 passed, 10 explicit opt-in native/Unity skips |
| Static/contracts | Ruff passed including the optional benchmark runner; strict mypy passed across 167 source files; schemas fresh; compileall passed |

P14.2 streaming voice sessions is next. No commit, tag or staging operation was performed.
