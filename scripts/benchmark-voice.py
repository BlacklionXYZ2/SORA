"""Run the measured P14.1 local VAD/STT/TTS decision benchmark.

Run through an isolated dependency environment so the optional voice candidates do not become
dependencies of SORA Core::

    uv run --isolated --python 3.12 \
      --with "silero-vad[onnx-cpu]>=6.2,<7" \
      --with "faster-whisper>=1.2,<2" \
      --with "kokoro-onnx>=0.6,<1" \
      --with "soundfile>=0.13,<1" --with "psutil>=7,<8" \
      python scripts/benchmark-voice.py

Each component runs in a fresh child process. Cold latency therefore includes model construction and
the first operation; warm latency measures five subsequent identical operations.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import psutil

from sora.voice import (
    BenchmarkMetric,
    DefaultSelection,
    HardwareProfile,
    LatencyProfile,
    MemoryProfile,
    ModelArtifact,
    VoiceBenchmarkReport,
    VoiceComponentBenchmark,
    percentile,
    word_error_rate,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORK_DIR = ROOT / ".local" / "p14-voice-benchmark"
DEFAULT_REPORT = ROOT / "docs" / "verification" / "p14-voice" / "benchmark.json"
DEFAULT_TTS_SAMPLE = ROOT / "docs" / "verification" / "p14-voice" / "tts-sample.wav"
KOKORO_MODEL_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
    "model-files-v1.0/kokoro-v1.0.int8.onnx"
)
KOKORO_VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
)
KOKORO_MODEL_SHA256 = "6e742170d309016e5891a994e1ce1559c702a2ccd0075e67ef7157974f6406cb"
KOKORO_VOICES_SHA256 = "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"
WHISPER_MODEL = "Systran/faster-whisper-base.en"
CORPUS = (
    "Sora, please open the project notes and show me the latest result.",
    "Stop speaking, but keep the coding task running in the background.",
    "This button here is the one I meant, not the window beside it.",
)


class RssSampler:
    """Sample process RSS frequently enough to catch native-inference allocations."""

    def __init__(self) -> None:
        self._process = psutil.Process()
        self._stop = threading.Event()
        self._samples: list[int] = []
        self._thread = threading.Thread(target=self._run, daemon=True)

    def __enter__(self) -> RssSampler:
        self._samples.append(self._process.memory_info().rss)
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        self._thread.join(timeout=1)
        self._samples.append(self._process.memory_info().rss)

    @property
    def peak_mib(self) -> float:
        return round(max(self._samples, default=0) / (1024 * 1024), 3)

    def _run(self) -> None:
        while not self._stop.wait(0.005):
            self._samples.append(self._process.memory_info().rss)


def elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def rss_mib() -> float:
    return round(psutil.Process().memory_info().rss / (1024 * 1024), 3)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(
    path: Path,
    *,
    relative_path: str,
    license_name: str,
    source_url: str,
) -> ModelArtifact:
    return ModelArtifact(
        name=path.name,
        relative_path=relative_path,
        size_bytes=path.stat().st_size,
        sha256=sha256(path),
        license=license_name,
        source_url=source_url,
    )


def download(url: str, destination: Path, *, expected_sha256: str) -> None:
    if destination.is_file() and destination.stat().st_size:
        if sha256(destination) != expected_sha256:
            raise RuntimeError(
                f"cached model digest does not match the pinned value: {destination}"
            )
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    request = urllib.request.Request(url, headers={"User-Agent": "SORA-P14-voice-benchmark/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as out:
            while block := response.read(1024 * 1024):
                out.write(block)
        if sha256(temporary) != expected_sha256:
            raise RuntimeError(f"downloaded model digest does not match the pinned value: {url}")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def generate_sapi_corpus(corpus_dir: Path) -> tuple[Path, ...]:
    corpus_dir.mkdir(parents=True, exist_ok=True)
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$speaker.Rate = 0; $speaker.Volume = 100; "
        "$speaker.SetOutputToWaveFile($env:SORA_BENCH_WAV); "
        "$speaker.Speak($env:SORA_BENCH_TEXT); $speaker.Dispose()"
    )
    paths: list[Path] = []
    for index, text in enumerate(CORPUS, start=1):
        path = corpus_dir / f"sapi-{index}.wav"
        environment = os.environ.copy()
        environment["SORA_BENCH_WAV"] = str(path)
        environment["SORA_BENCH_TEXT"] = text
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            check=True,
            env=environment,
            capture_output=True,
            text=True,
        )
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Windows SAPI did not produce {path}")
        paths.append(path)
    return tuple(paths)


def fresh_worker(component: str, work_dir: Path, tts_sample: Path) -> dict[str, Any]:
    output = work_dir / f"{component}-worker.json"
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--worker",
        component,
        "--work-dir",
        str(work_dir),
        "--tts-sample",
        str(tts_sample),
        "--worker-output",
        str(output),
    ]
    subprocess.run(command, check=True)
    return cast(dict[str, Any], json.loads(output.read_text(encoding="utf-8")))


def benchmark_vad(work_dir: Path) -> dict[str, Any]:
    import numpy as np
    import soundfile as sf
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad

    source_audio, source_rate = sf.read(work_dir / "corpus" / "sapi-1.wav", dtype="float32")
    source_audio = np.asarray(source_audio, dtype=np.float32)
    if source_audio.ndim == 2:
        source_audio = source_audio.mean(axis=1)
    if source_rate != 16_000:
        new_length = round(len(source_audio) * 16_000 / source_rate)
        source_audio = np.interp(
            np.linspace(0, len(source_audio) - 1, new_length),
            np.arange(len(source_audio)),
            source_audio,
        ).astype(np.float32)
    silence = np.zeros(16_000, dtype=np.float32)
    evaluation_audio = np.concatenate((silence, source_audio, silence))
    tensor = torch.from_numpy(evaluation_audio)
    duration_seconds = len(evaluation_audio) / 16_000
    reference_start = 1.0
    reference_end = 1.0 + len(source_audio) / 16_000

    baseline = rss_mib()
    started = time.perf_counter()
    with RssSampler() as sampler:
        model = load_silero_vad(onnx=True, opset_version=16)
        timestamps = get_speech_timestamps(tensor, model, sampling_rate=16_000, return_seconds=True)
        cold_ms = elapsed_ms(started)
        loaded = rss_mib()
        warm: list[float] = []
        for _ in range(5):
            started = time.perf_counter()
            timestamps = get_speech_timestamps(
                tensor, model, sampling_rate=16_000, return_seconds=True
            )
            warm.append(elapsed_ms(started))

    intervals = [(float(item["start"]), float(item["end"])) for item in timestamps]
    speech_overlap = sum(
        max(0.0, min(end, reference_end) - max(start, reference_start)) for start, end in intervals
    )
    false_positive = sum(
        max(0.0, min(end, reference_start) - start) + max(0.0, end - max(start, reference_end))
        for start, end in intervals
    )
    model_path = Path(importlib_path("silero_vad")) / "data" / "silero_vad.onnx"
    return {
        "component": "vad",
        "candidate_id": "silero-vad-6.2.2-onnx-cpu",
        "implementation_version": importlib.metadata.version("silero-vad"),
        "execution_provider": "ONNX Runtime CPUExecutionProvider",
        "model_name": "Silero VAD v6.2 ONNX opset 16",
        "software_license": "MIT",
        "model_license": "MIT",
        "artifacts": [
            artifact(
                model_path,
                relative_path="python-environment/silero_vad/data/silero_vad.onnx",
                license_name="MIT",
                source_url=(
                    "https://github.com/snakers4/silero-vad/blob/"
                    "v6.2.2/src/silero_vad/data/silero_vad.onnx"
                ),
            ).model_dump(mode="json")
        ],
        "latency": latency(cold_ms, warm, duration_seconds),
        "memory": memory(baseline, loaded, sampler.peak_mib),
        "quality": [
            metric(
                "speech_interval_recall",
                speech_overlap / (reference_end - reference_start),
                "ratio",
                "Overlap with the known SAPI speech interval; higher is better.",
            ),
            metric(
                "padded_silence_false_positive_ms",
                false_positive * 1000,
                "ms",
                "Speech attributed to the one-second silence pads; lower is better.",
            ),
            metric(
                "detected_segments",
                len(intervals),
                "count",
                "Number of segments found in one clean utterance with silence pads.",
            ),
        ],
        "limitations": [
            "Quality fixture is clean synthetic Windows SAPI speech, not microphone speech "
            "or noise."
        ],
    }


def benchmark_stt(work_dir: Path) -> dict[str, Any]:
    from faster_whisper import WhisperModel

    model_root = work_dir / "models" / "stt"
    first_clip = work_dir / "corpus" / "sapi-1.wav"
    baseline = rss_mib()
    started = time.perf_counter()
    with RssSampler() as sampler:
        model = WhisperModel(
            WHISPER_MODEL,
            device="cpu",
            compute_type="int8",
            cpu_threads=6,
            num_workers=1,
            download_root=str(model_root),
        )
        transcribe(model, first_clip)
        cold_ms = elapsed_ms(started)
        loaded = rss_mib()
        warm: list[float] = []
        for _ in range(5):
            started = time.perf_counter()
            transcribe(model, first_clip)
            warm.append(elapsed_ms(started))
        hypotheses = [
            transcribe(model, work_dir / "corpus" / f"sapi-{index}.wav")
            for index in range(1, len(CORPUS) + 1)
        ]

    import soundfile as sf

    first_audio, first_rate = sf.read(first_clip)
    duration_seconds = len(first_audio) / first_rate
    errors = [
        word_error_rate(reference, hypothesis)
        for reference, hypothesis in zip(CORPUS, hypotheses, strict=True)
    ]
    revision_file = model_root / "models--Systran--faster-whisper-base.en" / "refs" / "main"
    revision = revision_file.read_text(encoding="utf-8").strip()
    snapshot_root = revision_file.parent.parent / "snapshots" / revision
    files = sorted(path for path in snapshot_root.iterdir() if path.is_file())
    return {
        "component": "stt",
        "candidate_id": "faster-whisper-base-en-cpu-int8",
        "implementation_version": importlib.metadata.version("faster-whisper"),
        "execution_provider": "CTranslate2 CPU int8, 6 threads",
        "model_name": f"{WHISPER_MODEL}@{revision}",
        "software_license": "MIT",
        "model_license": "MIT (OpenAI Whisper; converted distribution)",
        "artifacts": [
            artifact(
                path,
                relative_path=f".local/p14-voice-benchmark/models/stt/{path.relative_to(model_root).as_posix()}",
                license_name="MIT",
                source_url=f"https://huggingface.co/{WHISPER_MODEL}/tree/{revision}",
            ).model_dump(mode="json")
            for path in files
        ],
        "latency": latency(cold_ms, warm, duration_seconds),
        "memory": memory(baseline, loaded, sampler.peak_mib),
        "quality": [
            metric(
                "corpus_word_error_rate",
                sum(errors) / len(errors),
                "ratio",
                "Case/punctuation-insensitive WER across three clean SAPI utterances; "
                "lower is better.",
            ),
            metric(
                "exact_transcripts",
                sum(error == 0 for error in errors),
                "count",
                "Utterances transcribed with zero normalized word errors; higher is better.",
            ),
        ],
        "transcripts": hypotheses,
        "limitations": [
            "Quality corpus is clean synthetic Windows SAPI speech and does not measure "
            "accents, noise, or far-field microphones.",
            "The Windows faster-whisper GPU path requires NVIDIA CUDA; this AMD host was "
            "measured on CPU.",
        ],
    }


def benchmark_tts(work_dir: Path, tts_sample: Path) -> dict[str, Any]:
    import numpy as np
    import soundfile as sf
    from faster_whisper import WhisperModel
    from kokoro_onnx import Kokoro

    model_path = work_dir / "models" / "tts" / "kokoro-v1.0.int8.onnx"
    voices_path = work_dir / "models" / "tts" / "voices-v1.0.bin"
    baseline = rss_mib()
    started = time.perf_counter()
    with RssSampler() as sampler:
        model = Kokoro(str(model_path), str(voices_path))
        samples, sample_rate = model.create(CORPUS[0], voice="af_heart", speed=1.0, lang="en-us")
        cold_ms = elapsed_ms(started)
        loaded = rss_mib()
        warm: list[float] = []
        for _ in range(5):
            started = time.perf_counter()
            samples, sample_rate = model.create(
                CORPUS[0], voice="af_heart", speed=1.0, lang="en-us"
            )
            warm.append(elapsed_ms(started))
    samples = np.asarray(samples, dtype=np.float32)
    tts_sample.parent.mkdir(parents=True, exist_ok=True)
    sf.write(tts_sample, samples, sample_rate, subtype="PCM_16")
    duration_seconds = len(samples) / sample_rate

    # Loop-back intelligibility is measured after the TTS latency/RSS window has closed, so loading
    # Whisper here cannot inflate the recorded TTS result.
    whisper = WhisperModel(
        WHISPER_MODEL,
        device="cpu",
        compute_type="int8",
        cpu_threads=6,
        num_workers=1,
        download_root=str(work_dir / "models" / "stt"),
        local_files_only=True,
    )
    loopback = transcribe(whisper, tts_sample)
    return {
        "component": "tts",
        "candidate_id": "kokoro-v1.0-onnx-int8",
        "implementation_version": importlib.metadata.version("kokoro-onnx"),
        "execution_provider": "ONNX Runtime CPUExecutionProvider",
        "model_name": "Kokoro-82M v1.0 int8, af_heart",
        "software_license": "MIT",
        "model_license": "Apache-2.0",
        "artifacts": [
            artifact(
                model_path,
                relative_path=".local/p14-voice-benchmark/models/tts/kokoro-v1.0.int8.onnx",
                license_name="Apache-2.0",
                source_url=KOKORO_MODEL_URL,
            ).model_dump(mode="json"),
            artifact(
                voices_path,
                relative_path=".local/p14-voice-benchmark/models/tts/voices-v1.0.bin",
                license_name="Apache-2.0",
                source_url=KOKORO_VOICES_URL,
            ).model_dump(mode="json"),
        ],
        "latency": latency(cold_ms, warm, duration_seconds),
        "memory": memory(baseline, loaded, sampler.peak_mib),
        "quality": [
            metric(
                "loopback_word_error_rate",
                word_error_rate(CORPUS[0], loopback),
                "ratio",
                "faster-whisper base.en normalized WER on generated audio; lower is better.",
            ),
            metric(
                "peak_absolute_amplitude",
                float(np.max(np.abs(samples))),
                "ratio",
                "Peak floating-point sample magnitude; values above one would clip.",
            ),
            metric(
                "clipped_sample_ratio",
                float(np.mean(np.abs(samples) >= 0.999)),
                "ratio",
                "Samples at digital full scale; lower is better.",
            ),
            metric(
                "sample_rate",
                sample_rate,
                "Hz",
                "Generated PCM sample rate.",
            ),
        ],
        "loopback_transcript": loopback,
        "limitations": [
            "Loop-back WER measures intelligibility, not human-rated naturalness or voice "
            "preference.",
            "Only the English af_heart voice and one utterance were latency-tested.",
        ],
    }


def transcribe(model: Any, path: Path) -> str:
    segments, _info = model.transcribe(
        str(path),
        language="en",
        beam_size=1,
        vad_filter=False,
        condition_on_previous_text=False,
    )
    return " ".join(segment.text.strip() for segment in segments).strip()


def importlib_path(package: str) -> str:
    module = __import__(package)
    return str(Path(module.__file__).resolve().parent)


def latency(cold_ms: float, warm: list[float], audio_seconds: float) -> dict[str, Any]:
    p95 = percentile(warm, 95)
    return LatencyProfile(
        cold_ms=cold_ms,
        warm_samples_ms=tuple(warm),
        warm_p50_ms=percentile(warm, 50),
        warm_p95_ms=p95,
        workload_audio_seconds=round(audio_seconds, 6),
        warm_p95_realtime_factor=round(p95 / 1000 / audio_seconds, 6),
    ).model_dump(mode="json")


def memory(baseline: float, loaded: float, peak: float) -> dict[str, Any]:
    return MemoryProfile(
        baseline_rss_mib=baseline,
        loaded_rss_mib=loaded,
        peak_rss_mib=max(peak, baseline, loaded),
    ).model_dump(mode="json")


def metric(name: str, value: float, unit: str, interpretation: str) -> dict[str, Any]:
    return BenchmarkMetric(
        name=name,
        value=round(float(value), 6),
        unit=unit,
        interpretation=interpretation,
    ).model_dump(mode="json")


def hardware_profile() -> HardwareProfile:
    script = (
        "$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1; "
        "$os = Get-CimInstance Win32_OperatingSystem; "
        "$gpus = @(Get-CimInstance Win32_VideoController | ForEach-Object Name); "
        "[pscustomobject]@{cpu=$cpu.Name; os=$os.Caption + ' ' + $os.Version; "
        "arch=$os.OSArchitecture; gpus=$gpus} | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    facts = json.loads(completed.stdout)
    gpu_names = facts["gpus"] if isinstance(facts["gpus"], list) else [facts["gpus"]]
    return HardwareProfile(
        operating_system=facts["os"],
        architecture=facts["arch"],
        cpu=facts["cpu"],
        physical_cores=psutil.cpu_count(logical=False) or 1,
        logical_cores=psutil.cpu_count(logical=True) or 1,
        memory_gib=round(psutil.virtual_memory().total / (1024**3), 3),
        accelerators=tuple(str(name) for name in gpu_names),
    )


def build_report(work_dir: Path, report_path: Path, tts_sample: Path) -> None:
    from huggingface_hub import snapshot_download

    generate_sapi_corpus(work_dir / "corpus")
    tts_dir = work_dir / "models" / "tts"
    download(
        KOKORO_MODEL_URL,
        tts_dir / "kokoro-v1.0.int8.onnx",
        expected_sha256=KOKORO_MODEL_SHA256,
    )
    download(
        KOKORO_VOICES_URL,
        tts_dir / "voices-v1.0.bin",
        expected_sha256=KOKORO_VOICES_SHA256,
    )
    # Resolve the public model snapshot before spawning the STT worker. Network transfer is setup,
    # not cold-start latency; the worker still starts from a fresh process and loads the model once.
    snapshot_download(repo_id=WHISPER_MODEL, cache_dir=work_dir / "models" / "stt")

    raw_results = [
        fresh_worker(component, work_dir, tts_sample) for component in ("vad", "stt", "tts")
    ]
    # Worker-only diagnostic fields are useful in the report methodology but are not component
    # contract fields.
    transcripts = raw_results[1].pop("transcripts")
    loopback = raw_results[2].pop("loopback_transcript")
    results = tuple(VoiceComponentBenchmark.model_validate(raw) for raw in raw_results)
    reasons = {
        "vad": (
            "Small streaming ONNX model; measured well below real time on CPU and avoids a "
            "hardware-specific GPU requirement."
        ),
        "stt": (
            "The measured base.en CPU-int8 model provides an English quality/latency baseline on "
            "this AMD Windows host; larger or multilingual models remain an explicit later choice."
        ),
        "tts": (
            "The measured int8 Kokoro model is local, intelligible in loop-back, compact relative "
            "to full precision, and requires no realtime service."
        ),
    }
    report = VoiceBenchmarkReport(
        measured_at=datetime.now(UTC).astimezone(),
        hardware=hardware_profile(),
        corpus=CORPUS,
        results=results,
        defaults=tuple(
            DefaultSelection(
                component=result.component,
                candidate_id=result.candidate_id,
                reason=reasons[result.component],
            )
            for result in results
        ),
        methodology=(
            "Each component ran in a fresh Python child process on the recorded host.",
            "Cold latency includes model construction plus the first operation; warm latency is "
            "five subsequent identical operations.",
            "RSS was sampled every five milliseconds from the isolated worker process.",
            "VAD and STT quality used three deterministic Windows SAPI English utterances; the "
            "VAD fixture added one second of silence at each edge.",
            f"STT normalized hypotheses: {json.dumps(transcripts, ensure_ascii=False)}",
            f"Kokoro loop-back transcript: {loopback}",
            "No LiveKit server, cloud speech API, CUDA compatibility layer, or persistent "
            "microphone recording was used.",
        ),
        limitations=(
            "The corpus is synthetic, clean, English-only speech; microphone, accent, noise and "
            "conversational overlap evaluation remains part of P14.2.",
            "Kokoro naturalness was not assigned a subjective score; the recorded metrics "
            "establish technical validity and loop-back intelligibility.",
            "Windows faster-whisper exposes CUDA acceleration for NVIDIA hardware, so the "
            "installed AMD GPU was not claimed as an STT accelerator.",
        ),
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(report_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--tts-sample", type=Path, default=DEFAULT_TTS_SAMPLE)
    parser.add_argument("--worker", choices=("vad", "stt", "tts"))
    parser.add_argument("--worker-output", type=Path)
    args = parser.parse_args()
    if args.worker:
        if args.worker_output is None:
            parser.error("--worker-output is required with --worker")
        workers = {"vad": benchmark_vad, "stt": benchmark_stt}
        if args.worker == "tts":
            payload = benchmark_tts(args.work_dir, args.tts_sample)
        else:
            payload = workers[args.worker](args.work_dir)
        args.worker_output.parent.mkdir(parents=True, exist_ok=True)
        args.worker_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return
    build_report(args.work_dir, args.report, args.tts_sample)


if __name__ == "__main__":
    main()
