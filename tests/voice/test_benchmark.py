"""P14.1 voice benchmark evidence-model tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

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

ROOT = Path(__file__).resolve().parents[2]


def artifact(component: str) -> ModelArtifact:
    return ModelArtifact(
        name=f"{component}.onnx",
        relative_path=f"models/{component}.onnx",
        size_bytes=42,
        sha256="a" * 64,
        license="MIT",
        source_url="https://example.invalid/model",
    )


def result(component: str) -> VoiceComponentBenchmark:
    samples = (10.0, 12.0, 14.0)
    return VoiceComponentBenchmark(
        component=component,  # type: ignore[arg-type]
        candidate_id=f"candidate-{component}",
        implementation_version="1.0",
        execution_provider="cpu",
        model_name=f"model-{component}",
        software_license="MIT",
        model_license="MIT",
        artifacts=(artifact(component),),
        latency=LatencyProfile(
            cold_ms=100,
            warm_samples_ms=samples,
            warm_p50_ms=percentile(samples, 50),
            warm_p95_ms=percentile(samples, 95),
            workload_audio_seconds=1,
            warm_p95_realtime_factor=percentile(samples, 95) / 1000,
        ),
        memory=MemoryProfile(baseline_rss_mib=20, loaded_rss_mib=25, peak_rss_mib=30),
        quality=(
            BenchmarkMetric(
                name="fixture_score",
                value=1,
                unit="ratio",
                interpretation="Deterministic fixture result.",
            ),
        ),
    )


def report() -> VoiceBenchmarkReport:
    results = tuple(result(component) for component in ("vad", "stt", "tts"))
    return VoiceBenchmarkReport(
        measured_at=datetime.now(UTC),
        hardware=HardwareProfile(
            operating_system="Windows",
            architecture="x64",
            cpu="fixture",
            physical_cores=1,
            logical_cores=2,
            memory_gib=8,
            accelerators=("CPU",),
        ),
        corpus=("one", "two", "three"),
        results=results,
        defaults=tuple(
            DefaultSelection(
                component=component,  # type: ignore[arg-type]
                candidate_id=f"candidate-{component}",
                reason="The fixture candidate was measured.",
            )
            for component in ("vad", "stt", "tts")
        ),
        methodology=("fixture",),
    )


def test_report_requires_complete_measured_defaults() -> None:
    model = report()
    assert [selection.component for selection in model.defaults] == ["vad", "stt", "tts"]
    with pytest.raises(ValidationError, match="default must reference"):
        model.model_copy(
            update={
                "defaults": (
                    DefaultSelection(
                        component="vad", candidate_id="unmeasured", reason="not measured"
                    ),
                    *model.defaults[1:],
                )
            }
        ).model_validate(
            model.model_copy(
                update={
                    "defaults": (
                        DefaultSelection(
                            component="vad", candidate_id="unmeasured", reason="not measured"
                        ),
                        *model.defaults[1:],
                    )
                }
            ).model_dump()
        )


def test_report_rejects_partial_or_extra_fields() -> None:
    payload = report().model_dump(mode="json")
    payload["results"] = payload["results"][:2]
    with pytest.raises(ValidationError, match="at least 3 items"):
        VoiceBenchmarkReport.model_validate(payload)
    payload = report().model_dump(mode="json")
    payload["authority"] = "granted"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        VoiceBenchmarkReport.model_validate(payload)


def test_latency_summary_must_match_samples() -> None:
    with pytest.raises(ValidationError, match="warm_p95_ms"):
        LatencyProfile(
            cold_ms=1,
            warm_samples_ms=(1, 2, 3),
            warm_p50_ms=2,
            warm_p95_ms=999,
        )


def test_word_error_rate_is_punctuation_insensitive() -> None:
    assert word_error_rate("Hello, SORA!", "hello sora") == 0
    assert word_error_rate("one two three", "one three") == pytest.approx(1 / 3, abs=1e-6)


def test_recorded_host_benchmark_is_complete_and_has_audio_evidence() -> None:
    report_path = ROOT / "docs" / "verification" / "p14-voice" / "benchmark.json"
    sample_path = ROOT / "docs" / "verification" / "p14-voice" / "tts-sample.wav"
    model = VoiceBenchmarkReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    assert {result.component for result in model.results} == {"vad", "stt", "tts"}
    assert all(selection.measured for selection in model.defaults)
    assert all(not selection.requires_livekit for selection in model.defaults)
    assert sample_path.stat().st_size > 44
