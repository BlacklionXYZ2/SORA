"""Strict, reusable evidence models for the P14.1 voice benchmark."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from sora.contracts.base import StrictModel, require_aware

VoiceComponent = Literal["vad", "stt", "tts"]


class HardwareProfile(StrictModel):
    """Hardware and operating-system facts captured with a benchmark run."""

    operating_system: str = Field(min_length=1, max_length=256)
    architecture: str = Field(min_length=1, max_length=64)
    cpu: str = Field(min_length=1, max_length=256)
    physical_cores: int = Field(ge=1, le=1024)
    logical_cores: int = Field(ge=1, le=2048)
    memory_gib: float = Field(gt=0, le=16_384)
    accelerators: tuple[str, ...] = Field(min_length=1, max_length=16)


class ModelArtifact(StrictModel):
    """A measured local model file with an auditable origin and licence."""

    name: str = Field(min_length=1, max_length=256)
    relative_path: str = Field(min_length=1, max_length=1024)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license: str = Field(min_length=1, max_length=128)
    source_url: str = Field(min_length=1, max_length=2048)


class LatencyProfile(StrictModel):
    """Cold and warm wall-clock latency measured on one workload."""

    cold_ms: float = Field(ge=0)
    warm_samples_ms: tuple[float, ...] = Field(min_length=3, max_length=100)
    warm_p50_ms: float = Field(ge=0)
    warm_p95_ms: float = Field(ge=0)
    workload_audio_seconds: float | None = Field(default=None, gt=0)
    warm_p95_realtime_factor: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_summary(self) -> LatencyProfile:
        expected_p50 = percentile(self.warm_samples_ms, 50)
        expected_p95 = percentile(self.warm_samples_ms, 95)
        if abs(self.warm_p50_ms - expected_p50) > 0.01:
            raise ValueError("warm_p50_ms does not summarize warm_samples_ms")
        if abs(self.warm_p95_ms - expected_p95) > 0.01:
            raise ValueError("warm_p95_ms does not summarize warm_samples_ms")
        if self.warm_p95_realtime_factor is not None:
            if self.workload_audio_seconds is None:
                raise ValueError("realtime factor requires workload_audio_seconds")
            expected_rtf = self.warm_p95_ms / 1000 / self.workload_audio_seconds
            if abs(self.warm_p95_realtime_factor - expected_rtf) > 0.001:
                raise ValueError("warm_p95_realtime_factor does not match latency and workload")
        return self


class MemoryProfile(StrictModel):
    """Resident-memory observations for the benchmark process."""

    baseline_rss_mib: float = Field(ge=0)
    loaded_rss_mib: float = Field(ge=0)
    peak_rss_mib: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_order(self) -> MemoryProfile:
        if self.peak_rss_mib < max(self.baseline_rss_mib, self.loaded_rss_mib):
            raise ValueError("peak RSS cannot be below baseline or loaded RSS")
        return self


class BenchmarkMetric(StrictModel):
    """Named quality or throughput measurement with explicit interpretation."""

    name: str = Field(min_length=1, max_length=128)
    value: float
    unit: str = Field(min_length=1, max_length=64)
    interpretation: str = Field(min_length=1, max_length=512)


class VoiceComponentBenchmark(StrictModel):
    """Measured result for one VAD, STT, or TTS candidate."""

    component: VoiceComponent
    candidate_id: str = Field(min_length=1, max_length=128)
    implementation_version: str = Field(min_length=1, max_length=128)
    execution_provider: str = Field(min_length=1, max_length=128)
    model_name: str = Field(min_length=1, max_length=256)
    software_license: str = Field(min_length=1, max_length=128)
    model_license: str = Field(min_length=1, max_length=128)
    artifacts: tuple[ModelArtifact, ...] = Field(min_length=1, max_length=64)
    latency: LatencyProfile
    memory: MemoryProfile
    quality: tuple[BenchmarkMetric, ...] = Field(min_length=1, max_length=32)
    limitations: tuple[str, ...] = Field(default=(), max_length=32)

    @field_validator("quality")
    @classmethod
    def unique_metric_names(
        cls, metrics: tuple[BenchmarkMetric, ...]
    ) -> tuple[BenchmarkMetric, ...]:
        names = [metric.name for metric in metrics]
        if len(names) != len(set(names)):
            raise ValueError("quality metric names must be unique")
        return metrics


class DefaultSelection(StrictModel):
    """Measured default chosen for one component."""

    component: VoiceComponent
    candidate_id: str = Field(min_length=1, max_length=128)
    measured: Literal[True] = True
    requires_livekit: Literal[False] = False
    reason: str = Field(min_length=1, max_length=2048)


class VoiceBenchmarkReport(StrictModel):
    """Complete P14.1 report; partial runs cannot masquerade as a decision."""

    benchmark_version: Literal["1.0"] = "1.0"
    measured_at: datetime
    hardware: HardwareProfile
    corpus: tuple[str, ...] = Field(min_length=3, max_length=64)
    results: tuple[VoiceComponentBenchmark, ...] = Field(min_length=3, max_length=32)
    defaults: tuple[DefaultSelection, ...] = Field(min_length=3, max_length=3)
    methodology: tuple[str, ...] = Field(min_length=1, max_length=64)
    limitations: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("measured_at")
    @classmethod
    def aware_timestamp(cls, value: datetime) -> datetime:
        return require_aware(value, "measured_at")

    @model_validator(mode="after")
    def validate_complete_decision(self) -> VoiceBenchmarkReport:
        components = [result.component for result in self.results]
        if set(components) != {"vad", "stt", "tts"}:
            raise ValueError("report must contain measured VAD, STT and TTS results")
        if len(components) != len(set(components)):
            raise ValueError("this benchmark version accepts one candidate per component")
        selections = {selection.component: selection for selection in self.defaults}
        if set(selections) != {"vad", "stt", "tts"}:
            raise ValueError("report must choose one measured default per component")
        candidates = {result.component: result.candidate_id for result in self.results}
        if any(
            selection.candidate_id != candidates[component]
            for component, selection in selections.items()
        ):
            raise ValueError("every default must reference its measured component candidate")
        return self


def percentile(values: tuple[float, ...] | list[float], percentile_value: float) -> float:
    """Return a linearly interpolated percentile without a numerical dependency."""

    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 <= percentile_value <= 100:
        raise ValueError("percentile must be between 0 and 100")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * percentile_value / 100
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Compute case/punctuation-insensitive word error rate using edit distance."""

    reference_words = _normalized_words(reference)
    hypothesis_words = _normalized_words(hypothesis)
    if not reference_words:
        return 0.0 if not hypothesis_words else 1.0
    previous = list(range(len(hypothesis_words) + 1))
    for reference_index, reference_word in enumerate(reference_words, start=1):
        current = [reference_index]
        for hypothesis_index, hypothesis_word in enumerate(hypothesis_words, start=1):
            substitution = previous[hypothesis_index - 1] + (reference_word != hypothesis_word)
            current.append(
                min(
                    current[hypothesis_index - 1] + 1,
                    previous[hypothesis_index] + 1,
                    substitution,
                )
            )
        previous = current
    return round(previous[-1] / len(reference_words), 6)


def _normalized_words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", value.lower())
