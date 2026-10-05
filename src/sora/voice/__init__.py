"""Voice benchmarking and, in later P14 stages, session orchestration."""

from .benchmark import (
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
from .client import (
    AudioFrame,
    PlaybackSink,
    StreamingVoiceClient,
    SttAdapter,
    TranscriptHypothesis,
    TtsAdapter,
    VadAdapter,
    VadDecision,
    VoiceCoreTransport,
    VoiceLipSyncSink,
)
from .intents import classify_voice_intent, contains_spoken_cursor_reference, new_work_description
from .presentation import (
    SynthesizedAudioChunk,
    VoicePresentationClock,
    VoicePresentationFrame,
    VoicePresentationResetReason,
    pcm_s16le_rms,
)
from .sessions import VoiceFinalization, VoiceGenerationCancelled, VoiceSessionCoordinator

__all__ = [
    "BenchmarkMetric",
    "AudioFrame",
    "DefaultSelection",
    "HardwareProfile",
    "LatencyProfile",
    "MemoryProfile",
    "ModelArtifact",
    "PlaybackSink",
    "StreamingVoiceClient",
    "SynthesizedAudioChunk",
    "SttAdapter",
    "TranscriptHypothesis",
    "TtsAdapter",
    "VadAdapter",
    "VadDecision",
    "VoiceBenchmarkReport",
    "VoiceComponentBenchmark",
    "VoiceGenerationCancelled",
    "VoiceFinalization",
    "VoiceSessionCoordinator",
    "VoiceCoreTransport",
    "VoiceLipSyncSink",
    "VoicePresentationClock",
    "VoicePresentationFrame",
    "VoicePresentationResetReason",
    "classify_voice_intent",
    "contains_spoken_cursor_reference",
    "new_work_description",
    "pcm_s16le_rms",
    "percentile",
    "word_error_rate",
]
