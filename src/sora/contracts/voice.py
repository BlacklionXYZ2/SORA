"""P14 voice-session contracts; raw microphone and synthesized audio stay client-local."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import ContractModel, Identifier, NonEmptyText, require_aware


class VoiceSessionStatus(StrEnum):
    ACTIVE = "active"
    INPUT_UNAVAILABLE = "input_unavailable"
    OUTPUT_UNAVAILABLE = "output_unavailable"
    DEVICES_UNAVAILABLE = "devices_unavailable"
    CLOSED = "closed"


class VoiceTranscriptKind(StrEnum):
    PARTIAL = "partial"
    FINAL = "final"


class VoiceTranscriptDisposition(StrEnum):
    PARTIAL_ACCEPTED = "partial_accepted"
    FINALIZED = "finalized"
    DUPLICATE = "duplicate"
    SUPPRESSED_ECHO = "suppressed_echo"
    INTERRUPTED = "interrupted"


class VoiceConversationIntent(StrEnum):
    """Deterministic high-level handling for a finalized spoken utterance."""

    DIALOGUE = "dialogue"
    STOP_SPEAKING = "stop_speaking"
    STEER_TASK = "steer_task"
    CANCEL_TASK = "cancel_task"
    NEW_WORK = "new_work"


class VoiceControlStatus(StrEnum):
    APPLIED = "applied"
    CLARIFICATION_REQUIRED = "clarification_required"
    UNSUPPORTED = "unsupported"
    NOT_APPLIED = "not_applied"


class VoiceReferenceStatus(StrEnum):
    RESOLVED = "resolved"
    CLARIFICATION_REQUIRED = "clarification_required"


class VoiceDeviceKind(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


class VoiceDeviceState(StrEnum):
    LOST = "lost"
    RECOVERED = "recovered"


class VoicePlaybackState(StrEnum):
    QUEUED = "queued"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class VoiceEmotion(StrEnum):
    """Coarse utterance intent; never a per-frame animation instruction."""

    NEUTRAL = "neutral"
    WARM = "warm"
    CHEERFUL = "cheerful"
    CONCERNED = "concerned"
    FOCUSED = "focused"


class VoiceInterruptionKind(StrEnum):
    BARGE_IN = "barge_in"
    STOP_SPEAKING = "stop_speaking"
    CANCEL_RESPONSE = "cancel_response"


class VoiceInterruptionDisposition(StrEnum):
    APPLIED = "applied"
    DUPLICATE = "duplicate"
    NO_ACTIVE_RESPONSE = "no_active_response"


class VoiceSessionStartRequest(ContractModel):
    session_id: Identifier
    input_device_id: Identifier
    output_device_id: Identifier
    language: str = Field(default="en", min_length=2, max_length=35, pattern=r"^[A-Za-z0-9-]+$")
    voice_id: Identifier = "af_heart"
    echo_reference_enabled: bool = True
    started_at: datetime

    @field_validator("started_at")
    @classmethod
    def validate_started_at(cls, value: datetime) -> datetime:
        return require_aware(value, "started_at")


class VoiceTranscriptEvent(ContractModel):
    event_id: Identifier
    session_id: Identifier
    utterance_id: Identifier
    sequence: int = Field(ge=0, le=1_000_000)
    kind: VoiceTranscriptKind
    text: NonEmptyText
    confidence: float = Field(ge=0, le=1)
    device_generation: int = Field(ge=1, le=1_000_000)
    speech_started_at: datetime
    speech_ended_at: datetime | None = None
    reference_spoken_at: datetime | None = None
    captured_at: datetime
    # The utterance itself as a base64 mono 16 kHz WAV, for brains that hear audio natively.
    # Optional: Core ignores it unless the brain supports audio and Settings allow it.
    audio_wav_base64: str | None = Field(default=None, min_length=60, max_length=2_700_000)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("transcript text cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_timing(self) -> VoiceTranscriptEvent:
        require_aware(self.speech_started_at, "speech_started_at")
        require_aware(self.captured_at, "captured_at")
        if self.speech_started_at > self.captured_at:
            raise ValueError("speech cannot start after transcript capture")
        if self.kind is VoiceTranscriptKind.FINAL and self.speech_ended_at is None:
            raise ValueError("final transcript requires speech_ended_at")
        if self.kind is VoiceTranscriptKind.PARTIAL and self.speech_ended_at is not None:
            raise ValueError("partial transcript cannot claim a final speech end")
        if self.speech_ended_at is not None:
            require_aware(self.speech_ended_at, "speech_ended_at")
            if not self.speech_started_at <= self.speech_ended_at <= self.captured_at:
                raise ValueError("speech timestamps are out of order")
        if self.reference_spoken_at is not None:
            require_aware(self.reference_spoken_at, "reference_spoken_at")
            reference_end = self.speech_ended_at or self.captured_at
            if not self.speech_started_at <= self.reference_spoken_at <= reference_end:
                raise ValueError("spoken reference timestamp is outside the utterance")
        return self


class VoiceConversationAction(ContractModel):
    intent: VoiceConversationIntent
    status: VoiceControlStatus
    message: NonEmptyText
    task_id: Identifier | None = None
    output_stopped: bool = False

    @model_validator(mode="after")
    def validate_action(self) -> VoiceConversationAction:
        task_intents = {
            VoiceConversationIntent.STEER_TASK,
            VoiceConversationIntent.CANCEL_TASK,
            VoiceConversationIntent.NEW_WORK,
        }
        if self.status is VoiceControlStatus.APPLIED and self.intent in task_intents:
            if self.task_id is None:
                raise ValueError("applied task control requires a task ID")
        if self.intent is VoiceConversationIntent.STOP_SPEAKING and self.task_id is not None:
            raise ValueError("stop-speaking control cannot target a task")
        return self


class VoiceReferenceResolution(ContractModel):
    status: VoiceReferenceStatus
    reason: NonEmptyText
    reference_spoken_at: datetime | None = None
    reference_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_resolution(self) -> VoiceReferenceResolution:
        if self.reference_spoken_at is not None:
            require_aware(self.reference_spoken_at, "reference_spoken_at")
        if (self.status is VoiceReferenceStatus.RESOLVED) != (self.reference_id is not None):
            raise ValueError("only a resolved spoken reference can contain a reference ID")
        return self


class VoiceDeviceEvent(ContractModel):
    event_id: Identifier
    session_id: Identifier
    kind: VoiceDeviceKind
    device_id: Identifier
    state: VoiceDeviceState
    generation: int = Field(ge=1, le=1_000_000)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        return require_aware(value, "occurred_at")


class VoicePlaybackEvent(ContractModel):
    event_id: Identifier
    session_id: Identifier
    playback_id: Identifier
    sequence: int = Field(ge=0, le=1_000_000)
    state: Literal[
        VoicePlaybackState.STARTED,
        VoicePlaybackState.COMPLETED,
        VoicePlaybackState.FAILED,
    ]
    output_device_id: Identifier
    device_generation: int = Field(ge=1, le=1_000_000)
    occurred_at: datetime
    position_ms: int = Field(default=0, ge=0, le=86_400_000)
    detail: str | None = Field(default=None, max_length=512)

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        return require_aware(value, "occurred_at")


class VoicePlaybackCommand(ContractModel):
    playback_id: Identifier
    session_id: Identifier
    utterance_id: Identifier
    output_device_id: Identifier
    device_generation: int = Field(ge=1)
    output_epoch: int = Field(ge=0)
    voice_id: Identifier
    emotion: VoiceEmotion = VoiceEmotion.WARM
    text: NonEmptyText
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_lifetime(self) -> VoicePlaybackCommand:
        require_aware(self.created_at, "created_at")
        require_aware(self.expires_at, "expires_at")
        if self.expires_at <= self.created_at:
            raise ValueError("playback command must expire after creation")
        return self


class VoiceSpeechPreview(ContractModel):
    """Sentences of a voice reply that the model is still writing.

    Core opens the playback at the first finished sentence so the audio worker can start
    speaking before the turn commits. The worker polls with ``after`` and gets sentences from
    that index; ``finished`` means the model's reply text is complete.
    """

    session_id: Identifier
    playback: VoicePlaybackCommand | None = None
    sentences: tuple[NonEmptyText, ...] = Field(default=(), max_length=256)
    next_index: int = Field(ge=0, le=100_000)
    finished: bool = False


class VoiceSessionSnapshot(ContractModel):
    session_id: Identifier
    status: VoiceSessionStatus
    input_device_id: Identifier
    output_device_id: Identifier
    input_generation: int = Field(ge=1)
    output_generation: int = Field(ge=1)
    language: str
    voice_id: Identifier
    partial_utterance_id: Identifier | None = None
    partial_text: str | None = Field(default=None, max_length=16_384)
    finalized_utterances: int = Field(ge=0)
    active_playback_id: Identifier | None = None
    playback_state: VoicePlaybackState | None = None
    output_epoch: int = Field(ge=0)
    active_generation_id: Identifier | None = None
    generation_cancel_requested: bool = False
    output_suppressed: bool = False
    opened_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_snapshot(self) -> VoiceSessionSnapshot:
        require_aware(self.opened_at, "opened_at")
        require_aware(self.updated_at, "updated_at")
        if self.updated_at < self.opened_at:
            raise ValueError("voice session update precedes session opening")
        if (self.partial_utterance_id is None) != (self.partial_text is None):
            raise ValueError("partial utterance ID and text must appear together")
        if (self.active_playback_id is None) != (self.playback_state is None):
            raise ValueError("active playback ID and state must appear together")
        if self.active_generation_id is None and self.generation_cancel_requested:
            raise ValueError("generation cancellation requires an active generation")
        if self.active_generation_id is None and self.output_suppressed:
            raise ValueError("output suppression requires an active generation")
        return self


class VoiceInterruptionRequest(ContractModel):
    event_id: Identifier
    session_id: Identifier
    kind: VoiceInterruptionKind
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        return require_aware(value, "occurred_at")


class VoiceInterruptionResult(ContractModel):
    disposition: VoiceInterruptionDisposition
    kind: VoiceInterruptionKind
    session: VoiceSessionSnapshot
    generation_id: Identifier | None = None
    generation_cancel_requested: bool = False
    playback_id: Identifier | None = None
    output_stopped: bool = False

    @model_validator(mode="after")
    def validate_interruption(self) -> VoiceInterruptionResult:
        if self.generation_cancel_requested and self.generation_id is None:
            raise ValueError("generation cancellation requires a generation ID")
        if self.disposition is VoiceInterruptionDisposition.NO_ACTIVE_RESPONSE:
            if self.generation_id is not None or self.playback_id is not None:
                raise ValueError("no-active interruption cannot identify active work")
            if self.generation_cancel_requested or self.output_stopped:
                raise ValueError("no-active interruption cannot report stopped work")
        return self


class VoiceTurnResult(ContractModel):
    disposition: VoiceTranscriptDisposition
    session: VoiceSessionSnapshot
    user_message_id: Identifier | None = None
    assistant_message_id: Identifier | None = None
    assistant_text: str | None = Field(default=None, max_length=16_384)
    playback: VoicePlaybackCommand | None = None
    control: VoiceConversationAction | None = None
    reference: VoiceReferenceResolution | None = None

    @model_validator(mode="after")
    def validate_result(self) -> VoiceTurnResult:
        has_turn = self.disposition in {
            VoiceTranscriptDisposition.FINALIZED,
            VoiceTranscriptDisposition.DUPLICATE,
        }
        values = (self.user_message_id, self.assistant_message_id, self.assistant_text)
        if has_turn and any(value is None for value in values):
            raise ValueError("finalized and duplicate results require durable turn IDs and text")
        if not has_turn and any(value is not None for value in values):
            raise ValueError("non-final transcript results cannot reference durable messages")
        if (
            self.disposition is not VoiceTranscriptDisposition.FINALIZED
            and self.playback is not None
        ):
            raise ValueError("only a newly finalized turn may queue playback")
        return self
